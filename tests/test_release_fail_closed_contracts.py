from apex_fpl.optimisation.solver_status import certified_infeasible
from apex_fpl.services.pinnacle_readiness import evaluate_pinnacle_payload


def test_missing_solver_metadata_is_not_an_infeasibility_certificate():
    assert certified_infeasible("Infeasible", {}) is False


def test_only_highs_status_two_certifies_infeasibility():
    assert certified_infeasible("Infeasible", {"status_code": 2}) is True
    assert certified_infeasible("Infeasible", {"status_code": 1}) is False
    assert certified_infeasible("SolverLimit", {"status_code": 2}) is False


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
