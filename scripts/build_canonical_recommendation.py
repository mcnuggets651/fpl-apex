#!/usr/bin/env python3
"""Assemble the non-actionable canonical staging packet.

This script validates that Pinnacle, Elite and the sealed bundle all describe the
same healthy decision surface. It deliberately does *not* publish a team. The only
code allowed to turn this staging packet into ``ready_to_act=true`` is the final
adaptive/receding-horizon strategy selector in ``apply_joint_path_promotion.py``.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from apex_fpl.services.decision_bundle import DecisionBundle


FINAL_SELECTOR_NAMES = (
    "adaptive_gw1_launch_with_transfer_option_value",
    "receding_horizon_current_team_maximum_ev",
)


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"missing required diagnostic: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SystemExit(f"unreadable diagnostic {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"diagnostic is not a JSON object: {path}")
    return payload


def _snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    snap = payload.get("official_snapshot")
    return snap if isinstance(snap, dict) else {}


def _snapshot_fingerprint(payload: dict[str, Any]) -> tuple[str | None, str | None]:
    snap = _snapshot(payload)
    bootstrap = snap.get("bootstrap_sha256")
    fixtures = snap.get("fixtures_sha256")
    return (
        str(bootstrap) if bootstrap else None,
        str(fixtures) if fixtures else None,
    )


def _staging_context(payload: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    stage_blockers = list(blockers)
    if not stage_blockers:
        stage_blockers.append("final adaptive/receding-horizon strategy selector not yet applied")
    return {
        "contract": "apex-answer-context-v1",
        "generated_at": payload["generated_at"],
        "only_input_for_apex_answers": True,
        "safe_to_act": False,
        "ready_to_act": False,
        "blockers": stage_blockers,
        "warnings": [],
        "decision_bundle_id": payload.get("decision_bundle_id"),
        "production_result": None,
        "recommendation": None,
        "strategy_stage": "base_validated" if payload.get("strategy_base_ready") else "blocked",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pinnacle", default="data/generated/pinnacle_latest.json")
    parser.add_argument("--elite", default="data/generated/elite_latest.json")
    parser.add_argument("--output-dir", default="data/generated")
    parser.add_argument("--bundle-dir")
    args = parser.parse_args()

    pinnacle = _load(Path(args.pinnacle))
    elite = _load(Path(args.elite))
    bundle = DecisionBundle.load(args.bundle_dir) if args.bundle_dir else None

    blockers: list[str] = []
    if pinnacle.get("safe_to_act") is not True:
        blockers.append("Apex safety gate is not green")
    if pinnacle.get("full_apex_ready") is not True:
        blockers.append("full Apex data gate is not green")
    if pinnacle.get("pinnacle_ready") is not True:
        blockers.append("Pinnacle decision-readiness gate is not green")
        gate = pinnacle.get("pinnacle_gate")
        if isinstance(gate, dict):
            blockers.extend(str(row) for row in gate.get("blockers") or [])
    if elite.get("safe_to_act") is not True or elite.get("full_apex_ready") is not True:
        blockers.append("Elite diagnostic did not run on a fully green Apex surface")

    pinnacle_fp = _snapshot_fingerprint(pinnacle)
    elite_fp = _snapshot_fingerprint(elite)
    if None in pinnacle_fp or None in elite_fp:
        blockers.append("diagnostic Official FPL content hashes are missing")
    elif pinnacle_fp != elite_fp:
        blockers.append("Pinnacle/Elite Official FPL content hashes do not match")

    pinnacle_bundle_id = pinnacle.get("decision_bundle_id")
    elite_bundle_id = elite.get("decision_bundle_id")
    if not pinnacle_bundle_id or not elite_bundle_id:
        blockers.append("Pinnacle/Elite sealed decision bundle identity is missing")
    elif pinnacle_bundle_id != elite_bundle_id:
        blockers.append("Pinnacle/Elite sealed decision bundle identities do not match")
    if bundle is not None and (
        pinnacle_bundle_id != bundle.bundle_id or elite_bundle_id != bundle.bundle_id
    ):
        blockers.append("diagnostics do not match the supplied sealed decision bundle")

    # The exact-horizon object remains a required internal diagnostic. It proves the
    # surface and exact FPL mechanics are healthy, but it is no longer a production
    # selector after the adaptive-strategy release.
    authority = pinnacle.get("authoritative_decision")
    if not isinstance(authority, dict) or authority.get("status") != "Optimal":
        blockers.append("internal exact-horizon diagnostic is missing or not optimal")
        authority = authority if isinstance(authority, dict) else {}
    selected = authority.get("solution")
    if not isinstance(selected, dict) or selected.get("status") != "Optimal":
        blockers.append("internal exact-horizon diagnostic solution is not optimal")
        selected = selected if isinstance(selected, dict) else {}
    squad = selected.get("squad") or []
    xi = selected.get("xi") or []
    weeks = authority.get("weeks") or []
    mechanics = weeks[0] if isinstance(weeks, list) and weeks else {}
    if not isinstance(squad, list) or len(squad) != 15:
        blockers.append("internal exact-horizon diagnostic does not contain a legal 15")
    if not isinstance(xi, list) or len(xi) != 11:
        blockers.append("internal exact-horizon diagnostic does not contain a legal XI")
    if not isinstance(mechanics, dict) or not mechanics:
        blockers.append("internal exact-horizon exact mechanics are missing")
    elif mechanics.get("captain_id") == mechanics.get("vice_captain_id"):
        blockers.append("internal exact-horizon captain and vice are identical")

    blockers = list(dict.fromkeys(blockers))
    base_ready = not blockers
    generated_at = (
        bundle.created_at
        if bundle is not None
        else pinnacle.get("generated_at") or datetime.now(timezone.utc).isoformat()
    )
    payload: dict[str, Any] = {
        "contract": "apex-strategy-recommendation-v3",
        "generated_at": generated_at,
        "canonical": True,
        "user_facing_source_of_truth": True,
        "strategy_stage": "base_validated" if base_ready else "blocked",
        "strategy_base_ready": base_ready,
        # No intermediate selector may ever be actionable. Only the final strategy
        # assembler is allowed to flip this field to true.
        "ready_to_act": False,
        "blockers": blockers,
        "official_snapshot": pinnacle.get("official_snapshot"),
        "decision_bundle_id": pinnacle_bundle_id,
        "decision_bundle": pinnacle.get("decision_bundle"),
        "gameweeks": pinnacle.get("gameweeks") or elite.get("gameweeks") or [],
        "decision_policy": {
            "primary_forecast": "canonical ensemble xp",
            "production_selectors": list(FINAL_SELECTOR_NAMES),
            "pre_gw1_selection": (
                "exact GW1 expected points first; future legal transfer option value only among "
                "squads inside the disclosed near-equivalent GW1 point band"
            ),
            "in_season_selection": (
                "receding-horizon maximum-EV policy from the actual current squad, bank, "
                "selling prices and free-transfer state; publish only the freshly solved first action"
            ),
            "static_exact_horizon_role": "internal diagnostic only; never user-facing authority",
            "secondary_selection": "none; Elite is diagnostic-only",
            "ownership_in_points_objective": False,
            "minutes_model": "first-class EV input; uncertainty is not a separate safety penalty",
            "uncertainty": "correlated scenarios/CVaR/regret are diagnostics, not a second hidden forecast",
            "deadline_mechanics": "exact XI/captain/vice/autosub mechanics on the final selected squad",
            "unique_optimum_claimed": False,
            "same_surface_check": "sealed decision bundle identity and material input hashes must match",
        },
        "recommendation": None,
        "epsilon_convergence": elite.get("epsilon_convergence"),
        "epsilon_sensitivity": elite.get("epsilon_sensitivity") or [],
        "haaland_scenario": (elite.get("scenarios") or {}).get("haaland"),
        "no_haaland_scenario": (elite.get("scenarios") or {}).get("no_haaland"),
        "robustness": {
            "cvar_scenarios": pinnacle.get("robust_cvar_scenarios"),
            "robust_compare": pinnacle.get("robustness_comparison"),
            "selection_regret": pinnacle.get("selection_regret"),
            "solver_parity": pinnacle.get("solver_parity"),
            "pinnacle_gate": pinnacle.get("pinnacle_gate"),
        },
        "internal_diagnostics": {
            "pinnacle_contract": pinnacle.get("contract"),
            "elite_contract": elite.get("contract"),
            "pinnacle_snapshot_id": _snapshot(pinnacle).get("snapshot_id"),
            "elite_snapshot_id": _snapshot(elite).get("snapshot_id"),
            "pinnacle_content_fingerprint": pinnacle_fp,
            "elite_content_fingerprint": elite_fp,
            "same_official_surface": pinnacle_fp == elite_fp and None not in pinnacle_fp,
            "pinnacle_decision_bundle_id": pinnacle_bundle_id,
            "elite_decision_bundle_id": elite_bundle_id,
            "same_decision_bundle": bool(
                pinnacle_bundle_id
                and elite_bundle_id
                and pinnacle_bundle_id == elite_bundle_id
            ),
            "exact_horizon_staging": {
                "authority": False,
                "purpose": "mechanics/robustness diagnostic only",
                "contract": authority.get("contract"),
                "status": authority.get("status"),
                "objective": authority.get("objective"),
                "objective_reconciliation": authority.get("objective_reconciliation"),
                "solution": selected,
                "weeks": weeks,
                "shortlist": authority.get("shortlist"),
                "equivalence": authority.get("equivalence"),
            },
        },
    }

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "apex_recommendation_latest.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    context = _staging_context(payload, blockers)
    (output_dir / "apex_answer_context.json").write_text(
        json.dumps(context, indent=2) + "\n", encoding="utf-8"
    )
    markdown_lines = [
        "# Apex Unified Recommendation — STAGING",
        "",
        f"Generated: {generated_at}",
        "",
        "No team is actionable until the adaptive/receding-horizon strategy selector,",
        "all-player truth audit and final selected-player evidence gate complete.",
    ]
    if blockers:
        markdown_lines += ["", "Base-stage blockers:", "", *[f"- {row}" for row in blockers]]
    (output_dir / "apex_recommendation_latest.md").write_text(
        "\n".join(markdown_lines) + "\n", encoding="utf-8"
    )
    print("\n".join(markdown_lines))
    raise SystemExit(0 if base_ready else 2)


if __name__ == "__main__":
    main()
