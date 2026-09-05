from pathlib import Path


def test_fixed_route_stress_is_not_wired_into_serving_solve() -> None:
    solve_source = Path("src/apex/runtime/solve.py").read_text(encoding="utf-8")
    stress_source = Path("src/apex/decision/root_action_stress.py").read_text(
        encoding="utf-8"
    )

    # Fixed baseline-route stress cannot certify scenario-optimal continuation.
    # Until scenario-conditioned re-optimisation/equivalent stochastic solving is
    # complete, it must not enter the production solve or invoke the policy selector.
    assert "root_action_stress" not in solve_source
    assert "stress_candidate_routes_by_root_action" not in solve_source
    assert "summarise_transfer_policy" not in stress_source
    assert "ScenarioActionValue" not in stress_source
