#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.joint_initial_path import optimise_joint_initial_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--output", default="reports/joint_initial_path.json")
    parser.add_argument("--per-view-candidates", type=int, default=2, help="deprecated compatibility flag")
    parser.add_argument("--transfer-candidate-limit", type=int, default=180)
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out = bundle.to_pipeline_output()
    settings = bundle.settings
    players, eligibility = evidence_eligibility(out.players, out.news_audit)
    captain_eligible = captain_eligible_ids(players)
    xi_eligible = set(
        players.loc[players["xi_evidence_eligible"], "player_id"].astype(int)
    )
    tolerance = float(settings.get("exact_near_equivalent_points", 0.25))

    result = optimise_joint_initial_path(
        players,
        out.projections,
        out.gameweeks,
        budget=float(settings["budget"]),
        max_per_team=int(settings["max_per_team"]),
        decay=float(settings["fixture_decay"]),
        projection_col="xp",
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        transfer_candidate_limit=args.transfer_candidate_limit,
        exact_candidate_limit=int(settings.get("exact_candidate_limit", 16)),
        gw1_regret_tolerance=tolerance,
    )

    selected = result.selected
    floor_ok = bool(selected is not None and selected.within_gw1_band)
    payload = result.to_dict()
    payload.update(
        {
            "contract": "apex-adaptive-launch-audit-v2",
            "diagnostic_only": True,
            "decision_bundle_id": bundle.bundle_id,
            "gameweeks": [int(gw) for gw in out.gameweeks],
            "eligibility_contract": eligibility,
            "promotion_gate": {
                "gw1_first_optimal": result.status == "optimal",
                "candidate_pool_stable": bool(result.candidate_pool_stable),
                "gw1_floor_respected": floor_ok,
                "promotion_candidate": bool(
                    result.status == "optimal"
                    and result.candidate_pool_stable
                    and floor_ok
                ),
            },
            "notes": [
                "Exact GW1 expected points are the primary launch objective.",
                "The existing near-equivalent point threshold is a hard GW1 floor, not a multi-week weight.",
                "Only launch-equivalent squads are ranked by the legal future transfer planner.",
                "The transfer planner models cash, rolled free transfers and explicit hit costs.",
                "Future moves are contingencies only and must be re-solved from fresh projections before each deadline.",
                "Current official prices are held fixed inside the diagnostic; speculative price rises are not forecast.",
            ],
        }
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(output)

    if result.status != "optimal":
        raise SystemExit("adaptive GW1 launch policy did not solve optimally")


if __name__ == "__main__":
    main()
