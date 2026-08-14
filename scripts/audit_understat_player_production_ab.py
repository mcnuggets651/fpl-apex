#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.understat import fetch_understat_season, season_start_year
from apex_fpl.evaluation.understat_player_ab import (
    map_understat_to_current_ids,
    reprice_projection_surface,
)
from apex_fpl.evaluation.understat_players import normalise_understat_players
from apex_fpl.models.scenarios import generate_projection_scenarios
from apex_fpl.optimisation.cvar import optimise_initial_cvar
from apex_fpl.optimisation.exact_decision import (
    optimise_exact_horizon_decision,
    optimise_fixed_squad_gameweek,
)
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.stability import selection_regret_analysis
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility


def _xp_map(projections: pd.DataFrame, gw: int) -> dict[int, float]:
    rows = projections[projections["gw"] == int(gw)]
    values = rows.groupby("player_id")["xp"].sum()
    return {int(pid): float(value) for pid, value in values.items()}


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    values = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): min(max(float(value), 0.0), 1.0)
        for pid, value in zip(players["player_id"].astype(int), values)
    }


def _fixed_squad_exact_score(
    squad: pd.DataFrame,
    projections: pd.DataFrame,
    players: pd.DataFrame,
    gameweeks: list[int],
    *,
    decay: float,
    captain_eligible: set[int],
    xi_eligible: set[int],
) -> tuple[float, list[dict]]:
    appearance = _appearance_map(players)
    weeks: list[dict] = []
    objective = 0.0
    for offset, gw in enumerate(gameweeks):
        xp = _xp_map(projections, gw)
        xi, mechanics = optimise_fixed_squad_gameweek(
            squad,
            xp,
            appearance,
            captain_eligible=captain_eligible,
            xi_eligible=xi_eligible,
        )
        discount = float(decay) ** offset
        objective += discount * float(mechanics.expected_total_points)
        weeks.append(
            {
                "gw": int(gw),
                "discount": discount,
                "expected_total_points": float(mechanics.expected_total_points),
                "discounted_expected_points": discount * float(mechanics.expected_total_points),
                "xi_ids": sorted(xi["player_id"].astype(int).tolist()),
                "captain_id": int(mechanics.captain_id),
                "vice_captain_id": int(mechanics.vice_captain_id),
                "bench_gk_id": int(mechanics.bench_gk_id),
                "outfield_bench_order": [int(pid) for pid in mechanics.outfield_bench_order],
            }
        )
    return float(objective), weeks


def _solution_summary(decision, names: dict[int, str]) -> dict:
    ids = sorted(decision.solution.squad["player_id"].astype(int).tolist())
    gw1 = decision.weeks[0]
    return {
        "status": decision.status,
        "exact_horizon_objective": float(decision.objective),
        "squad_ids": ids,
        "squad_names": [names.get(pid, str(pid)) for pid in ids],
        "gw1_xi_ids": [int(pid) for pid in gw1.xi_ids],
        "gw1_xi_names": [names.get(int(pid), str(pid)) for pid in gw1.xi_ids],
        "captain_id": int(gw1.mechanics.captain_id),
        "captain_name": names.get(int(gw1.mechanics.captain_id), str(gw1.mechanics.captain_id)),
        "vice_captain_id": int(gw1.mechanics.vice_captain_id),
        "vice_captain_name": names.get(
            int(gw1.mechanics.vice_captain_id), str(gw1.mechanics.vice_captain_id)
        ),
        "gw1_exact_points": float(gw1.mechanics.expected_total_points),
        "near_equivalent_candidate_count": int(len(decision.near_equivalent_candidates)),
    }


