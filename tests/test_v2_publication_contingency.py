from __future__ import annotations

from apex.runtime.publication import _governance


class Snapshot:
    def read_json(self, name):
        assert name == "qualification_matrix.json"
        return []


def test_governance_separates_serving_and_contingency_horizons() -> None:
    decision = {
        "certification": {
            "state": "DEGRADED",
            "actionable": True,
            "reasons": [],
            "warnings": ["future contingency horizon truncated"],
            "valid_until": "2026-09-05T10:00:00Z",
        },
        "system_decision": {"decision_mode": "TRANSFER_HORIZON"},
        "provider_diagnostics": {
            "max_contiguous_horizon": 8,
            "contingency_qualified_horizon": 4,
            "serving_provider_by_horizon": {
                str(horizon): "airsenal"
                for horizon in range(1, 9)
            },
        },
        "evidence_manifest": {},
    }
    acquisition = {
        "mode": "AUTHENTICATED_MY_TEAM",
        "credential_present": True,
        "state_complete_for_transfers": True,
    }
    governance = _governance(
        Snapshot(),
        decision,
        {"season": "2026-2027", "target_gameweek": 3},
        acquisition,
    )

    assert governance["max_contiguous_qualified_horizon"] == 8
    assert governance["contingency_qualified_horizon"] == 4
    assert governance["manager_actionability"]["manager_state_scope"] == "FULL_MANAGER"
