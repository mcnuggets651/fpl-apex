from types import SimpleNamespace

from apex_fpl.services.pinnacle_readiness import evaluate_pinnacle_payload
from scripts.audit_max_ev_policy import _certified_infeasible


def test_missing_solver_metadata_is_not_an_infeasibility_certificate():
    decision = SimpleNamespace(status="Infeasible", solution=SimpleNamespace(solver={}))
    assert _certified_infeasible(decision) is False


def test_only_highs_status_two_certifies_infeasibility():
    certified = SimpleNamespace(
        status="Infeasible", solution=SimpleNamespace(solver={"status_code": 2})
    )
    limited = SimpleNamespace(
        status="Infeasible", solution=SimpleNamespace(solver={"status_code": 1})
    )
    assert _certified_infeasible(certified) is True
    assert _certified_infeasible(limited) is False


def test_incomplete_exact_shortlist_blocks_release():
    # Minimal payload intentionally omits every unrelated production requirement;
    # the assertion is that shortlist incompleteness itself is a blocker rather
    # than a warning, irrespective of the other expected blockers.
    result = evaluate_pinnacle_payload(
        {
            "authoritative_decision": {
                "status": "Optimal",
                "objective": 1.0,
                "objective_reconciliation": 1.0,
                "solution": {"status": "Optimal", "squad": [], "xi": []},
                "weeks": [],
                "shortlist": {
                    "candidate_count": 1,
                    "complete_within_configured_band": False,
                },
                "equivalence": {"unique_optimum_proven": False},
            }
        }
    )
    assert result.ready is False
    assert any("shortlist is incomplete" in blocker for blocker in result.blockers)
    assert not any("shortlist" in warning for warning in result.warnings)
