#!/usr/bin/env python3
"""Compare legacy safety gating with the EV-first policy on one sealed surface.

This is a diagnostic only. Both policies consume the same immutable player,
projection and evidence surface. Production publication readiness is recorded but
is not allowed to masquerade as an optimiser-policy failure.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.optimisation.exact_decision import optimise_exact_horizon_decision
from apex_fpl.services.audit_contracts import assess_diagnostic_surface
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import (
    captain_eligible_ids,
    evidence_eligibility,
)
from apex_fpl.services.pipeline import run_pipeline


LEGACY_MINUTES_CONFIDENCE = 0.75
LEGACY_ROLE_CONFIDENCE = 0.65
LEGACY_CAPTAIN_EXPECTED_MINUTES = 60.0
LEGACY_CAPTAIN_START_PROBABILITY = 0.50
LEGACY_CAPTAIN_APPEARANCE_PROBABILITY = 0.75
LEGACY_CAPTAIN_PROJECTION_CONFIDENCE = 0.40


def _num(frame: pd.DataFrame, column: str, default: float = 0.0) -> pd.Series:
    if column not in frame:
        return pd.Series(default, index=frame.index, dtype=float)
    return pd.to_numeric(frame[column], errors="coerce").fillna(default)


def _ids(frame: pd.DataFrame) -> set[int]:
    return set(pd.to_numeric(frame["player_id"], errors="coerce").dropna().astype(int))


def _decision_payload(decision, players: pd.DataFrame) -> dict:
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }
    first_week = decision.weeks[0]
    return {
        "status": decision.status,
        "objective": float(decision.objective),
        "squad_ids": sorted(_ids(decision.solution.squad)),
        "squad_names": [names[pid] for pid in sorted(_ids(decision.solution.squad))],
        "first_gw": int(first_week.gw),
        "first_gw_xi_ids": sorted(int(pid) for pid in first_week.xi_ids),
        "first_gw_xi_names": [names[int(pid)] for pid in sorted(first_week.xi_ids)],
        "first_gw_captain_id": int(first_week.mechanics.captain_id),
        "first_gw_captain_name": names[int(first_week.mechanics.captain_id)],
        "first_gw_vice_captain_id": int(first_week.mechanics.vice_captain_id),
        "first_gw_vice_captain_name": names[int(first_week.mechanics.vice_captain_id)],
        "first_gw_expected_total_points": float(first_week.mechanics.expected_total_points),
        "near_equivalent_candidate_count": len(decision.near_equivalent_candidates),
    }


def _solve(players, projections, gws, settings, *, captain_eligible, xi_eligible):
    return optimise_exact_horizon_decision(
        players,
        projections,
        gws,
        budget=settings.budget,
        max_per_team=settings.max_per_team,
        decay=settings.fixture_decay,
        shortlist_bench_weight=settings.approximate_bench_weight,
        candidate_limit=settings.exact_candidate_limit,
        candidate_regret_fraction=settings.exact_candidate_regret_fraction,
        near_equivalent_points=settings.exact_near_equivalent_points,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        projection_col="xp",
    )


def _load_surface(settings, args):
    if args.bundle_dir:
        bundle = DecisionBundle.load(args.bundle_dir)
        output = bundle.to_pipeline_output()
        return output, {
            "mode": "sealed_decision_bundle",
            "bundle_id": bundle.bundle_id,
            "bundle_created_at": bundle.created_at,
        }
    output = run_pipeline(
        settings,
        horizon=args.horizon,
        scenario="both",
        force=args.force,
        plan_transfers=False,
    )
    return output, {"mode": "live_pipeline", "bundle_id": None}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--horizon", type=int, default=8)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--bundle-dir", default="")
    parser.add_argument("--output", default="reports/max_ev_policy_audit.json")
    args = parser.parse_args()

    settings = load_settings()
    out, surface = _load_surface(settings, args)
    readiness = assess_diagnostic_surface(out, projection_col="xp")
    if not readiness.ready:
        raise SystemExit(
            "max-EV diagnostic surface invalid: " + "; ".join(readiness.blockers)
        )

    players, eligibility = evidence_eligibility(out.players, out.news_audit)
    confidence = (
        out.projections.groupby("player_id")["projection_confidence"].mean()
        if "projection_confidence" in out.projections
        else pd.Series(dtype=float)
    )
    if "projection_confidence" not in players:
        players["projection_confidence"] = players["player_id"].map(confidence)

    new_xi = set(
        players.loc[players["xi_evidence_eligible"].fillna(False), "player_id"].astype(int)
    )
    new_captain = captain_eligible_ids(players)

    confident = (
        _num(players, "minutes_confidence") >= LEGACY_MINUTES_CONFIDENCE
    ) & (_num(players, "role_confidence") >= LEGACY_ROLE_CONFIDENCE)
    supported_uncertainty = players["evidence_state"].astype(str).eq("uncertain_supported")
    legacy_xi_mask = (
        players["xi_evidence_eligible"].fillna(False).astype(bool)
        & (confident | supported_uncertainty)
    )
    legacy_xi = set(players.loc[legacy_xi_mask, "player_id"].astype(int))
    legacy_captain_mask = legacy_xi_mask.copy()
    legacy_captain_mask &= _num(players, "expected_minutes") >= LEGACY_CAPTAIN_EXPECTED_MINUTES
    legacy_captain_mask &= _num(players, "start_probability") >= LEGACY_CAPTAIN_START_PROBABILITY
    legacy_captain_mask &= (
        _num(players, "appearance_probability") >= LEGACY_CAPTAIN_APPEARANCE_PROBABILITY
    )
    legacy_captain_mask &= (
        _num(players, "projection_confidence") >= LEGACY_CAPTAIN_PROJECTION_CONFIDENCE
    )
    legacy_captain = set(players.loc[legacy_captain_mask, "player_id"].astype(int))

    legacy = _solve(
        players,
        out.projections,
        out.gameweeks,
        settings,
        captain_eligible=legacy_captain,
        xi_eligible=legacy_xi,
    )
    ev_first = _solve(
        players,
        out.projections,
        out.gameweeks,
        settings,
        captain_eligible=new_captain,
        xi_eligible=new_xi,
    )
    if legacy.status != "Optimal" or ev_first.status != "Optimal":
        raise SystemExit(
            f"policy audit solve failed: legacy={legacy.status}, ev_first={ev_first.status}"
        )

    old = _decision_payload(legacy, players)
    new = _decision_payload(ev_first, players)
    old_squad, new_squad = set(old["squad_ids"]), set(new["squad_ids"])
    old_xi, new_xi_ids = set(old["first_gw_xi_ids"]), set(new["first_gw_xi_ids"])
    names = {
        int(row.player_id): str(row.web_name)
        for row in players[["player_id", "web_name"]]
        .drop_duplicates("player_id")
        .itertuples(index=False)
    }
    report = {
        "contract": "apex-max-ev-policy-audit-v2",
        "production_changed": False,
        "canonical_publish_attempted": False,
        "surface": surface,
        "diagnostic_readiness": readiness.to_dict(),
        "gameweeks": [int(gw) for gw in out.gameweeks],
        "official_snapshot": out.snapshot,
        "base_safe_to_act": bool(out.safety.safe_to_act),
        "base_full_apex_ready": bool(out.safety.full_apex_ready),
        "base_publication_blockers": list(out.safety.blockers),
        "policy": {
            "legacy": "confidence floors plus adverse-evidence ceilings",
            "ev_first": "adverse-evidence ceilings only; uncertainty remains diagnostic",
            "projection_surface": "canonical ensemble mean xp for both policies",
        },
        "eligibility": {
            "legacy_xi_eligible_count": len(legacy_xi),
            "ev_first_xi_eligible_count": len(new_xi),
            "legacy_captain_eligible_count": len(legacy_captain),
            "ev_first_captain_eligible_count": len(new_captain),
            "uncertainty_diagnostic_count": len(
                eligibility.get("uncertainty_diagnostic_ids", [])
            ),
        },
        "legacy": old,
        "ev_first": new,
        "decision_delta": {
            "objective_delta": float(new["objective"] - old["objective"]),
            "first_gw_expected_points_delta": float(
                new["first_gw_expected_total_points"]
                - old["first_gw_expected_total_points"]
            ),
            "squad_overlap": len(old_squad & new_squad),
            "first_gw_xi_overlap": len(old_xi & new_xi_ids),
            "players_in": [names[pid] for pid in sorted(new_squad - old_squad)],
            "players_out": [names[pid] for pid in sorted(old_squad - new_squad)],
            "first_gw_xi_in": [names[pid] for pid in sorted(new_xi_ids - old_xi)],
            "first_gw_xi_out": [names[pid] for pid in sorted(old_xi - new_xi_ids)],
            "captain_changed": new["first_gw_captain_id"] != old["first_gw_captain_id"],
        },
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
