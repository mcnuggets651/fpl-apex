#!/usr/bin/env python3
"""Generate the enhanced Apex Pinnacle decision snapshot.

This runner deliberately sits on top of the normal validated Apex data pipeline:
all source checks, official identity, projections and personalised team-state logic
are reused. The difference is the decision layer: the initial squad is solved over
all Gameweeks in the horizon and then subjected to exact force/ban regret analysis.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
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


def _legacy_overlap(legacy, horizon) -> dict:
    legacy_ids = set(pd.to_numeric(legacy.squad.get("player_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    horizon_ids = set(pd.to_numeric(horizon.squad.get("player_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    legacy_xi = set(pd.to_numeric(legacy.xi.get("player_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    horizon_xi = set(pd.to_numeric(horizon.xi.get("player_id", pd.Series(dtype=float)), errors="coerce").dropna().astype(int))
    return {
        "squad_overlap": len(legacy_ids & horizon_ids),
        "squad_changed": sorted(legacy_ids ^ horizon_ids),
        "xi_overlap": len(legacy_xi & horizon_xi),
        "legacy_objective": legacy.objective,
        "horizon_objective": horizon.objective,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--alternatives", type=int, default=12)
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

    scenarios = {
        "unrestricted": optimise_initial_horizon(**common),
    }
    haaland = players[players["web_name"].astype(str).str.casefold().eq("haaland")]
    if not haaland.empty:
        haaland_id = int(haaland.iloc[0]["player_id"])
        scenarios["haaland"] = optimise_initial_horizon(**common, locked={haaland_id})
        scenarios["no-haaland"] = optimise_initial_horizon(**common, banned={haaland_id})

    bad = [name for name, sol in scenarios.items() if sol.status != "Optimal"]
    if bad:
        raise SystemExit("Pinnacle horizon optimiser failed scenarios: " + ", ".join(bad))

    baseline = scenarios["unrestricted"]
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
        name: _legacy_overlap(out.scenarios[name], sol)
        for name, sol in scenarios.items()
        if name in out.scenarios
    }

    report_dir = Path(args.report_dir)
    output_dir = Path(args.output_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    regret.to_csv(report_dir / "pinnacle_selection_regret.csv", index=False)

    personal_team = None
    team_state_file = report_dir / "team_state.json"
    if team_state_file.exists():
        try:
            personal_team = json.loads(team_state_file.read_text(encoding="utf-8"))
        except Exception:
            personal_team = None

    payload = {
        "contract": "apex-pinnacle-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fpl_entry_id": settings.fpl_entry_id,
        "gameweeks": gws,
        "safe_to_act": True,
        "full_apex_ready": True,
        "decision_layer": {
            "initial_squad": "full-horizon legal MILP with per-GW XI/captain",
            "sensitivity": "exact force/ban objective regret",
            "stochastic_covariance_layer": False,
            "note": "deterministic horizon optimum is the baseline; covariance/CVaR is the next pinnacle layer",
        },
        "official_snapshot": out.snapshot,
        "sources": [s.to_dict() for s in out.sources],
        "personal_team": personal_team,
        "scenarios": {name: _solution(sol) for name, sol in scenarios.items()},
        "legacy_comparison": legacy_compare,
        "selection_regret": _records(regret),
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
    output_json.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")

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
        "- initial solver: full-horizon MILP",
        "- sensitivity: exact force/ban regret",
        "- stochastic covariance/CVaR layer: pending",
        "",
    ]
    for name, sol in scenarios.items():
        cap = sol.captain.iloc[0].get("web_name", "-") if not sol.captain.empty else "-"
        vice = sol.vice_captain.iloc[0].get("web_name", "-") if not sol.vice_captain.empty else "-"
        lines += [
            f"## {name}",
            "",
            f"Objective: **{sol.objective:.2f}**",
            f"Captain: **{cap}**",
            f"Vice-captain: **{vice}**",
            "",
            sol.squad.to_markdown(index=False),
            "",
        ]
    if not regret.empty:
        lines += ["## Selection-regret stress test", "", regret.to_markdown(index=False), ""]
    output_md.write_text("\n".join(lines), encoding="utf-8")
    print(f"Pinnacle snapshot written to {output_json}")


if __name__ == "__main__":
    main()
