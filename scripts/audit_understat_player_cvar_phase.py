#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

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
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--surface", choices=("baseline", "challenger"), required=True)
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument(
        "--historical-audit",
        default="reports/understat_player_predictive_audit.json",
    )
    parser.add_argument("--output", required=True)
    parser.add_argument("--scenario-seed", type=int, default=20260807)
    parser.add_argument("--stochastic-scenarios", type=int, default=256)
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

    decision_players, _ = evidence_eligibility(out.players, out.news_audit)
    captain_eligible = captain_eligible_ids(decision_players)
    xi_eligible = set(
        decision_players.loc[
            decision_players["xi_evidence_eligible"], "player_id"
        ].astype(int)
    )
    if len(captain_eligible) < 2:
        raise SystemExit("fewer than two captain-eligible players on sealed bundle")

    projections = out.projections.copy()
    if args.surface == "challenger":
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
        projections, _ = reprice_projection_surface(
            decision_players,
            projections,
            understat_rates,
            dict(settings["weights"]),
            float(settings["risk_penalty"]),
            xg_weight=xg_weight,
            xa_weight=xa_weight,
        )

    gameweeks = [int(gw) for gw in out.gameweeks]
    scenarios = generate_projection_scenarios(
        decision_players,
        projections,
        gameweeks,
        n_scenarios=args.stochastic_scenarios,
        seed=args.scenario_seed,
    )
    robust = optimise_initial_cvar(
        players=decision_players,
        scenarios=scenarios,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=float(settings["fixture_decay"]),
        bench_weight=float(settings["approximate_bench_weight"]),
        cvar_alpha=0.10,
        cvar_weight=0.20,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    if robust.status != "Optimal":
        raise SystemExit(f"{args.surface} CVaR solve failed: {robust.status}")

    payload = {
        "contract": "apex-understat-player-cvar-phase-v1",
        "decision_bundle_id": bundle.bundle_id,
        "official_snapshot": bundle.manifest.get("official_snapshot"),
        "surface": args.surface,
        "scenario_seed": int(args.scenario_seed),
        "scenario_count": int(args.stochastic_scenarios),
        "xg_understat_weight": xg_weight,
        "xa_understat_weight": xa_weight,
        "status": robust.status,
        "objective": float(robust.objective),
        "mean_points": float(robust.mean_points),
        "lower_tail_cvar": float(robust.lower_tail_cvar),
        "squad_ids": sorted(robust.squad["player_id"].astype(int).tolist()),
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
