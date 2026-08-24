from __future__ import annotations

import pytest

from apex_fpl.core import DecisionSearchFailure, DecisionSearchOutcome
from apex_fpl.core.decision import SolverStatus


def test_solver_limit_error_and_true_infeasibility_remain_distinct_outcomes() -> None:
    limit = DecisionSearchOutcome(
        failure=DecisionSearchFailure(SolverStatus.SOLVER_LIMIT, "time limit")
    )
    error = DecisionSearchOutcome(
        failure=DecisionSearchFailure(SolverStatus.ERROR, "worker crashed")
    )
    infeasible = DecisionSearchOutcome(
        failure=DecisionSearchFailure(SolverStatus.INFEASIBLE, "proved infeasible")
    )
    assert limit.status is SolverStatus.SOLVER_LIMIT
    assert error.status is SolverStatus.ERROR
    assert infeasible.status is SolverStatus.INFEASIBLE
    assert len({limit.status, error.status, infeasible.status}) == 3


def test_search_outcome_requires_exactly_one_result_or_failure() -> None:
    with pytest.raises(ValueError, match="exactly one"):
        DecisionSearchOutcome()
    with pytest.raises(ValueError, match="not a decision-search failure"):
        DecisionSearchFailure(SolverStatus.OPTIMAL, "not a failure")
