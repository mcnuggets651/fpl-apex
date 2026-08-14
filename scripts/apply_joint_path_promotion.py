#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.services.answer_context import build_answer_context
from apex_fpl.services.decision_bundle import DecisionBundle
from apex_fpl.services.decision_eligibility import captain_eligible_ids, evidence_eligibility
from apex_fpl.services.joint_initial_path import optimise_joint_initial_path

PROMOTION_GAIN_FLOOR = 0.25
PER_VIEW_CANDIDATES = 3
TRANSFER_CANDIDATE_LIMIT = 180


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return payload


def _records(frame: pd.DataFrame) -> list[dict]:
    if frame.empty:
        return []
    return json.loads(frame.to_json(orient="records"))


def _promotion_gate(result) -> dict:
    return {
        "joint_path_optimal": result.status == "optimal",
        "candidate_pool_stable": bool(result.candidate_pool_stable),
        "material_gain_vs_static": bool(
            result.gain_vs_baseline is not None
            and result.gain_vs_baseline >= PROMOTION_GAIN_FLOOR
        ),
        "promotion_candidate": bool(
            result.status == "optimal"
            and result.candidate_pool_stable
            and result.gain_vs_baseline is not None
            and result.gain_vs_baseline >= PROMOTION_GAIN_FLOOR
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--output-dir", default="data/generated")
    args = parser.parse_args()

    bundle = DecisionBundle.load(args.bundle_dir)
    out = bundle.to_pipeline_output()
    output_dir = Path(args.output_dir)
    recommendation_path = output_dir / "apex_recommendation_latest.json"
    context_path = output_dir / "apex_answer_context.json"
    pinnacle_path = output_dir / "pinnacle_latest.json"

    payload = _load(recommendation_path)
    pinnacle = _load(pinnacle_path)
    if payload.get("ready_to_act") is not True:
        raise SystemExit("joint-path promotion requires an already-actionable canonical fallback")
    if payload.get("decision_bundle_id") != bundle.bundle_id:
        raise SystemExit("canonical recommendation does not match the sealed decision bundle")
    if pinnacle.get("decision_bundle_id") != bundle.bundle_id:
        raise SystemExit("Pinnacle diagnostic does not match the sealed decision bundle")

    players, eligibility = evidence_eligibility(out.players, out.news_audit)
    captain_eligible = captain_eligible_ids(players)
    xi_eligible = set(players.loc[players["xi_evidence_eligible"], "player_id"].astype(int))
    settings = bundle.settings
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
        per_view_candidates=PER_VIEW_CANDIDATES,
        transfer_candidate_limit=TRANSFER_CANDIDATE_LIMIT,
        exact_candidate_limit=int(settings.get("exact_candidate_limit", 16)),
    )
    gate = _promotion_gate(result)

    diagnostics = payload.setdefault("internal_diagnostics", {})
    diagnostics["joint_initial_path"] = {
        "contract": "apex-joint-initial-path-production-v1",
        "decision_bundle_id": bundle.bundle_id,
        "promotion_gain_floor": PROMOTION_GAIN_FLOOR,
        "per_view_candidates": PER_VIEW_CANDIDATES,
        "transfer_candidate_limit": TRANSFER_CANDIDATE_LIMIT,
        "eligibility_contract": eligibility,
        "promotion_gate": gate,
        **result.to_dict(),
    }

    policy = payload.setdefault("decision_policy", {})
    policy["starting_squad_transfer_horizon"] = [int(gw) for gw in out.gameweeks]
    policy["future_transfer_rules"] = (
        "rolled free transfers, current cash/selling prices and explicit -4 hit costs; "
        "future moves remain contingent and are re-solved before every deadline"
    )
    policy["future_price_assumption"] = "current official prices held fixed; no speculative price-rise forecast"

    if gate["promotion_candidate"]:
        selected = result.selected
        if selected is None:
            raise SystemExit("promotion gate passed without a selected joint-path squad")
        selected_ids = set(int(pid) for pid in selected.squad_ids)
        squad = players[players["player_id"].astype(int).isin(selected_ids)].copy()
        if len(squad) != 15:
            raise SystemExit("joint-path selected squad does not resolve to 15 players")

        gw1 = int(out.gameweeks[0])
        px = (
            out.projections[out.projections["gw"].astype(int).eq(gw1)]
            .groupby("player_id")["xp"]
            .sum()
        )
        squad["gw1_xp"] = squad["player_id"].map(px).fillna(0.0)
        appearances = pd.to_numeric(
            players.get("appearance_probability", pd.Series(1.0, index=players.index)),
            errors="coerce",
        ).fillna(1.0)
        appearance = {
            int(pid): min(max(float(prob), 0.0), 1.0)
            for pid, prob in zip(players["player_id"].astype(int), appearances)
        }
        xp_map = {int(pid): float(value) for pid, value in px.items()}
        xi, mechanics = optimise_fixed_squad_gameweek(
            squad,
            xp_map,
            appearance,
            captain_eligible=captain_eligible,
            xi_eligible=xi_eligible,
        )
        names = {
            int(row.player_id): str(row.web_name)
            for row in players[["player_id", "web_name"]]
            .drop_duplicates("player_id")
            .itertuples(index=False)
        }
        recommendation = payload.get("recommendation") or {}
        recommendation.update(
            {
                "selector": "joint_gw1_gw8_transfer_path_maximum_ev",
                "selector_reason": (
                    "The starting 15 is chosen by exact GW1 mechanics plus the best legal "
                    "GW2-GW8 transfer path on the same ensemble-mean xP surface. Rolled free "
                    "transfers, bank and explicit hit costs are part of the objective."
                ),
                "objective": float(selected.total_objective),
                "objective_reconciliation": float(selected.total_objective),
                "static_path_objective": (
                    float(result.baseline.total_objective) if result.baseline else None
                ),
                "gain_vs_static_path": float(result.gain_vs_baseline or 0.0),
                "squad": _records(squad.sort_values(["position", "price", "player_id"])),
                "xi": _records(xi.sort_values(["position", "price", "player_id"])),
                "captain": names.get(int(mechanics.captain_id), str(mechanics.captain_id)),
                "vice_captain": names.get(
                    int(mechanics.vice_captain_id), str(mechanics.vice_captain_id)
                ),
                "bench_gk": names.get(int(mechanics.bench_gk_id), str(mechanics.bench_gk_id)),
                "outfield_bench_order": [
                    names.get(int(pid), str(pid)) for pid in mechanics.outfield_bench_order
                ],
                "gw1_expected_total_with_mechanics": float(mechanics.expected_total_points),
                "planned_transfer_path": list(selected.weeks),
                "planned_transfer_hit_cost": int(selected.total_hit_cost),
                "future_moves_are_contingent": True,
            }
        )
        payload["recommendation"] = recommendation
        policy["primary_selection"] = (
            "maximum expected points over the legal GW1-GW8 ownership path when the "
            "predeclared joint-path promotion gate passes; otherwise exact static-horizon fallback"
        )
        policy["joint_path_promoted"] = True
    else:
        policy["joint_path_promoted"] = False
        policy["joint_path_fallback"] = "existing exact static-horizon canonical selector"

    answer_context = build_answer_context(payload, pinnacle)
    if answer_context.get("safe_to_act") is not True:
        payload["ready_to_act"] = False
        payload["blockers"] = list(
            dict.fromkeys([*(payload.get("blockers") or []), *(answer_context.get("blockers") or [])])
        )
        payload["recommendation"] = None
        answer_context = build_answer_context(payload, pinnacle)

    recommendation_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    context_path.write_text(json.dumps(answer_context, indent=2), encoding="utf-8")

    if payload.get("ready_to_act") is not True or answer_context.get("safe_to_act") is not True:
        raise SystemExit("joint-path production promotion failed the canonical answer gate")

    print(
        json.dumps(
            {
                "selector": payload["recommendation"]["selector"],
                "promotion_gate": gate,
                "gain_vs_static_path": payload["recommendation"].get("gain_vs_static_path"),
                "planned_transfer_hit_cost": payload["recommendation"].get("planned_transfer_hit_cost"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