def _rank_table(
    players: pd.DataFrame,
    baseline: pd.DataFrame,
    challenger: pd.DataFrame,
) -> pd.DataFrame:
    b = baseline.groupby("player_id", as_index=False)["weighted_xp"].sum().rename(
        columns={"weighted_xp": "baseline_horizon_xp"}
    )
    c = challenger.groupby("player_id", as_index=False)["weighted_xp"].sum().rename(
        columns={"weighted_xp": "challenger_horizon_xp"}
    )
    out = b.merge(c, on="player_id", how="outer").fillna(0.0)
    keep = [
        col
        for col in ["player_id", "web_name", "team_name", "position", "price"]
        if col in players.columns
    ]
    out = out.merge(players[keep].drop_duplicates("player_id"), on="player_id", how="left")
    out["delta_horizon_xp"] = out["challenger_horizon_xp"] - out["baseline_horizon_xp"]
    out["baseline_rank"] = out["baseline_horizon_xp"].rank(method="min", ascending=False)
    out["challenger_rank"] = out["challenger_horizon_xp"].rank(method="min", ascending=False)
    out["rank_change"] = out["baseline_rank"] - out["challenger_rank"]
    return out.sort_values("challenger_horizon_xp", ascending=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument(
        "--historical-audit",
        default="reports/understat_player_predictive_audit.json",
    )
    parser.add_argument("--output", default="reports/understat_player_production_ab.json")
    parser.add_argument("--scenario-seed", type=int, default=20260807)
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
    parser.add_argument("--alternatives", type=int, default=12)
    args = parser.parse_args()

    historical_path = Path(args.historical_audit)
    if not historical_path.exists():
        raise SystemExit(f"missing predictive audit prerequisite: {historical_path}")
    historical = json.loads(historical_path.read_text(encoding="utf-8"))
    if historical.get("pass") is not True:
        raise SystemExit("historical Understat player predictive gate is not green")
    xg_weight = float(historical.get("selected_xg_understat_weight", -1))
    xa_weight = float(historical.get("selected_xa_understat_weight", -1))
    if abs(xg_weight - 0.50) > 1e-12 or abs(xa_weight - 0.30) > 1e-12:
        raise SystemExit(
            "validated Understat weights changed; this A/B is frozen to 0.50 xG / 0.30 xA"
        )

    bundle = DecisionBundle.load(args.bundle_dir)
    out = bundle.to_pipeline_output()
    settings = bundle.settings
    if not out.safety.safe_to_act or not out.safety.full_apex_ready:
        raise SystemExit("sealed Apex bundle is not production-ready")

    decision_players, evidence_report = evidence_eligibility(out.players, out.news_audit)
    captain_eligible = captain_eligible_ids(decision_players)
    xi_eligible = set(
        decision_players.loc[
            decision_players["xi_evidence_eligible"], "player_id"
        ].astype(int)
    )
    if len(captain_eligible) < 2:
        raise SystemExit("fewer than two captain-eligible players on sealed bundle")

    core_pin = str(
        (bundle.manifest.get("upstreams", {}).get("fpl_core_insights", {}) or {}).get(
            "commit", ""
        )
    )
    if not core_pin:
        raise SystemExit("sealed bundle has no FPL Core pin")
    http = CachedHttp(Path("data/cache"))
    current_core_players = FPLCoreClient(
        http,
        str(settings["season"]),
        ref=core_pin,
    ).players(force=False)
    previous_year = season_start_year(str(settings["season"])) - 1
    understat = normalise_understat_players(
        fetch_understat_season(
            previous_year,
            cache_dir=Path("data/cache/understat"),
            refresh=False,
        ),
        previous_year,
    )
    understat_rates = map_understat_to_current_ids(current_core_players, understat)

    baseline = out.projections.copy()
    challenger, repricing = reprice_projection_surface(
        decision_players,
        baseline,
        understat_rates,
        dict(settings["weights"]),
        float(settings["risk_penalty"]),
        xg_weight=xg_weight,
        xa_weight=xa_weight,
    )
    gws = [int(gw) for gw in out.gameweeks]
    decay = float(settings["fixture_decay"])
    exact_kwargs = dict(
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=decay,
        shortlist_bench_weight=float(settings["approximate_bench_weight"]),
        candidate_limit=int(settings.get("exact_candidate_limit", 16)),
        candidate_regret_fraction=float(settings.get("exact_candidate_regret_fraction", 0.005)),
        near_equivalent_points=float(settings.get("exact_near_equivalent_points", 0.25)),
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    baseline_exact = optimise_exact_horizon_decision(
        decision_players, baseline, gws, **exact_kwargs
    )
    challenger_exact = optimise_exact_horizon_decision(
        decision_players, challenger, gws, **exact_kwargs
    )
    if baseline_exact.status != "Optimal" or challenger_exact.status != "Optimal":
        raise SystemExit("baseline/challenger exact-horizon solve failed")

    baseline_squad_on_challenger, _ = _fixed_squad_exact_score(
        baseline_exact.solution.squad,
        challenger,
        decision_players,
        gws,
        decay=decay,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    challenger_squad_on_baseline, _ = _fixed_squad_exact_score(
        challenger_exact.solution.squad,
        baseline,
        decision_players,
        gws,
        decay=decay,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    challenger_gain = float(challenger_exact.objective - baseline_squad_on_challenger)
    baseline_regret = float(baseline_exact.objective - challenger_squad_on_baseline)

    initial_common = dict(
        players=decision_players,
        gameweeks=gws,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=decay,
        bench_weight=float(settings["approximate_bench_weight"]),
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        projection_col="xp",
    )
    baseline_initial = optimise_initial_horizon(projections=baseline, **initial_common)
    challenger_initial = optimise_initial_horizon(projections=challenger, **initial_common)
    baseline_regret_table = selection_regret_analysis(
        decision_players,
        baseline,
        gws,
        baseline_initial,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=decay,
        bench_weight=float(settings["approximate_bench_weight"]),
        alternative_limit=args.alternatives,
        captain_eligible=captain_eligible,
    )
    challenger_regret_table = selection_regret_analysis(
        decision_players,
        challenger,
        gws,
        challenger_initial,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=decay,
        bench_weight=float(settings["approximate_bench_weight"]),
        alternative_limit=args.alternatives,
        captain_eligible=captain_eligible,
    )

    baseline_scenarios = generate_projection_scenarios(
        decision_players,
        baseline,
        gws,
        n_scenarios=args.stochastic_scenarios,
        seed=args.scenario_seed,
    )
    challenger_scenarios = generate_projection_scenarios(
        decision_players,
        challenger,
        gws,
        n_scenarios=args.stochastic_scenarios,
        seed=args.scenario_seed,
    )
    robust_common = dict(
        players=decision_players,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=decay,
        bench_weight=float(settings["approximate_bench_weight"]),
        cvar_alpha=0.10,
        cvar_weight=0.20,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    baseline_robust = optimise_initial_cvar(
        scenarios=baseline_scenarios,
        **robust_common,
    )
    challenger_robust = optimise_initial_cvar(
        scenarios=challenger_scenarios,
        **robust_common,
    )
    if baseline_robust.status != "Optimal" or challenger_robust.status != "Optimal":
        raise SystemExit("baseline/challenger CVaR solve failed")

    names = {
        int(row.player_id): str(row.web_name)
        for row in decision_players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }
    baseline_ids = set(baseline_exact.solution.squad["player_id"].astype(int))
    challenger_ids = set(challenger_exact.solution.squad["player_id"].astype(int))
    baseline_xi = set(baseline_exact.solution.xi["player_id"].astype(int))
    challenger_xi = set(challenger_exact.solution.xi["player_id"].astype(int))

    mapped_ids = set(understat_rates["player_id"].astype(int))
    relevant = decision_players[
        pd.to_numeric(decision_players.get("expected_minutes", 0), errors="coerce") >= 45
    ]
    relevant_ids = set(relevant["player_id"].astype(int))
    relevant_coverage = (
        len(mapped_ids & relevant_ids) / len(relevant_ids) if relevant_ids else 0.0
    )
    baseline_tolerance = max(
        float(settings.get("exact_near_equivalent_points", 0.25)),
        0.005 * float(baseline_exact.objective),
    )

    promotion_eligible = bool(
        historical.get("pass") is True
        and relevant_coverage >= 0.60
        and repricing["zero_base_unrepriced_players"] <= 5
        and challenger_gain >= -1e-8
        and baseline_regret <= baseline_tolerance + 1e-8
        and baseline_robust.status == "Optimal"
        and challenger_robust.status == "Optimal"
    )

    rank_table = _rank_table(decision_players, baseline, challenger)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    rank_table.to_csv(output_path.with_name("understat_player_production_ab_rankings.csv"), index=False)
    baseline_regret_table.to_csv(
        output_path.with_name("understat_player_production_ab_baseline_regret.csv"),
        index=False,
    )
    challenger_regret_table.to_csv(
        output_path.with_name("understat_player_production_ab_challenger_regret.csv"),
        index=False,
    )
    challenger.to_csv(
        output_path.with_name("understat_player_production_ab_challenger_surface.csv"),
        index=False,
    )

    payload = {
        "contract": "apex-understat-player-production-ab-v1",
        "production_changed": False,
        "decision_bundle_id": bundle.bundle_id,
        "official_snapshot": bundle.manifest.get("official_snapshot"),
        "historical_predictive_prerequisite": {
            "contract": historical.get("contract"),
            "pass": historical.get("pass"),
            "xg_understat_weight": xg_weight,
            "xa_understat_weight": xa_weight,
        },
        "challenger_policy": {
            "source_season": previous_year,
            "identity_policy": "current pinned FPL Core IDs + unique normalized full-name match",
            "direct_attacking_signal_only": True,
            "bonus_prior_held_fixed": True,
            "all_other_projection_inputs": "sealed baseline decision bundle",
            "scenario_seed_shared": args.scenario_seed,
            "scenario_count": args.stochastic_scenarios,
        },
        "coverage": {
            **repricing,
            "mapped_rate_rows": int(len(understat_rates)),
            "decision_relevant_players_expected_minutes_ge_45": int(len(relevant_ids)),
            "decision_relevant_mapped_players": int(len(mapped_ids & relevant_ids)),
            "decision_relevant_mapping_rate": float(relevant_coverage),
        },
        "baseline": _solution_summary(baseline_exact, names),
        "challenger": _solution_summary(challenger_exact, names),
        "decision_comparison": {
            "squad_overlap": int(len(baseline_ids & challenger_ids)),
            "squad_changed_ids": sorted(baseline_ids ^ challenger_ids),
            "squad_changed_names": [names.get(pid, str(pid)) for pid in sorted(baseline_ids ^ challenger_ids)],
            "gw1_xi_overlap": int(len(baseline_xi & challenger_xi)),
            "captain_agrees": bool(
                baseline_exact.weeks[0].mechanics.captain_id
                == challenger_exact.weeks[0].mechanics.captain_id
            ),
            "baseline_squad_on_challenger_exact_objective": baseline_squad_on_challenger,
            "challenger_squad_on_baseline_exact_objective": challenger_squad_on_baseline,
            "challenger_surface_selection_gain": challenger_gain,
            "baseline_surface_regret_of_challenger": baseline_regret,
            "baseline_noninferiority_tolerance": baseline_tolerance,
        },
        "robustness": {
            "baseline": {
                "objective": float(baseline_robust.objective),
                "mean_points": float(baseline_robust.mean_points),
                "lower_tail_cvar": float(baseline_robust.lower_tail_cvar),
                "squad_ids": sorted(baseline_robust.squad["player_id"].astype(int).tolist()),
            },
            "challenger": {
                "objective": float(challenger_robust.objective),
                "mean_points": float(challenger_robust.mean_points),
                "lower_tail_cvar": float(challenger_robust.lower_tail_cvar),
                "squad_ids": sorted(challenger_robust.squad["player_id"].astype(int).tolist()),
            },
        },
        "ranking_moves": {
            "largest_increases": json.loads(
                rank_table.nlargest(20, "delta_horizon_xp").to_json(orient="records")
            ),
            "largest_decreases": json.loads(
                rank_table.nsmallest(20, "delta_horizon_xp").to_json(orient="records")
            ),
        },
        "acceptance_gate": {
            "historical_predictive_gate_must_pass": True,
            "minimum_relevant_mapping_rate": 0.60,
            "maximum_zero_base_unrepriced_players": 5,
            "challenger_selection_gain_must_be_nonnegative": True,
            "challenger_must_be_noninferior_on_baseline_surface": True,
            "baseline_surface_regret_limit": baseline_tolerance,
            "both_cvar_solves_must_be_optimal": True,
        },
        "pass": promotion_eligible,
        "recommendation": (
            "eligible_for_bounded_player_blend_production_integration"
            if promotion_eligible
            else "remain_shadow_do_not_change_canonical_player_rates"
        ),
        "evidence_eligibility": evidence_report,
    }
    output_path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, default=str))


if __name__ == "__main__":
    main()
