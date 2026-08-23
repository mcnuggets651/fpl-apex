#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

from apex_fpl.optimisation.transfer_views import optimise_transfer_plan_view
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.release_profile import INSEASON_SELECTOR


CONTRACT = "apex-inseason-action-sensitivity-v1"
TRANSFER_CANDIDATE_LIMIT = 160
SOLVER_RELATIVE_GAP = 0.0005
SOLVER_TIME_LIMIT = 180.0
OBJECTIVE_TOLERANCE = 1e-4


def _load(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _ids(rows: list[dict] | None) -> list[int]:
    return sorted(
        int(row["player_id"])
        for row in (rows or [])
        if isinstance(row, dict) and row.get("player_id") is not None
    )


def _action_signature(week: dict[str, Any] | None) -> dict[str, Any]:
    week = week or {}
    return {
        "gw": int(week.get("gw") or 0),
        "transfers": int(week.get("transfers") or 0),
        "hit_cost": int(week.get("hit_cost") or 0),
        "transfers_in_ids": _ids(week.get("transfers_in")),
        "transfers_out_ids": _ids(week.get("transfers_out")),
        "squad_ids": _ids(week.get("squad")),
    }


def _plan_record(name: str, plan, *, minimum: int | None, maximum: int | None) -> dict[str, Any]:
    first = plan.weeks[0] if plan.status == "Optimal" and plan.weeks else None
    return {
        "name": name,
        "first_gw_min_transfers": minimum,
        "first_gw_max_transfers": maximum,
        "status": plan.status,
        "solver_status_code": plan.solver_status_code,
        "solver_message": plan.solver_message,
        "objective": float(plan.objective) if math.isfinite(float(plan.objective)) else None,
        "objective_upper_bound": plan.objective_upper_bound,
        "mip_gap": plan.mip_gap,
        "certified_infeasible": bool(plan.certified_infeasible),
        "action": _action_signature(first) if first is not None else None,
    }


def audit_inseason_action_sensitivity(
    *,
    bundle: DecisionBundle,
    canonical: dict[str, Any],
) -> dict[str, Any]:
    recommendation = canonical.get("recommendation") or {}
    if recommendation.get("selector") != INSEASON_SELECTOR:
        raise ValueError("in-season action sensitivity requires the receding-horizon selector")
    if canonical.get("decision_bundle_id") != bundle.bundle_id:
        raise ValueError("canonical recommendation does not match the sealed DecisionBundle")

    out = bundle.to_pipeline_output()
    state_resolution = out.team_state
    state = state_resolution.state if state_resolution is not None else None
    if state_resolution is None or state_resolution.ok is not True or state is None:
        raise ValueError("in-season action sensitivity requires a healthy sealed team state")
    if len(state.squad) != 15 or not state.selling_prices_exact:
        raise ValueError("in-season action sensitivity requires exact 15-player selling-price state")

    players, _ = evidence_eligibility(out.players, out.news_audit)
    captain_eligible = captain_eligible_ids(players)
    settings = bundle.settings
    common = dict(
        players=players,
        projections=out.projections,
        gameweeks=[int(gw) for gw in out.gameweeks],
        current_squad=set(map(int, state.squad)),
        projection_col="xp",
        bank=float(state.bank),
        free_transfers=int(state.free_transfers),
        max_per_team=int(settings["max_per_team"]),
        decay=float(settings["fixture_decay"]),
        selling_prices={int(pid): float(price) for pid, price in state.selling_prices.items()},
        candidate_limit=TRANSFER_CANDIDATE_LIMIT,
        captain_eligible=captain_eligible,
        enforce_current_bench_resilience=True,
        solver_time_limit=SOLVER_TIME_LIMIT,
        solver_relative_gap=SOLVER_RELATIVE_GAP,
    )

    blockers: list[str] = []
    warnings: list[str] = []
    baseline_plan = optimise_transfer_plan_view(**common)
    baseline = _plan_record("unconstrained_replay", baseline_plan, minimum=None, maximum=None)
    if baseline_plan.status != "Optimal" or not baseline_plan.weeks:
        blockers.append(
            "fresh in-season baseline replay is not optimal: "
            + str(baseline_plan.solver_message or baseline_plan.status)
        )
        return {
            "contract": CONTRACT,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "decision_bundle_id": bundle.bundle_id,
            "selector": INSEASON_SELECTOR,
            "ready": False,
            "blockers": blockers,
            "warnings": warnings,
            "baseline": baseline,
            "counterfactuals": [],
        }

    published_action = recommendation.get("action_now") or {}
    published_signature = _action_signature(published_action)
    baseline_signature = _action_signature(baseline_plan.weeks[0])
    published_objective = float(recommendation.get("objective") or 0.0)
    if abs(float(baseline_plan.objective) - published_objective) > OBJECTIVE_TOLERANCE:
        blockers.append(
            "fresh in-season replay objective does not reproduce the published strategy "
            f"({baseline_plan.objective:.6f} vs {published_objective:.6f})"
        )
    if baseline_signature != published_signature:
        blockers.append("fresh in-season replay does not reproduce the published transfer action")

    published_transfers = int(published_signature["transfers"])
    free_transfers = int(state.free_transfers)
    specs: list[tuple[str, int | None, int | None]] = [
        ("roll", 0, 0),
        ("no_hit", 0, min(free_transfers, 15)),
        ("published_transfer_count", published_transfers, published_transfers),
    ]
    if published_transfers > 0:
        specs.append(("one_fewer_transfer", published_transfers - 1, published_transfers - 1))
    if published_transfers < 15:
        specs.append(("one_more_transfer", published_transfers + 1, published_transfers + 1))

    seen: set[tuple[int | None, int | None]] = set()
    counterfactuals: list[dict[str, Any]] = []
    for name, minimum, maximum in specs:
        key = (minimum, maximum)
        if key in seen:
            continue
        seen.add(key)
        plan = optimise_transfer_plan_view(
            **common,
            first_gw_min_transfers=minimum,
            first_gw_max_transfers=maximum,
        )
        record = _plan_record(name, plan, minimum=minimum, maximum=maximum)
        if plan.status == "Optimal":
            record["regret_vs_unconstrained"] = float(baseline_plan.objective) - float(plan.objective)
            if float(plan.objective) > float(baseline_plan.objective) + OBJECTIVE_TOLERANCE:
                blockers.append(
                    f"{name} counterfactual beats the supposedly unconstrained baseline"
                )
            if name == "published_transfer_count" and record.get("action") != published_signature:
                blockers.append(
                    "same-count in-season replay does not reproduce the published transfer identities"
                )
        elif plan.certified_infeasible:
            record["regret_vs_unconstrained"] = None
        else:
            blockers.append(
                f"{name} counterfactual is inconclusive: {plan.solver_message or plan.status}"
            )
        counterfactuals.append(record)

    hit_cost = int(published_signature["hit_cost"])
    if hit_cost > 0:
        roll = next((row for row in counterfactuals if row["name"] == "roll"), None)
        no_hit = next((row for row in counterfactuals if row["name"] == "no_hit"), None)
        if not blockers:
            roll_gain = roll.get("regret_vs_unconstrained") if roll else None
            no_hit_gain = no_hit.get("regret_vs_unconstrained") if no_hit else None
            warnings.append(
                "aggressive hit action certified on the sealed surface: "
                f"hit_cost={hit_cost}; roll_regret={roll_gain}; no_hit_regret={no_hit_gain}"
            )

    public_snapshot = bool(state.public_deadline_snapshot and state.source == "public_fpl_entry")
    if public_snapshot:
        warnings.append(
            "team state is the latest public deadline snapshot; FPL hides another manager's "
            "post-deadline transfers until the next deadline, so a manual override is required "
            "if the manager has already changed the squad"
        )

    return {
        "contract": CONTRACT,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decision_bundle_id": bundle.bundle_id,
        "selector": INSEASON_SELECTOR,
        "lifecycle": "in_season_receding_horizon",
        "gameweeks": [int(gw) for gw in out.gameweeks],
        "team_state": {
            "source": state.source,
            "published_gw": state.published_gw,
            "bank": state.bank,
            "free_transfers": state.free_transfers,
            "selling_prices_exact": state.selling_prices_exact,
            "public_deadline_snapshot": state.public_deadline_snapshot,
        },
        "published_action": published_signature,
        "baseline": baseline,
        "counterfactuals": counterfactuals,
        "ready": not blockers,
        "blockers": list(dict.fromkeys(blockers)),
        "warnings": list(dict.fromkeys(warnings)),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--canonical", default="data/generated/apex_recommendation_latest.json")
    parser.add_argument("--output", default="reports/inseason_action_sensitivity.json")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    canonical = _load(args.canonical)
    payload = audit_inseason_action_sensitivity(bundle=bundle, canonical=canonical)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))
    if payload.get("ready") is not True:
        raise SystemExit(
            "in-season action sensitivity is not ready: "
            + "; ".join(str(row) for row in payload.get("blockers") or [])
        )


if __name__ == "__main__":
    main()
