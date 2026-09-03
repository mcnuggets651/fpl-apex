from __future__ import annotations

from copy import deepcopy

from apex.runtime.publication import replay_security_payload
from apex.runtime.publication_impl import canonical_json_bytes


def _decision_payload() -> dict:
    return {
        "schema_version": 1,
        "system_decision": {
            "decision_mode": "INITIAL_SQUAD",
            "squad_ids": list(range(1, 16)),
            "xi_ids": list(range(1, 12)),
            "captain_id": 1,
            "vice_captain_id": 2,
        },
        "certification": {
            "state": "CERTIFIED",
            "actionable": True,
            "reasons": [],
        },
        "provider_diagnostics": {
            "max_contiguous_horizon": 1,
            "contingency_qualified_horizon": 1,
            "contingency_missing_by_horizon": {},
            "serving_provider_by_horizon": {"1": "airsenal"},
            "decision_optimisation": {
                "kind": "INITIAL_SQUAD",
                "status": "OPTIMAL",
                "solver": {
                    "message": "Optimization terminated successfully.",
                    "mip_gap": 0.0,
                    "primary_message": "primary backend status",
                    "secondary_message": "secondary backend status",
                    "next_candidate_message": "next-candidate backend status",
                    "primary_tiebreak": "LEXICOGRAPHIC_SQUAD_BLOCKS_UNDER_EXACT_PRIMARY_LOCK",
                    "selection_policy": "PRIMARY_MAX_EV_FALLBACK_UNCERTIFIED_SHORTLIST",
                    "shortlist_complete": False,
                    "candidate_count": 16,
                    "selected_generation_rank": 1,
                    "selected_exact_objective": 123.0,
                },
                "weeks": [],
            },
            "runtime_serving_h1_health": "HEALTHY",
        },
        "evidence_manifest": {
            "hard_evidence_count": 0,
            "hard_exclusion_count": 0,
        },
    }


def _semantic_bytes(payload: dict) -> bytes:
    return canonical_json_bytes(replay_security_payload(payload))


def test_solver_backend_telemetry_is_not_part_of_replay_identity():
    baseline = _decision_payload()
    expected = _semantic_bytes(baseline)

    mutations = {
        "message": "different HiGHS status text on another runner",
        "mip_gap": 1.23456789e-12,
        "primary_message": "different primary status text",
        "secondary_message": "different secondary status text",
        "next_candidate_message": "different next-candidate status text",
    }
    for field, value in mutations.items():
        changed = deepcopy(baseline)
        changed["provider_diagnostics"]["decision_optimisation"]["solver"][field] = value
        assert _semantic_bytes(changed) == expected


def test_decision_driving_optimisation_state_remains_part_of_replay_identity():
    baseline = _decision_payload()
    expected = _semantic_bytes(baseline)

    changed_policy = deepcopy(baseline)
    changed_policy["provider_diagnostics"]["decision_optimisation"]["solver"][
        "selection_policy"
    ] = "DIFFERENT_POLICY"
    assert _semantic_bytes(changed_policy) != expected

    changed_objective = deepcopy(baseline)
    changed_objective["provider_diagnostics"]["decision_optimisation"]["solver"][
        "selected_exact_objective"
    ] = 122.0
    assert _semantic_bytes(changed_objective) != expected

    changed_decision = deepcopy(baseline)
    changed_decision["system_decision"]["captain_id"] = 3
    assert _semantic_bytes(changed_decision) != expected
