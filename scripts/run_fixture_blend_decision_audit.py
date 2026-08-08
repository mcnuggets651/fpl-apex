#!/usr/bin/env python3
"""Shadow-only decision impact audit for the validated 50/50 Understat-Elo candidate.

This script never publishes or changes production configuration. It runs the current
pipeline, constructs the research-only convex fixture surface without Elo
multiplication, reprices only the fixture-sensitive transparent Apex terms, updates
canonical xP by the exact effective Apex ensemble share, and solves production and
shadow max-EV squads side by side.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.data.understat import load_understat_history, season_start_year
from apex_fpl.models.fixtures import fixture_multipliers
from apex_fpl.models.team_goals import TeamGoalConfig, build_team_goal_surface, build_team_ratings
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import optimise_gameweek_mechanics
from apex_fpl.services.data_quality import official_strength_is_usable
from apex_fpl.services.decision_eligibility import captain_eligible_ids
from apex_fpl.services.pipeline import run_pipeline
from apex_fpl.services.projection_audit import reprice_apex_for_fixture_shadow
from apex_fpl.services.provenance import load_upstream_pins

UNDERSTAT_WEIGHT = 0.50
UNDERSTAT_CFG = TeamGoalConfig(half_life_days=180.0, prior_matches=5.0)


def _records(frame: pd.DataFrame) -> list[dict]:
    return [] if frame.empty else json.loads(frame.to_json(orient="records"))


def _ids(frame: pd.DataFrame) -> set[int]:
    if frame.empty:
        return set()
    return set(pd.to_numeric(frame["player_id"], errors="coerce").dropna().astype(int))


def _gw_xp(projections: pd.DataFrame, gw: int) -> dict[int, float]:
    d = projections[projections["gw"] == int(gw)]
    values = d.groupby("player_id")["xp"].sum()
    return {int(pid): float(value) for pid, value in values.items()}


def _appearance(players: pd.DataFrame) -> dict[int, float]:
    values = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): float(prob)
        for pid, prob in zip(players["player_id"].astype(int), values, strict=False)
    }


def _mechanics(solution, projections, gw, players, eligible) -> dict:
    result = optimise_gameweek_mechanics(
        solution.squad,
        solution.xi,
        _gw_xp(projections, gw),
        _appearance(players),
        captain_eligible=eligible,
    ).to_dict()
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }
    result["captain_name"] = names.get(result["captain_id"], str(result["captain_id"]))
    result["vice_captain_name"] = names.get(
        result["vice_captain_id"], str(result["vice_captain_id"])
    )
    result["outfield_bench_order_names"] = [
        names.get(pid, str(pid)) for pid in result["outfield_bench_order"]
    ]
    return result


def _blend_surface(production_fx: pd.DataFrame, understat_fx: pd.DataFrame) -> pd.DataFrame:
    keys = ["gw", "team", "opponent", "is_home"]
    p = production_fx[
        [*keys, "expected_team_goals", "expected_goals_against"]
    ].rename(
        columns={
            "expected_team_goals": "prod_xg",
            "expected_goals_against": "prod_xga",
        }
    )
    u = understat_fx[
        [*keys, "expected_team_goals", "expected_goals_against"]
    ].rename(
        columns={
            "expected_team_goals": "understat_xg",
            "expected_goals_against": "understat_xga",
        }
    )
    d = p.merge(u, on=keys, how="inner", validate="one_to_one")
    if len(d) != len(production_fx):
        raise ValueError(
            f"fixture blend coverage mismatch: {len(d)}/{len(production_fx)} fixture sides"
        )
    alpha = UNDERSTAT_WEIGHT
    d["expected_team_goals"] = alpha * d["understat_xg"] + (1.0 - alpha) * d["prod_xg"]
    d["expected_goals_against"] = (
        alpha * d["understat_xga"] + (1.0 - alpha) * d["prod_xga"]
    )
    d["clean_sheet_prob"] = np.exp(-d["expected_goals_against"])
    d["team_goal_source"] = "shadow_convex_understat_elo_50_50"
    return d[
        [
            *keys,
            "expected_team_goals",
            "expected_goals_against",
            "clean_sheet_prob",
            "team_goal_source",
        ]
    ]


def _shadow_canonical_projection(
    production: pd.DataFrame,
    shadow_apex: pd.DataFrame,
) -> pd.DataFrame:
    keys = ["player_id", "gw"]
    delta = shadow_apex[keys + ["apex_xp"]].rename(
        columns={"apex_xp": "shadow_apex_xp"}
    )
    out = production.merge(delta, on=keys, how="left", validate="one_to_one")
    old_apex = pd.to_numeric(out["apex_xp"], errors="coerce").fillna(0.0).to_numpy(float)
    old_contribution = pd.to_numeric(
        out.get("xp_expert_apex_model", 0.0), errors="coerce"
    ).fillna(0.0).to_numpy(float)
    effective_share = np.divide(
        old_contribution,
        old_apex,
        out=np.zeros(len(out), dtype=float),
        where=np.abs(old_apex) > 1e-12,
    )
    new_apex = pd.to_numeric(out["shadow_apex_xp"], errors="coerce").fillna(
        pd.Series(old_apex, index=out.index)
    ).to_numpy(float)
    old_xp = pd.to_numeric(out["xp"], errors="coerce").fillna(0.0).to_numpy(float)
    out["production_xp"] = old_xp
    out["effective_apex_ensemble_share"] = effective_share
    out["xp"] = old_xp + effective_share * (new_apex - old_apex)
    out["apex_xp"] = new_apex
    return out


def _solution_payload(solution, mechanics) -> dict:
    return {
        "status": solution.status,
        "objective": float(solution.objective),
        "squad": _records(solution.squad),
        "xi": _records(solution.xi),
        "captain": mechanics["captain_name"],
        "vice_captain": mechanics["vice_captain_name"],
        "expected_total_with_exact_gw1_mechanics": float(mechanics["expected_total"]),
        "bench_order": mechanics["outfield_bench_order_names"],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", default="reports/fixture_blend_decision_audit.json")
    args = parser.parse_args()

    settings = load_settings()
    out = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=False,
    )
    if not out.safety.safe_to_act or not out.safety.full_apex_ready:
        raise SystemExit(
            "fixture blend decision audit blocked by production safety gate: "
            + ("; ".join(out.safety.blockers) or "unknown blocker")
        )

    http = CachedHttp(settings.cache_dir)
    official = OfficialFPLClient(http).snapshot(force=False)
    pins = load_upstream_pins(settings.upstreams_lock_path)
    core_ref = str(pins.get("fpl_core_insights", {}).get("commit", "")) or "main"
    core = FPLCoreClient(http, settings.season, ref=core_ref)
    core_elos = core.fixture_elos(out.gameweeks, force=args.force)
    strength_ok, strength_detail = official_strength_is_usable(official.teams)
    if strength_ok:
        raise SystemExit(
            "shadow blend audit is currently validated only for the pre-GW neutral+Elo "
            f"production fallback; official strength became usable: {strength_detail}"
        )

    production_fx = fixture_multipliers(
        official.fixtures,
        official.teams,
        out.gameweeks,
        core_elos=core_elos,
        use_official_strength=False,
        team_goal_surface=None,
    )

    active_year = season_start_year(settings.season)
    first_year = max(2018, active_year - settings.understat_history_seasons)
    history = load_understat_history(
        range(first_year, active_year + 1),
        active_season=active_year,
        cache_dir=settings.cache_dir / "understat",
        refresh_active=args.force,
    )
    ratings = build_team_ratings(
        history.matches,
        official.teams,
        config=UNDERSTAT_CFG,
    )
    understat_surface = build_team_goal_surface(
        official.fixtures,
        ratings,
        out.gameweeks,
        config=UNDERSTAT_CFG,
    )
    understat_fx = fixture_multipliers(
        official.fixtures,
        official.teams,
        out.gameweeks,
        core_elos=None,
        use_official_strength=False,
        team_goal_surface=understat_surface,
    )

    blend_surface = _blend_surface(production_fx, understat_fx)
    blend_fx = fixture_multipliers(
        official.fixtures,
        official.teams,
        out.gameweeks,
        core_elos=None,
        use_official_strength=False,
        team_goal_surface=blend_surface,
    )

    team_map = official.players[["player_id", "team"]].drop_duplicates("player_id")
    shadow_apex = reprice_apex_for_fixture_shadow(
        out.projections,
        production_fx,
        blend_fx,
        team_map,
    )
    shadow_projection = _shadow_canonical_projection(out.projections, shadow_apex)

    players = out.players.drop(columns=["team"], errors="ignore").merge(
        team_map, on="player_id", how="left", validate="one_to_one"
    )
    eligible = captain_eligible_ids(players)
    common = dict(
        players=players,
        gameweeks=out.gameweeks,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        captain_eligible=eligible,
        projection_col="xp",
    )
    prod_solution = optimise_initial_horizon(
        **common,
        projections=out.projections,
    )
    shadow_solution = optimise_initial_horizon(
        **common,
        projections=shadow_projection,
    )
    if prod_solution.status != "Optimal" or shadow_solution.status != "Optimal":
        raise SystemExit(
            f"shadow optimiser failed: production={prod_solution.status}, "
            f"shadow={shadow_solution.status}"
        )

    prod_mechanics = _mechanics(
        prod_solution, out.projections, out.gameweeks[0], players, eligible
    )
    shadow_mechanics = _mechanics(
        shadow_solution, shadow_projection, out.gameweeks[0], players, eligible
    )

    prod_ids = _ids(prod_solution.squad)
    shadow_ids = _ids(shadow_solution.squad)
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }

    player_delta = shadow_projection.groupby("player_id", as_index=False).agg(
        production_horizon_xp=("production_xp", "sum"),
        shadow_horizon_xp=("xp", "sum"),
        mean_effective_apex_share=("effective_apex_ensemble_share", "mean"),
    )
    player_delta["delta_horizon_xp"] = (
        player_delta["shadow_horizon_xp"] - player_delta["production_horizon_xp"]
    )
    player_delta["web_name"] = player_delta["player_id"].map(names)

    focus_names = {"shaw", "thiaw", "virgil", "calafiori", "gabriel", "saliba"}
    focus = player_delta[
        player_delta["web_name"].astype(str).str.casefold().isin(focus_names)
    ].sort_values("delta_horizon_xp", ascending=False)

    report = {
        "contract": "apex-fixture-blend-decision-audit-v1",
        "production_changed": False,
        "canonical_publish_attempted": False,
        "gameweeks": out.gameweeks,
        "official_strength_usable": False,
        "fixture_candidate": {
            "understat_weight": UNDERSTAT_WEIGHT,
            "elo_weight": 1.0 - UNDERSTAT_WEIGHT,
            "understat_half_life_days": UNDERSTAT_CFG.half_life_days,
            "understat_prior_matches": UNDERSTAT_CFG.prior_matches,
            "elo_applied_after_blend": False,
        },
        "production": _solution_payload(prod_solution, prod_mechanics),
        "shadow_blend": _solution_payload(shadow_solution, shadow_mechanics),
        "decision_delta": {
            "squad_overlap": len(prod_ids & shadow_ids),
            "players_in": [names[pid] for pid in sorted(shadow_ids - prod_ids)],
            "players_out": [names[pid] for pid in sorted(prod_ids - shadow_ids)],
            "objective_delta": float(shadow_solution.objective - prod_solution.objective),
            "gw1_exact_mechanics_delta": float(
                shadow_mechanics["expected_total"] - prod_mechanics["expected_total"]
            ),
            "captain_changed": (
                shadow_mechanics["captain_name"] != prod_mechanics["captain_name"]
            ),
        },
        "focus_player_fixture_xp_effects": _records(focus),
        "largest_canonical_xp_increases": _records(
            player_delta.nlargest(20, "delta_horizon_xp")
        ),
        "largest_canonical_xp_decreases": _records(
            player_delta.nsmallest(20, "delta_horizon_xp")
        ),
        "evidence_status": (
            "shadow research candidate only; historical blend gate did not pass the "
            "predeclared clean-sheet point-estimate criterion"
        ),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
