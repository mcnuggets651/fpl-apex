#!/usr/bin/env python3
"""Generate the enhanced Apex Pinnacle decision snapshot.

The normal Apex pipeline remains the source/data integrity gate. This runner adds
three independent decision views on the exact same current evidence:

1. the legacy production MILP for backwards comparison;
2. a true multi-Gameweek deterministic initial-squad MILP;
3. a covariance-aware scenario/CVaR MILP for downside robustness.

A decision is strongest when the deterministic horizon and CVaR solutions agree;
when they diverge the output exposes the trade-off instead of hiding uncertainty.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.models.scenarios import generate_projection_scenarios
from apex_fpl.optimisation.cvar import optimise_initial_cvar
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.stability import selection_regret_analysis
from apex_fpl.services.pipeline import run_pipeline


def _records(df: pd.DataFrame) -> list[dict]:
    if df.empty:
        return []
    return json.loads(df.to_json(orient="records"))


def _solution(sol) -> dict:
    return {
        "status": sol.status,
        "objective": sol.objective,
        "squad": _records(sol.squad),
        "xi": _records(sol.xi),
        "captain": _records(sol.captain),
        "vice_captain": _records(sol.vice_captain),
        "bench": _records(sol.bench),
    }


def _robust_solution(sol) -> dict:
    score = sol.scenario_scores
    return {
        "status": sol.status,
        "objective": sol.objective,
        "mean_points": sol.mean_points,
        "lower_tail_cvar": sol.lower_tail_cvar,
        "cvar_alpha": sol.cvar_alpha,
        "cvar_weight": sol.cvar_weight,
        "scenario_p10": float(np.quantile(score, 0.10)) if len(score) else None,
        "scenario_p50": float(np.quantile(score, 0.50)) if len(score) else None,
        "scenario_p90": float(np.quantile(score, 0.90)) if len(score) else None,
        "squad": _records(sol.squad),
        "xi": _records(sol.xi),
        "captain": _records(sol.captain),
        "vice_captain": _records(sol.vice_captain),
        "bench": _records(sol.bench),
    }


def _ids(frame: pd.DataFrame) -> set[int]:
    if frame.empty or "player_id" not in frame.columns:
        return set()
    return set(pd.to_numeric(frame["player_id"], errors="coerce").dropna().astype(int))


def _comparison(left, right) -> dict:
    left_squad, right_squad = _ids(left.squad), _ids(right.squad)
    left_xi, right_xi = _ids(left.xi), _ids(right.xi)
    left_cap, right_cap = _ids(left.captain), _ids(right.captain)
    return {
        "squad_overlap": len(left_squad & right_squad),
        "squad_changed": sorted(left_squad ^ right_squad),
        "xi_overlap": len(left_xi & right_xi),
        "captain_agrees": bool(left_cap and left_cap == right_cap),
        "left_objective": float(left.objective),
        "right_objective": float(right.objective),
    }


def _scenario_player_summary(players, scenario_surface, decay: float) -> pd.DataFrame:
    discounts = np.asarray(
        [float(decay) ** t for t in range(len(scenario_surface.gameweeks))],
        dtype=float,
    )
    horizon = np.sum(scenario_surface.values * discounts[None, None, :], axis=2)
    summary = pd.DataFrame(
        {
            "player_id": scenario_surface.player_ids.astype(int),
            "scenario_horizon_mean": np.mean(horizon, axis=0),
            "scenario_horizon_sd": np.std(horizon, axis=0, ddof=0),
            "scenario_horizon_p10": np.quantile(horizon, 0.10, axis=0),
            "scenario_horizon_p50": np.quantile(horizon, 0.50, axis=0),
            "scenario_horizon_p90": np.quantile(horizon, 0.90, axis=0),
        }
    )
    keep = [
        col
        for col in ["player_id", "web_name", "team_name", "position", "price"]
        if col in players.columns
    ]
    return summary.merge(players[keep], on="player_id", how="left").sort_values(
        "scenario_horizon_mean", ascending=False
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--alternatives", type=int, default=12)
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
    parser.add_argument("--scenario-seed", type=int, default=20260807)
    parser.add_argument("--cvar-alpha", type=float, default=0.10)
    parser.add_argument("--cvar-weight", type=float, default=0.20)
    parser.add_argument("--report-dir", default="reports")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    settings = load_settings()
    out = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=True,
    )
    if not out.safety.safe_to_act or not out.safety.full_apex_ready:
        blockers = "; ".join(out.safety.blockers) or "unknown production blocker"
        raise SystemExit(f"Pinnacle runner blocked by Apex production gate: {blockers}")

    gws = out.gameweeks
    players = out.players
    projections = out.projections
    common = dict(
        players=players,
        projections=projections,
        gameweeks=gws,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
    )

    deterministic = {"unrestricted": optimise_initial_horizon(**common)}
    haaland = players[players["web_name"].astype(str).str.casefold().eq("haaland")]
    haaland_id = int(haaland.iloc[0]["player_id"]) if not haaland.empty else None
    if haaland_id is not None:
        deterministic["haaland"] = optimise_initial_horizon(
            **common, locked={haaland_id}
        )
        deterministic["no-haaland"] = optimise_initial_horizon(
            **common, banned={haaland_id}
        )

    bad = [name for name, sol in deterministic.items() if sol.status != "Optimal"]
    if bad:
        raise SystemExit(
            "Pinnacle horizon optimiser failed scenarios: " + ", ".join(bad)
        )

    # PipelineOutput intentionally publishes only decision columns. Rejoin the
    # official team ID from the same cached official snapshot for covariance links.
    official = OfficialFPLClient(CachedHttp(settings.cache_dir)).snapshot(force=False)
    team_ids = official.players[["player_id", "team"]].drop_duplicates("player_id")
    scenario_players = players.drop(columns=["team"], errors="ignore").merge(
        team_ids, on="player_id", how="left", validate="one_to_one"
    )
    scenario_surface = generate_projection_scenarios(
        scenario_players,
        projections,
        gws,
        n_scenarios=args.stochastic_scenarios,
        seed=args.scenario_seed,
    )

    robust_common = dict(
        players=scenario_players,
        scenarios=scenario_surface,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        cvar_alpha=args.cvar_alpha,
        cvar_weight=args.cvar_weight,
    )
    robust = {"unrestricted": optimise_initial_cvar(**robust_common)}
    if haaland_id is not None:
        robust["haaland"] = optimise_initial_cvar(
            **robust_common, locked={haaland_id}
        )
        robust["no-haaland"] = optimise_initial_cvar(
            **robust_common, banned={haaland_id}
        )
    bad_robust = [name for name, sol in robust.items() if sol.status != "Optimal"]
    if bad_robust:
        raise SystemExit("Pinnacle CVaR optimiser failed: " + ", ".join(bad_robust))

    baseline = deterministic["unrestricted"]
    regret = selection_regret_analysis(
        players,
        projections,
        gws,
        baseline,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        alternative_limit=args.alternatives,
    )

    legacy_compare = {
        name: _comparison(out.scenarios[name], sol)
        for name, sol in deterministic.items()
        if name in out.scenarios
    }
    robust_compare = {
        name: _comparison(deterministic[name], sol)
        for name, sol in robust.items()
        if name in deterministic
    }

    report_dir = Path(args.report_dir)
    output_dir = Path(args.output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    regret.to_csv(report_dir / "pinnacle_selection_regret.csv", index=False)
    scenario_summary = _scenario_player_summary(
        players, scenario_surface, settings.fixture_decay
    )
    scenario_summary.to_csv(
        report_dir / "pinnacle_scenario_player_summary.csv", index=False
    )

    personal_team = None
    team_state_file = report_dir / "team_state.json"
    if team_state_file.exists():
        try:
            personal_team = json.loads(team_state_file.read_text(encoding="utf-8"))
        except Exception:
            personal_team = None

    payload = {
        "contract": "apex-pinnacle-v2-cvar",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fpl_entry_id": settings.fpl_entry_id,
        "gameweeks": gws,
        "safe_to_act": True,
        "full_apex_ready": True,
        "decision_layer": {
            "deterministic_initial_squad": (
                "full-horizon legal MILP with per-GW XI/captain"
            ),
            "stochastic_covariance_layer": True,
            "stochastic_model": scenario_surface.model_version,
            "stochastic_scenarios": scenario_surface.n_scenarios,
            "scenario_seed": scenario_surface.seed,
            "cvar_alpha": args.cvar_alpha,
            "cvar_weight": args.cvar_weight,
            "covariance_coefficients_walk_forward_calibrated": False,
            "sensitivity": "exact force/ban objective regret",
            "decision_rule": (
                "use deterministic expected-value optimum as baseline; use CVaR "
                "solution and overlap/regret as robustness evidence"
            ),
        },
        "official_snapshot": out.snapshot,
        "sources": [s.to_dict() for s in out.sources],
        "personal_team": personal_team,
        "deterministic_scenarios": {
            name: _solution(sol) for name, sol in deterministic.items()
        },
        "robust_cvar_scenarios": {
            name: _robust_solution(sol) for name, sol in robust.items()
        },
        "legacy_comparison": legacy_compare,
        "robustness_comparison": robust_compare,
        "selection_regret": _records(regret),
        "scenario_player_summary": _records(scenario_summary.head(150)),
        "transfer_plan": (
            {
                "status": out.transfer_plan.status,
                "objective": out.transfer_plan.objective,
                "weeks": out.transfer_plan.weeks,
            }
            if out.transfer_plan is not None
            else None
        ),
    }

    output_json = output_dir / "pinnacle_latest.json"
    output_md = output_dir / "pinnacle_latest.md"
    output_json.write_text(
        json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
    )

    lines = [
        "# Apex Pinnacle decision",
        "",
        f"Generated: {payload['generated_at']}",
        f"Gameweeks: {', '.join(map(str, gws))}",
        "",
        "## Decision gate",
        "",
        "- safe_to_act: `true`",
        "- full_apex_ready: `true`",
        "- deterministic initial solver: full-horizon MILP",
        f"- covariance-aware scenarios: {scenario_surface.n_scenarios}",
        f"- lower-tail CVaR alpha: {args.cvar_alpha:.0%}",
        f"- CVaR objective weight: {args.cvar_weight:.0%}",
        "- covariance priors walk-forward calibrated: `false`",
        "- sensitivity: exact force/ban objective regret",
        "",
    ]
    for name, sol in deterministic.items():
        cap = (
            sol.captain.iloc[0].get("web_name", "-")
            if not sol.captain.empty
            else "-"
        )
        vice = (
            sol.vice_captain.iloc[0].get("web_name", "-")
            if not sol.vice_captain.empty
            else "-"
        )
        lines += [
            f"## Deterministic {name}",
            "",
            f"Objective: **{sol.objective:.2f}**",
            f"Captain: **{cap}**",
            f"Vice-captain: **{vice}**",
            "",
            sol.squad.to_markdown(index=False),
            "",
        ]
    for name, sol in robust.items():
        lines += [
            f"## Robust CVaR {name}",
            "",
            f"Blended objective: **{sol.objective:.2f}**",
            f"Scenario mean: **{sol.mean_points:.2f}**",
            f"Lower-tail CVaR: **{sol.lower_tail_cvar:.2f}**",
            f"Deterministic/robust squad overlap: **{robust_compare[name]['squad_overlap']}/15**",
            "",
            sol.squad.to_markdown(index=False),
            "",
        ]
    if not regret.empty:
        lines += [
            "## Selection-regret stress test",
            "",
            regret.to_markdown(index=False),
            "",
        ]
    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Pinnacle snapshot written to {output_json}")


if __name__ == "__main__":
    main()
