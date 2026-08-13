#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.optimisation.exact_decision import optimise_exact_horizon_decision
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.pipeline import run_pipeline
from shrinkage_shadow_parity import load_projection_evidence_players, parity_shadow


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


def build_gaps(shadow: pd.DataFrame, audit: pd.DataFrame, gameweeks: list[int], decay: float) -> pd.DataFrame:
    discounts = {int(gw): float(decay) ** i for i, gw in enumerate(gameweeks)}
    frame = shadow.copy()
    frame["discount"] = frame["gw"].map(discounts).fillna(0.0)
    effective = pd.to_numeric(frame["effective_weight_apex_model"], errors="coerce").fillna(0.0)
    production_blended = pd.to_numeric(frame["xp"], errors="coerce").fillna(0.0)
    raw_blended = pd.to_numeric(frame["raw_counterfactual_blended_xp_v1"], errors="coerce").fillna(0.0)
    production_apex = pd.to_numeric(frame["apex_xp"], errors="coerce").fillna(0.0)
    raw_apex = production_apex + (raw_blended - production_blended) / effective.where(effective > 0, 1.0)
    frame["raw_h"] = raw_apex * frame["discount"]
    frame["shrunk_h"] = production_apex * frame["discount"]
    frame["air_h"] = pd.to_numeric(frame.get("airsenal_xp"), errors="coerce").fillna(0.0) * frame["discount"]
    gaps = frame.groupby("player_id", as_index=False).agg(
        raw_apex=("raw_h", "sum"),
        shrunk_apex=("shrunk_h", "sum"),
        airsenal=("air_h", "sum"),
    )
    gaps = gaps.merge(audit, on="player_id", how="left")
    gaps["raw_gap"] = (gaps["raw_apex"] - gaps["airsenal"]).abs()
    gaps["shrunk_gap"] = (gaps["shrunk_apex"] - gaps["airsenal"]).abs()
    return gaps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output-dir", default="reports/shrinkage_promotion")
    args = parser.parse_args()

    settings = load_settings()
    pipeline = run_pipeline(settings, horizon=args.horizon, scenario="both", force=args.force, plan_transfers=False)
    projection_players = load_projection_evidence_players(settings)
    audit, shadow = parity_shadow(pipeline.projections, projection_players)

    previous_coverage = float((pd.to_numeric(audit["previous_minutes"], errors="coerce").fillna(0.0) > 0).mean())
    evidence_coverage = float((pd.to_numeric(audit["evidence_minutes"], errors="coerce").fillna(0.0) > 0).mean())
    if previous_coverage < 0.35 or evidence_coverage < 0.35:
        raise RuntimeError(
            f"shrinkage evidence coverage invalid: previous={previous_coverage:.1%}, evidence={evidence_coverage:.1%}"
        )

    xg_zero = pd.to_numeric(audit["xg90_evidence_minutes"], errors="coerce").fillna(0.0).le(0.0)
    xa_zero = pd.to_numeric(audit["xa90_evidence_minutes"], errors="coerce").fillna(0.0).le(0.0)
    xg_changed = (
        pd.to_numeric(audit["shrunk_model_xg90"], errors="coerce").fillna(0.0)
        - pd.to_numeric(audit["raw_model_xg90"], errors="coerce").fillna(0.0)
    ).abs().gt(1e-12)
    xa_changed = (
        pd.to_numeric(audit["shrunk_model_xa90"], errors="coerce").fillna(0.0)
        - pd.to_numeric(audit["raw_model_xa90"], errors="coerce").fillna(0.0)
    ).abs().gt(1e-12)
    prior_only_injected = (xg_zero & xg_changed) | (xa_zero & xa_changed)
    prior_only_injected_count = int(prior_only_injected.sum())
    if prior_only_injected_count:
        raise RuntimeError(
            f"prior-only attacking rates leaked into activated production for {prior_only_injected_count} players"
        )

    decision_players, eligibility = evidence_eligibility(pipeline.players, pipeline.news_audit)
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
        xi_eligible=set(decision_players.loc[decision_players["xi_evidence_eligible"], "player_id"].astype(int)),
    )
    raw = optimise_exact_horizon_decision(
        projections=shadow,
        projection_col="raw_counterfactual_blended_xp_v1",
        **common,
    )
    shrunk = optimise_exact_horizon_decision(projections=shadow, projection_col="xp", **common)

    gaps = build_gaps(shadow, audit, pipeline.gameweeks, settings.fixture_decay)
    low = gaps[(gaps["evidence_minutes"] > 0.0) & (gaps["evidence_minutes"] < 270.0)]
    prior_only = gaps[gaps["evidence_minutes"] <= 0.0]
    high = gaps[gaps["raw_gap"] >= 3.0]
    historical = json.loads(Path("docs/evidence/shrinkage_validation_v2_summary.json").read_text())
    history_ok = bool(historical.get("attack_rate_shadow_gate_pass", False))
    independent = bool(historical.get("independent_final_holdout", False))
    low_ok = bool(not low.empty and low["shrunk_gap"].mean() < low["raw_gap"].mean())
    high_ok = bool(not high.empty and high["shrunk_gap"].mean() < high["raw_gap"].mean())
    prior_safety_ok = prior_only_injected_count == 0
    candidate = bool(history_ok and low_ok and high_ok and prior_safety_ok and shrunk.status == "Optimal")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    audit.to_csv(output_dir / "player_shrinkage_audit.csv", index=False)
    gaps.to_csv(output_dir / "live_gap_audit.csv", index=False)
    raw_payload = decision_payload(raw)
    shrunk_payload = decision_payload(shrunk)
    report = {
        "contract": "apex-shrinkage-activated-audit-v4",
        "diagnostic_only": True,
        "production_input_parity_required": True,
        "live_change": "activated_evidence_qualified_competitive_xg_xa_shrinkage_then_identical_preseason_blend; raw_counterfactual_holds_bonus_constant",
        "previous_evidence_coverage": previous_coverage,
        "competitive_evidence_coverage": evidence_coverage,
        "promotion_candidate": candidate,
        "holdout_independent": independent,
        "eligible_for_live_use": bool(candidate and independent),
        "history_gate_pass": history_ok,
        "prior_safety_gate_pass": prior_safety_ok,
        "zero_evidence_xg_count": int(xg_zero.sum()),
        "zero_evidence_xa_count": int(xa_zero.sum()),
        "prior_only_injected_count": prior_only_injected_count,
        "prior_only_player_count": int(len(prior_only)),
        "raw_decision": raw_payload,
        "shrunk_decision": shrunk_payload,
        "squad_overlap": len(set(raw_payload.get("squad_ids", [])) & set(shrunk_payload.get("squad_ids", []))),
        "low_sample_count": int(len(low)),
        "low_sample_mean_gap_raw": float(low["raw_gap"].mean()) if not low.empty else None,
        "low_sample_mean_gap_shrunk": float(low["shrunk_gap"].mean()) if not low.empty else None,
        "high_gap_count": int(len(high)),
        "high_gap_mean_raw": float(high["raw_gap"].mean()) if not high.empty else None,
        "high_gap_mean_shrunk": float(high["shrunk_gap"].mean()) if not high.empty else None,
        "named_diagnostics": gaps[gaps["web_name"].astype(str).str.casefold().isin({"dowman", "welbeck"})].to_dict("records"),
        "eligibility_contract": eligibility,
        "notes": [
            "Activated production xG/xA must equal the independently reconstructed evidence-qualified posterior to numerical tolerance.",
            "The raw A/B arm is a reconstructed counterfactual; production itself is never shrunk a second time.",
            "Zero-evidence metrics preserve the raw rate; a cohort prior alone cannot change live xP.",
            "Low-but-nonzero competitive evidence receives empirical-Bayes shrinkage.",
            "Fixtures, minutes, availability, set pieces, DEFCON, prices, source weights and exact mechanics are unchanged.",
            "The raw counterfactual holds bonus constant so the direct attacking-return effect remains isolated.",
            "AIrsenal gap reduction is diagnostic only and is not an optimisation target.",
            "Independent final holdout remains reported separately from preseason-provisional activation policy.",
        ],
    }
    (output_dir / "shrinkage_promotion_gate.json").write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(output_dir / "shrinkage_promotion_gate.json")


if __name__ == "__main__":
    main()
