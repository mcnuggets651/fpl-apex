"""Independent-assurance contracts for Apex V2 Slice 10.

These types represent evidence produced independently of the DecisionEngine. They do not
make a decision; they certify whether a sealed decision survives reference mechanics and,
when available, an external reference-solver parity check.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256
from .decision import DecisionMechanics, RationalValue
from .ids import (
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    DecisionPolicyId,
    ForecastId,
    IndependentAssuranceReportId,
    ManagerStateId,
    ReferenceMechanicsCertificateId,
    ReferenceSolverCertificateId,
    RuleSetId,
)


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


class AssuranceParityStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class ReferenceSolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    SOLVER_LIMIT = "SOLVER_LIMIT"
    ERROR = "ERROR"


class ReferenceMechanicsCheck(StrEnum):
    INPUT_IDENTITY = "INPUT_IDENTITY"
    STATE_CURRENT_EXACT = "STATE_CURRENT_EXACT"
    OWNED_UNIVERSE_MATCH = "OWNED_UNIVERSE_MATCH"
    CHIP_AVAILABLE = "CHIP_AVAILABLE"
    TRANSFER_SET = "TRANSFER_SET"
    TRANSFER_POSITIONS = "TRANSFER_POSITIONS"
    SQUAD_LEGAL = "SQUAD_LEGAL"
    FINANCE = "FINANCE"
    HIT_COST = "HIT_COST"
    XI_LEGAL = "XI_LEGAL"
    BENCH_STRUCTURE = "BENCH_STRUCTURE"
    CAPTAIN_VICE = "CAPTAIN_VICE"
    EXPECTED_MECHANICS = "EXPECTED_MECHANICS"


@dataclass(frozen=True, slots=True)
class ReferenceCheckResult:
    check: ReferenceMechanicsCheck
    passed: bool
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.check, ReferenceMechanicsCheck):
            raise ValueError("reference mechanics check must be typed")
        if not isinstance(self.passed, bool):
            raise ValueError("reference mechanics passed must be boolean")
        detail = str(self.detail).strip()
        if not detail:
            raise ValueError("reference mechanics check requires detail")
        object.__setattr__(self, "detail", detail)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "check": self.check.value,
            "passed": self.passed,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class ReferenceMechanicsCertificate:
    decision_id: DecisionId
    decision_input_id: DecisionInputId
    manager_state_id: ManagerStateId
    forecast_id: ForecastId
    ruleset_id: RuleSetId
    candidate_universe_id: CandidateUniverseId
    action_id: str
    recomputed_bank_after_tenths: int | None
    recomputed_hit_points: int | None
    recomputed_mechanics: DecisionMechanics | None
    checks: tuple[ReferenceCheckResult, ...]
    algorithm_id: str
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ReferenceMechanicsCertificate schema_version")
        action_id = str(self.action_id).strip()
        algorithm_id = str(self.algorithm_id).strip()
        if not action_id or not algorithm_id:
            raise ValueError("reference mechanics certificate requires action and algorithm identity")
        for name in ("recomputed_bank_after_tenths", "recomputed_hit_points"):
            value = getattr(self, name)
            if value is not None and (
                isinstance(value, bool) or not isinstance(value, int) or value < 0
            ):
                raise ValueError(f"{name} must be nonnegative integer or None")
        checks = tuple(sorted(self.checks, key=lambda row: row.check.value))
        expected = set(ReferenceMechanicsCheck)
        actual = {row.check for row in checks}
        if actual != expected or len(checks) != len(expected):
            missing = sorted(item.value for item in expected - actual)
            extra = sorted(item.value for item in actual - expected)
            raise ValueError(
                f"reference mechanics certificate must contain every check once missing={missing} extra={extra}"
            )
        artifacts = tuple(sorted({_artifact_id(item, label="reference mechanics source artifact") for item in self.source_artifact_ids}))
        if not artifacts:
            raise ValueError("reference mechanics certificate requires immutable source evidence")
        if all(row.passed for row in checks) and self.recomputed_mechanics is None:
            raise ValueError("passing reference mechanics requires recomputed mechanics")
        object.__setattr__(self, "action_id", action_id)
        object.__setattr__(self, "algorithm_id", algorithm_id)
        object.__setattr__(self, "checks", checks)
        object.__setattr__(self, "source_artifact_ids", artifacts)

    @property
    def passed(self) -> bool:
        return all(row.passed for row in self.checks)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-reference-mechanics-certificate",
            "schema_version": self.schema_version,
            "decision_id": str(self.decision_id),
            "decision_input_id": str(self.decision_input_id),
            "manager_state_id": str(self.manager_state_id),
            "forecast_id": str(self.forecast_id),
            "ruleset_id": str(self.ruleset_id),
            "candidate_universe_id": str(self.candidate_universe_id),
            "action_id": self.action_id,
            "recomputed_bank_after_tenths": self.recomputed_bank_after_tenths,
            "recomputed_hit_points": self.recomputed_hit_points,
            "recomputed_mechanics": (
                None if self.recomputed_mechanics is None else self.recomputed_mechanics.semantic_payload()
            ),
            "checks": [row.semantic_payload() for row in self.checks],
            "algorithm_id": self.algorithm_id,
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def certificate_id(self) -> ReferenceMechanicsCertificateId:
        return ReferenceMechanicsCertificateId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class ReferenceSolverCertificate:
    decision_input_id: DecisionInputId
    candidate_universe_id: CandidateUniverseId
    decision_policy_id: DecisionPolicyId
    worker_name: str
    worker_version: str
    solver_status: ReferenceSolverStatus
    best_objective: RationalValue | None
    best_bound: RationalValue | None
    gap: RationalValue | None
    selected_action_id: str | None
    action_surface_complete: bool
    tie_break_policy_id: str | None
    solver_input_artifact_id: str
    solver_output_artifact_id: str
    worker_artifact_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ReferenceSolverCertificate schema_version")
        if not isinstance(self.solver_status, ReferenceSolverStatus):
            raise ValueError("reference solver status must be typed")
        for label in ("worker_name", "worker_version"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise ValueError(f"{label} is required")
            object.__setattr__(self, label, text)
        if not isinstance(self.action_surface_complete, bool):
            raise ValueError("reference solver action_surface_complete must be boolean")
        if self.selected_action_id is not None:
            selected = str(self.selected_action_id).strip()
            if not selected:
                raise ValueError("reference solver selected_action_id cannot be blank")
            object.__setattr__(self, "selected_action_id", selected)
        if self.tie_break_policy_id is not None:
            tie = str(self.tie_break_policy_id).strip()
            if not tie:
                raise ValueError("reference solver tie_break_policy_id cannot be blank")
            object.__setattr__(self, "tie_break_policy_id", tie)
        for label in ("solver_input_artifact_id", "solver_output_artifact_id", "worker_artifact_id"):
            object.__setattr__(self, label, _artifact_id(getattr(self, label), label=label))
        if self.gap is not None:
            if self.best_objective is None or self.best_bound is None:
                raise ValueError("reference solver gap requires objective and bound")
            expected = RationalValue(
                self.best_bound.numerator * self.best_objective.denominator
                - self.best_objective.numerator * self.best_bound.denominator,
                self.best_bound.denominator * self.best_objective.denominator,
            )
            if self.gap != expected or self.gap.numerator < 0:
                raise ValueError("reference solver gap does not reconcile objective and bound")
        if self.solver_status is ReferenceSolverStatus.OPTIMAL:
            if (
                self.best_objective is None
                or self.best_bound is None
                or self.gap is None
                or self.gap.numerator != 0
                or not self.action_surface_complete
            ):
                raise ValueError("OPTIMAL reference solver requires complete zero-gap evidence")
        if self.solver_status in {
            ReferenceSolverStatus.INFEASIBLE,
            ReferenceSolverStatus.ERROR,
        } and self.best_objective is not None:
            raise ValueError(f"{self.solver_status.value} reference result cannot carry objective")

    def semantic_payload(self) -> dict[str, object]:
        def rv(value: RationalValue | None) -> dict[str, int] | None:
            return None if value is None else value.semantic_payload()

        return {
            "schema_name": "apex-reference-solver-certificate",
            "schema_version": self.schema_version,
            "decision_input_id": str(self.decision_input_id),
            "candidate_universe_id": str(self.candidate_universe_id),
            "decision_policy_id": str(self.decision_policy_id),
            "worker_name": self.worker_name,
            "worker_version": self.worker_version,
            "solver_status": self.solver_status.value,
            "best_objective": rv(self.best_objective),
            "best_bound": rv(self.best_bound),
            "gap": rv(self.gap),
            "selected_action_id": self.selected_action_id,
            "action_surface_complete": self.action_surface_complete,
            "tie_break_policy_id": self.tie_break_policy_id,
            "solver_input_artifact_id": self.solver_input_artifact_id,
            "solver_output_artifact_id": self.solver_output_artifact_id,
            "worker_artifact_id": self.worker_artifact_id,
        }

    @property
    def certificate_id(self) -> ReferenceSolverCertificateId:
        return ReferenceSolverCertificateId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class IndependentAssuranceReport:
    decision_id: DecisionId
    mechanics_certificate_id: ReferenceMechanicsCertificateId
    mechanics_passed: bool
    solver_certificate_id: ReferenceSolverCertificateId | None
    solver_parity_status: AssuranceParityStatus
    blockers: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported IndependentAssuranceReport schema_version")
        if not isinstance(self.mechanics_passed, bool):
            raise ValueError("mechanics_passed must be boolean")
        if not isinstance(self.solver_parity_status, AssuranceParityStatus):
            raise ValueError("solver parity status must be typed")
        blockers = tuple(str(item).strip() for item in self.blockers if str(item).strip())
        artifacts = tuple(sorted({_artifact_id(item, label="independent assurance source artifact") for item in self.source_artifact_ids}))
        if not artifacts:
            raise ValueError("independent assurance report requires immutable source evidence")
        if not self.mechanics_passed and not blockers:
            raise ValueError("failed mechanics assurance requires blocker detail")
        if self.solver_parity_status is AssuranceParityStatus.FAIL and not blockers:
            raise ValueError("failed solver parity requires blocker detail")
        if self.solver_certificate_id is None and self.solver_parity_status is not AssuranceParityStatus.INCONCLUSIVE:
            raise ValueError("missing solver certificate must remain INCONCLUSIVE")
        if self.publication_eligible and blockers:
            raise ValueError("publication-eligible assurance cannot carry blockers")
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "source_artifact_ids", artifacts)

    @property
    def publication_eligible(self) -> bool:
        return self.mechanics_passed and self.solver_parity_status is AssuranceParityStatus.PASS

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-independent-assurance-report",
            "schema_version": self.schema_version,
            "decision_id": str(self.decision_id),
            "mechanics_certificate_id": str(self.mechanics_certificate_id),
            "mechanics_passed": self.mechanics_passed,
            "solver_certificate_id": None if self.solver_certificate_id is None else str(self.solver_certificate_id),
            "solver_parity_status": self.solver_parity_status.value,
            "blockers": list(self.blockers),
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def report_id(self) -> IndependentAssuranceReportId:
        return IndependentAssuranceReportId(canonical_sha256(self.semantic_payload()))
