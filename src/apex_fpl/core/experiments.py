"""Dependency-free empirical experiment and qualification contracts for Apex V2.

Empirical production claims must not become true merely because an arbitrary immutable
artifact exists. This module separates the stable pre-qualification subject identity,
a predeclared experiment, its immutable result, and the derived qualification
certificate. Control-layer replay is responsible for re-deriving certificates from the
retained definition/result evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import gcd
from typing import Mapping

from .canonical import canonical_sha256
from .production_proof_contract import PRODUCTION_EMPIRICAL_SUBJECT_KIND


def _text(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _aware_iso(value: str, *, label: str) -> str:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _artifact_id(value: str, *, label: str) -> str:
    text = _text(value, label=label)
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} has invalid sha256 digest") from exc
    return text


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be nonnegative integer")
    return value


def _artifact_tuple(values: tuple[str, ...], *, label: str) -> tuple[str, ...]:
    normalized = tuple(sorted({_artifact_id(value, label=label) for value in values}))
    if not normalized:
        raise ValueError(f"{label} requires at least one artifact")
    return normalized


def _validate_production_empirical_subject(proof_id: str, subject_kind: str) -> None:
    expected = PRODUCTION_EMPIRICAL_SUBJECT_KIND.get(proof_id)
    if expected is not None and subject_kind != expected:
        raise ValueError(
            "production empirical proof subject_kind does not match constitutional contract: "
            f"{proof_id} requires {expected!r}, found {subject_kind!r}"
        )


def qualification_subject_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Return stable candidate semantics before qualification is attached.

    Existing V2 candidate identities intentionally include qualification state/artifact.
    A qualification certificate cannot target that final identity without a content cycle,
    because the final identity would itself depend on the certificate artifact ID. The
    subject identity therefore removes only the qualification fields while preserving all
    model/policy/worker semantics that are actually being qualified.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("qualification subject payload must be mapping")
    cleaned = {
        str(key): value
        for key, value in payload.items()
        if str(key) not in {"qualification_state", "qualification_artifact_id"}
    }
    if not cleaned:
        raise ValueError("qualification subject payload cannot be empty")
    return cleaned


def qualification_subject_id(payload: Mapping[str, object]) -> str:
    return canonical_sha256(
        {
            "schema_name": "apex-qualification-subject",
            "schema_version": 1,
            "subject": qualification_subject_payload(payload),
        }
    )


class QualificationMetricDirection(StrEnum):
    AT_MOST = "AT_MOST"
    AT_LEAST = "AT_LEAST"
    ABS_AT_MOST = "ABS_AT_MOST"


class EmpiricalQualificationDecision(StrEnum):
    SUPPORTED = "SUPPORTED"
    REJECTED = "REJECTED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True, slots=True)
class ExactQualificationValue:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise ValueError("qualification numerator must be integer")
        if isinstance(self.denominator, bool) or not isinstance(self.denominator, int):
            raise ValueError("qualification denominator must be integer")
        if self.denominator == 0:
            raise ValueError("qualification denominator cannot be zero")
        numerator = self.numerator
        denominator = self.denominator
        if denominator < 0:
            numerator *= -1
            denominator *= -1
        divisor = gcd(abs(numerator), denominator)
        object.__setattr__(self, "numerator", numerator // divisor)
        object.__setattr__(self, "denominator", denominator // divisor)

    def semantic_payload(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}

    def compare(self, other: "ExactQualificationValue") -> int:
        left = self.numerator * other.denominator
        right = other.numerator * self.denominator
        return (left > right) - (left < right)

    def absolute(self) -> "ExactQualificationValue":
        return ExactQualificationValue(abs(self.numerator), self.denominator)


@dataclass(frozen=True, slots=True)
class QualificationMetricRule:
    metric_id: str
    direction: QualificationMetricDirection
    threshold: ExactQualificationValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _text(self.metric_id, label="metric_id"))

    def semantic_payload(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "direction": self.direction.value,
            "threshold": self.threshold.semantic_payload(),
        }

    def satisfied_by(self, value: ExactQualificationValue) -> bool:
        candidate = (
            value.absolute()
            if self.direction is QualificationMetricDirection.ABS_AT_MOST
            else value
        )
        threshold = (
            self.threshold.absolute()
            if self.direction is QualificationMetricDirection.ABS_AT_MOST
            else self.threshold
        )
        comparison = candidate.compare(threshold)
        if self.direction in {
            QualificationMetricDirection.AT_MOST,
            QualificationMetricDirection.ABS_AT_MOST,
        }:
            return comparison <= 0
        return comparison >= 0


@dataclass(frozen=True, slots=True)
class QualificationMetricResult:
    metric_id: str
    value: ExactQualificationValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_id", _text(self.metric_id, label="metric_id"))

    def semantic_payload(self) -> dict[str, object]:
        return {"metric_id": self.metric_id, "value": self.value.semantic_payload()}


@dataclass(frozen=True, slots=True)
class ExperimentDefinition:
    proof_id: str
    subject_kind: str
    subject_id: str
    season: str
    evaluator_artifact_id: str
    policy_artifact_id: str
    declared_at: str
    evaluation_window_start: str
    evaluation_window_end: str
    minimum_sample_size: int
    metric_rules: tuple[QualificationMetricRule, ...]
    valid_until: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ExperimentDefinition schema_version")
        for label in ("proof_id", "subject_kind", "subject_id", "season"):
            object.__setattr__(self, label, _text(getattr(self, label), label=label))
        _validate_production_empirical_subject(self.proof_id, self.subject_kind)
        object.__setattr__(
            self,
            "evaluator_artifact_id",
            _artifact_id(self.evaluator_artifact_id, label="experiment evaluator artifact"),
        )
        object.__setattr__(
            self,
            "policy_artifact_id",
            _artifact_id(self.policy_artifact_id, label="experiment policy artifact"),
        )
        declared = _aware_iso(self.declared_at, label="experiment declared_at")
        start = _aware_iso(
            self.evaluation_window_start,
            label="experiment evaluation_window_start",
        )
        end = _aware_iso(
            self.evaluation_window_end,
            label="experiment evaluation_window_end",
        )
        valid_until = _aware_iso(self.valid_until, label="experiment valid_until")
        if _instant(declared) > _instant(start):
            raise ValueError("experiment must be predeclared before evaluation window starts")
        if _instant(start) >= _instant(end):
            raise ValueError("experiment evaluation window must have positive duration")
        if _instant(end) > _instant(valid_until):
            raise ValueError("experiment validity cannot end before evaluation window")
        rules = tuple(sorted(self.metric_rules, key=lambda row: row.metric_id))
        if not rules:
            raise ValueError("experiment requires at least one qualification metric rule")
        metric_ids = [row.metric_id for row in rules]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("experiment contains duplicate qualification metric rules")
        object.__setattr__(
            self,
            "minimum_sample_size",
            _positive_int(self.minimum_sample_size, label="minimum_sample_size"),
        )
        object.__setattr__(self, "metric_rules", rules)
        object.__setattr__(self, "declared_at", declared)
        object.__setattr__(self, "evaluation_window_start", start)
        object.__setattr__(self, "evaluation_window_end", end)
        object.__setattr__(self, "valid_until", valid_until)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-experiment-definition",
            "schema_version": self.schema_version,
            "proof_id": self.proof_id,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "season": self.season,
            "evaluator_artifact_id": self.evaluator_artifact_id,
            "policy_artifact_id": self.policy_artifact_id,
            "declared_at": self.declared_at,
            "evaluation_window_start": self.evaluation_window_start,
            "evaluation_window_end": self.evaluation_window_end,
            "minimum_sample_size": self.minimum_sample_size,
            "metric_rules": [row.semantic_payload() for row in self.metric_rules],
            "valid_until": self.valid_until,
        }

    @property
    def experiment_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ExperimentResult:
    experiment_id: str
    proof_id: str
    subject_kind: str
    subject_id: str
    season: str
    evaluator_artifact_id: str
    evaluated_at: str
    sample_size: int
    metrics: tuple[QualificationMetricResult, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ExperimentResult schema_version")
        for label in ("experiment_id", "proof_id", "subject_kind", "subject_id", "season"):
            object.__setattr__(self, label, _text(getattr(self, label), label=label))
        _validate_production_empirical_subject(self.proof_id, self.subject_kind)
        object.__setattr__(
            self,
            "evaluator_artifact_id",
            _artifact_id(self.evaluator_artifact_id, label="result evaluator artifact"),
        )
        object.__setattr__(
            self,
            "evaluated_at",
            _aware_iso(self.evaluated_at, label="result evaluated_at"),
        )
        object.__setattr__(
            self,
            "sample_size",
            _nonnegative_int(self.sample_size, label="sample_size"),
        )
        metrics = tuple(sorted(self.metrics, key=lambda row: row.metric_id))
        metric_ids = [row.metric_id for row in metrics]
        if len(metric_ids) != len(set(metric_ids)):
            raise ValueError("experiment result contains duplicate metric results")
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(
            self,
            "source_artifact_ids",
            _artifact_tuple(self.source_artifact_ids, label="experiment source artifact"),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-experiment-result",
            "schema_version": self.schema_version,
            "experiment_id": self.experiment_id,
            "proof_id": self.proof_id,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "season": self.season,
            "evaluator_artifact_id": self.evaluator_artifact_id,
            "evaluated_at": self.evaluated_at,
            "sample_size": self.sample_size,
            "metrics": [row.semantic_payload() for row in self.metrics],
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def result_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class EmpiricalQualificationCertificate:
    proof_id: str
    subject_kind: str
    subject_id: str
    season: str
    experiment_id: str
    experiment_definition_artifact_id: str
    result_id: str
    result_artifact_id: str
    decision: EmpiricalQualificationDecision
    blockers: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    first_available_at: str
    valid_until: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported EmpiricalQualificationCertificate schema_version")
        for label in (
            "proof_id",
            "subject_kind",
            "subject_id",
            "season",
            "experiment_id",
            "result_id",
        ):
            object.__setattr__(self, label, _text(getattr(self, label), label=label))
        _validate_production_empirical_subject(self.proof_id, self.subject_kind)
        object.__setattr__(
            self,
            "experiment_definition_artifact_id",
            _artifact_id(
                self.experiment_definition_artifact_id,
                label="experiment definition artifact",
            ),
        )
        object.__setattr__(
            self,
            "result_artifact_id",
            _artifact_id(self.result_artifact_id, label="experiment result artifact"),
        )
        blockers = tuple(str(item).strip() for item in self.blockers if str(item).strip())
        if self.decision is EmpiricalQualificationDecision.SUPPORTED and blockers:
            raise ValueError("supported empirical qualification cannot contain blockers")
        if self.decision is not EmpiricalQualificationDecision.SUPPORTED and not blockers:
            raise ValueError("non-supported empirical qualification requires blocker")
        first = _aware_iso(
            self.first_available_at,
            label="qualification first_available_at",
        )
        valid_until = _aware_iso(self.valid_until, label="qualification valid_until")
        if _instant(first) >= _instant(valid_until):
            raise ValueError("qualification validity window must have positive duration")
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(
            self,
            "source_artifact_ids",
            _artifact_tuple(self.source_artifact_ids, label="qualification source artifact"),
        )
        object.__setattr__(self, "first_available_at", first)
        object.__setattr__(self, "valid_until", valid_until)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-empirical-qualification-certificate",
            "schema_version": self.schema_version,
            "proof_id": self.proof_id,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "season": self.season,
            "experiment_id": self.experiment_id,
            "experiment_definition_artifact_id": self.experiment_definition_artifact_id,
            "result_id": self.result_id,
            "result_artifact_id": self.result_artifact_id,
            "decision": self.decision.value,
            "blockers": list(self.blockers),
            "source_artifact_ids": list(self.source_artifact_ids),
            "first_available_at": self.first_available_at,
            "valid_until": self.valid_until,
        }

    @property
    def certificate_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    @property
    def supported(self) -> bool:
        return self.decision is EmpiricalQualificationDecision.SUPPORTED
