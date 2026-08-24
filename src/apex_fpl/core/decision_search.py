"""Typed non-success decision-search outcomes.

DecisionResult intentionally represents a feasible incumbent. This envelope preserves
why a search produced no publishable result without collapsing solver limits/errors into
INFEASIBLE.
"""

from __future__ import annotations

from dataclasses import dataclass

from .decision import DecisionResult, SolverStatus


_FAILURE_STATUSES = {
    SolverStatus.INFEASIBLE,
    SolverStatus.UNBOUNDED,
    SolverStatus.SOLVER_LIMIT,
    SolverStatus.ERROR,
    SolverStatus.INVALID_INPUT,
}


@dataclass(frozen=True, slots=True)
class DecisionSearchFailure:
    status: SolverStatus
    message: str

    def __post_init__(self) -> None:
        if self.status not in _FAILURE_STATUSES:
            raise ValueError(f"{self.status.value} is not a decision-search failure status")
        message = str(self.message).strip()
        if not message:
            raise ValueError("decision-search failure requires a message")
        object.__setattr__(self, "message", message)

    def semantic_payload(self) -> dict[str, str]:
        return {"status": self.status.value, "message": self.message}


@dataclass(frozen=True, slots=True)
class DecisionSearchOutcome:
    result: DecisionResult | None = None
    failure: DecisionSearchFailure | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.failure is None):
            raise ValueError("DecisionSearchOutcome requires exactly one of result/failure")

    @property
    def status(self) -> SolverStatus:
        return self.result.solver.status if self.result is not None else self.failure.status  # type: ignore[union-attr]
