#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apex_fpl.config import load_settings
from apex_fpl.optimisation.exact_decision import optimise_exact_horizon_decision
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.pipeline import run_pipeline
from shrinkage_shadow_surface import build_shadow, horizon_gaps


def decision_payload(decision):
    if decision.status != "Optimal":
        return {"status": decision.status}
    names = {
        int(row.player_id): str(row.web_name)
        for row in decision.solution.squad[["player_id", "web_name"]].itertuples(index=False)
    }
    return {
        "status": decision.status,
        "objective": float(decision.objective),
        "squad_ids": sorted(names),
        "squad_names": [names[x] for x in sorted(names)],
        "weeks": [
            {
                "gw": int(week.gw),
                "xi_ids": [int(x) for x in week.xi_ids],
                "captain_id": int(week.mechanics.captain_id),
                "vice_captain_id": int(week.mechanics.vice_captain_id),
            }
            for week in decision.weeks
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default="reports/shrinkage_promotion")
    args = parser.parse_args()

    settings = load_settings()
    pipeline = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=False,
    )
    players, audit, shadow = build_shadow(pipeline.projections, pipeline.players)
    decision_players, eligibility = evidence_eligibility(players, pipeline.news_audit)
    common = dict(
        players=decision_players,
        gameweeks=pipeline.gameweeks,
        budget=float(settings.budget),
        max_per_team=int(settings.max_per_team),
        decay=float(settings.fixture_decay),
        shortlist_bench_weight=float(settings.approximate_bench_weight),
        candidate_limit=int(settings.exact_candidate_limit),
        candidate_regret_fraction=float(settings.exact_candidate_regret_fraction),
        near_equivalent_points=float(settings.exact_near_equivalent_points),
        captain_eligible=captain_eligible_ids(decision_players),
        xi_eligible=set(
            decision_players.loc[
                decision_players["xi_evidence_eligible"], "player_id"
            ].astype(int)
        ),
    )
    raw = optimise_exact_horizon_decision(
        projections=shadow,
        projection_col="xp",
        **common,
    )
    shrunk = optimise_exact_horizon_decision(
        projections=shadow,
        projection_col="shrunk_blended_xp",
        **common,
    )

    gaps = horizon_gaps(shadow, audit, pipeline.gameweeks, settings.fixture_decay)
    low = gaps[gaps["evidence_minutes"] < 270.0]
    high = gaps[gaps["raw_gap"] >= 3.0]
    historical = json.loads(
        Path("docs/evidence/shrinkage_validation_v2_summary.json").read_text()
    )
    history_ok = bool(historical.get("attack_rate_shadow_gate_pass", False))
    independent = bool(historical.get("independent_final_holdout", False))
    low_ok = bool(
        not low.empty and low["shrunk_gap"].mean() < low["raw_gap"].mean()
    )
    high_ok = bool(
        not high.empty and high["shrunk_gap"].mean() < high["raw_gap"].mean()
    )
    candidate = bool(
        history_ok and low_ok and high_ok and shrunk.status == "Optimal"
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output_dir / "player_shrinkage_audit.csv", index=False)
    gaps.to_csv(output_dir / "live_gap_audit.csv", index=False)
    raw_payload = decision_payload(raw)
    shrunk_payload = decision_payload(shrunk)
    report = {
        "contract": "apex-shrinkage-promotion-gate-v1",
        "diagnostic_only": True,
        "live_change": "xp_attack_only",
        "promotion_candidate": candidate,
        "holdout_independent": independent,
        "eligible_for_live_use": bool(candidate and independent),
        "history_gate_pass": history_ok,
        "raw_decision": raw_payload,
        "shrunk_decision": shrunk_payload,
        "squad_overlap": len(
            set(raw_payload.get("squad_ids", []))
            & set(shrunk_payload.get("squad_ids", []))
        ),
        "low_sample_count": int(len(low)),
        "low_sample_mean_gap_raw": float(low["raw_gap"].mean()) if not low.empty else None,
        "low_sample_mean_gap_shrunk": float(low["shrunk_gap"].mean()) if not low.empty else None,
        "high_gap_count": int(len(high)),
        "high_gap_mean_raw": float(high["raw_gap"].mean()) if not high.empty else None,
        "high_gap_mean_shrunk": float(high["shrunk_gap"].mean()) if not high.empty else None,
        "named_diagnostics": gaps[
            gaps["web_name"].astype(str).str.casefold().isin({"dowman", "welbeck"})
        ].to_dict("records"),
        "eligibility_contract": eligibility,
        "notes": [
            "Fixtures, minutes, availability, set pieces, DEFCON, prices, source weights and exact mechanics are unchanged.",
            "Bonus is held constant in the live A/B so the direct attacking-return effect is isolated.",
            "AIrsenal gap reduction is diagnostic only and is not an optimisation target.",
        ],
    }
    (output_dir / "shrinkage_promotion_gate.json").write_text(
        json.dumps(report, indent=2, default=str) + "\n"
    )
    print(output_dir / "shrinkage_promotion_gate.json")


if __name__ == "__main__":
    main()
