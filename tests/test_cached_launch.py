from __future__ import annotations

import json

from apex_fpl.services.cached_launch import load_cached_hardened_launch


def _payload(bundle_id: str = "bundle-1") -> dict:
    candidate = {
        "source_rank": 1,
        "squad_ids": list(range(1, 16)),
        "squad_names": [f"P{pid}" for pid in range(1, 16)],
        "starting_cost": 99.5,
        "starting_bank": 0.5,
        "gw1_expected_points": 70.0,
        "gw1_regret": 0.1,
        "within_gw1_band": True,
        "future_objective": 300.0,
        "total_hit_cost": 0,
        "weeks": [],
    }
    return {
        "ready_to_act": False,
        "recommendation": None,
        "internal_diagnostics": {
            "joint_initial_path": {
                "contract": "apex-adaptive-launch-production-v2",
                "decision_bundle_id": bundle_id,
                "promotion_gate": {
                    "promotion_candidate": True,
                    "candidate_pool_stable": True,
                    "gw1_floor_respected": True,
                },
                "status": "optimal",
                "baseline": candidate,
                "selected": candidate,
                "candidates": [candidate],
                "best_gw1_points": 70.1,
                "gw1_regret_tolerance": 0.25,
                "gw1_floor": 69.85,
                "small_pool_selected_ids": list(range(1, 16)),
                "full_pool_selected_ids": list(range(1, 16)),
                "candidate_pool_stable": True,
                "squad_overlap": 15,
                "gw1_delta_vs_static": 0.0,
                "future_delta_vs_static": 0.0,
                "projection_col": "xp",
                "note": (
                    "solver complete. Mandatory production convergence certification expanded "
                    "exact_candidate_limit from 16 to 24; winner_changed=false."
                ),
            }
        },
    }


def test_blocked_reality_output_can_reuse_broader_certified_math(tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    result = load_cached_hardened_launch(path, decision_bundle_id="bundle-1")

    assert result is not None
    assert result.status == "optimal"
    assert result.candidate_pool_stable is True
    assert result.selected is not None
    assert result.selected.squad_ids == tuple(range(1, 16))


def test_cache_rejects_other_decision_bundle(tmp_path):
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    assert load_cached_hardened_launch(path, decision_bundle_id="bundle-2") is None


def test_cache_rejects_narrow_result_without_broad_certification_marker(tmp_path):
    payload = _payload()
    payload["internal_diagnostics"]["joint_initial_path"]["note"] = "narrow solve only"
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_cached_hardened_launch(path, decision_bundle_id="bundle-1") is None


def test_cache_rejects_unstable_or_nonpromotable_result(tmp_path):
    payload = _payload()
    payload["internal_diagnostics"]["joint_initial_path"]["promotion_gate"][
        "promotion_candidate"
    ] = False
    path = tmp_path / "canonical.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert load_cached_hardened_launch(path, decision_bundle_id="bundle-1") is None
