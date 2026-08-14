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
    parser.add_argument("--per-view-candidates", type=int, default=2)
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
        per_view_candidates=args.per_view_candidates,
        transfer_candidate_limit=args.transfer_candidate_limit,
        exact_candidate_limit=int(settings.get("exact_candidate_limit", 16)),
    )

    payload = result.to_dict()
    payload.update(
        {
            "contract": "apex-joint-initial-path-audit-v1",
            "diagnostic_only": True,
            "decision_bundle_id": bundle.bundle_id,
            "gameweeks": [int(gw) for gw in out.gameweeks],
            "eligibility_contract": eligibility,
            "promotion_gate": {
                "joint_path_optimal": result.status == "optimal",
                "candidate_pool_stable": bool(result.candidate_pool_stable),
                "positive_gain_vs_static": bool(
                    result.gain_vs_baseline is not None and result.gain_vs_baseline > 0.0
                ),
                "material_gain_vs_static": bool(
                    result.gain_vs_baseline is not None and result.gain_vs_baseline >= 0.25
                ),
                "promotion_candidate": bool(
                    result.status == "optimal"
                    and result.candidate_pool_stable
                    and result.gain_vs_baseline is not None
                    and result.gain_vs_baseline >= 0.25
                ),
            },
            "notes": [
                "The static and joint-path starting squads are compared on the same pathway objective.",
                "GW1 uses exact XI/captain/vice/autosub mechanics; GW2-GW8 use the existing transfer MILP.",
                "The transfer MILP models cash, current selling prices, rolled free transfers and explicit -4 hit costs.",
                "Future moves are contingent plans only and must be re-solved before each deadline.",
                "Current market prices are held fixed across the planning horizon; speculative price rises are not forecast.",
                "This audit cannot change the canonical squad by itself.",
            ],
        }
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    print(output)

    if result.status != "optimal":
        raise SystemExit("joint initial-path challenger did not solve optimally")


if __name__ == "__main__":
    main()
