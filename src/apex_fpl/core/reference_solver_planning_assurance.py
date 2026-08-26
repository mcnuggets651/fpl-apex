"""Dependency-free assurance certificate for receding-horizon reference-solver parity."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .decision import RationalValue
from .ids import (
    CandidateUniverseId,
    DecisionInputId,
    DecisionPolicyId,
    ReferenceSolverCertificateId,
)
from .reference_solver_planning_io import PlanningReferenceSolverStatus


def _artifact_id(value: str, *, label: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


@dataclass(frozen=True, slots=True)
class PlanningReferenceSolverCertificate:
    decision_input_id: DecisionInputId
    candidate_universe_id: CandidateUniverseId
    decision_policy_id: DecisionPolicyId
    worker_name: str
    worker_version: str
    solver_contract: str
    solver_status: PlanningReferenceSolverStatus
    best_objective: RationalValue | None
    best_bound: RationalValue | None
    gap: RationalValue | None
    selected_action_id: str | None
    selected_trajectory_id: str | None
    search_complete: bool
    tie_break_policy_id: str
    solver_input_artifact_id: str
    solver_output_artifact_id: str
    worker_artifact_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported planning reference solver certificate schema")
        for label in ("worker_name", "worker_version", "solver_contract", "tie_break_policy_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"planning reference {label} is required")
            object.__setattr__(self, label, value)
        if not isinstance(self.solver_status, PlanningReferenceSolverStatus):
            raise ValueError("planning reference solver status must be typed")
        if not isinstance(self.search_complete, bool):
            raise ValueError("planning reference search_complete must be boolean")
        paired = (self.selected_action_id is None, self.selected_trajectory_id is None)
        if paired[0] != paired[1]:
            raise ValueError("planning reference selected action/trajectory identities must be paired")
        for field in ("selected_action_id", "selected_trajectory_id"):
            value = getattr(self, field)
            if value is not None:
                text = str(value).strip()
                if not text:
                    raise ValueError(f"planning reference {field} cannot be blank")
                object.__setattr__(self, field, text)
        for field in (
            "solver_input_artifact_id",
            "solver_output_artifact_id",
            "worker_artifact_id",
        ):
            object.__setattr__(self, field, _artifact_id(getattr(self, field), label=field))
        if self.gap is not None:
            if self.best_objective is None or self.best_bound is None:
                raise ValueError("planning reference gap requires objective and bound")
            expected = RationalValue(
                self.best_bound.numerator * self.best_objective.denominator
                - self.best_objective.numerator * self.best_bound.denominator,
                self.best_bound.denominator * self.best_objective.denominator,
            )
            if expected != self.gap or self.gap.numerator < 0:
                raise ValueError("planning reference certificate gap does not reconcile")
        if self.solver_status is PlanningReferenceSolverStatus.OPTIMAL:
            if (
                not self.search_complete
                or self.best_objective is None
                or self.best_bound is None
                or self.gap is None
                or self.gap.numerator != 0
                or self.selected_action_id is None
                or self.selected_trajectory_id is None
            ):
                raise ValueError("OPTIMAL planning reference certificate requires complete zero-gap parity")
        if self.solver_status in {
            PlanningReferenceSolverStatus.ERROR,
            PlanningReferenceSolverStatus.INFEASIBLE,
        } and self.best_objective is not None:
            raise ValueError(f"{self.solver_status.value} planning reference cannot carry objective")

    def semantic_payload(self) -> dict[str, object]:
        def rv(value: RationalValue | None) -> dict[str, int] | None:
            return None if value is None else value.semantic_payload()

        return {
            "schema_name": "apex-planning-reference-solver-certificate",
            "schema_version": self.schema_version,
            "decision_input_id": str(self.decision_input_id),
            "candidate_universe_id": str(self.candidate_universe_id),
            "decision_policy_id": str(self.decision_policy_id),
            "worker_name": self.worker_name,
            "worker_version": self.worker_version,
            "solver_contract": self.solver_contract,
            "solver_status": self.solver_status.value,
            "best_objective": rv(self.best_objective),
            "best_bound": rv(self.best_bound),
            "gap": rv(self.gap),
            "selected_action_id": self.selected_action_id,
            "selected_trajectory_id": self.selected_trajectory_id,
            "search_complete": self.search_complete,
            "tie_break_policy_id": self.tie_break_policy_id,
            "solver_input_artifact_id": self.solver_input_artifact_id,
            "solver_output_artifact_id": self.solver_output_artifact_id,
            "worker_artifact_id": self.worker_artifact_id,
        }

    @property
    def certificate_id(self) -> ReferenceSolverCertificateId:
        return ReferenceSolverCertificateId(canonical_sha256(self.semantic_payload()))
