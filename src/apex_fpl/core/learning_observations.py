"""Exact normalized observations used by Slice 11 offline evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .ids import EvaluationDatasetId, EvaluationObservationSetId
from .learning import ExactMetricValue
from .outcome_truth import OutcomeTarget


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    case_id: str
    target: OutcomeTarget
    predicted_value: ExactMetricValue
    actual_value: ExactMetricValue
    interval_lower: ExactMetricValue | None = None
    interval_upper: ExactMetricValue | None = None

    def __post_init__(self) -> None:
        case_id = str(self.case_id).strip()
        if not case_id:
            raise ValueError("evaluation observation requires case_id")
        if not isinstance(self.target, OutcomeTarget):
            raise ValueError("evaluation observation target must be typed")
        if (self.interval_lower is None) != (self.interval_upper is None):
            raise ValueError("evaluation observation interval requires both bounds")
        if self.interval_lower is not None and self.interval_upper is not None:
            lower = self.interval_lower.numerator * self.interval_upper.denominator
            upper = self.interval_upper.numerator * self.interval_lower.denominator
            if lower > upper:
                raise ValueError("evaluation observation lower interval exceeds upper")
        object.__setattr__(self, "case_id", case_id)

    def semantic_payload(self) -> dict[str, object]:
        def metric(value: ExactMetricValue | None) -> dict[str, int] | None:
            return None if value is None else value.semantic_payload()

        return {
            "case_id": self.case_id,
            "target": self.target.value,
            "predicted_value": self.predicted_value.semantic_payload(),
            "actual_value": self.actual_value.semantic_payload(),
            "interval_lower": metric(self.interval_lower),
            "interval_upper": metric(self.interval_upper),
        }


@dataclass(frozen=True, slots=True)
class EvaluationObservationSet:
    evaluation_dataset_id: EvaluationDatasetId
    observations: tuple[EvaluationObservation, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported EvaluationObservationSet schema_version")
        observations = tuple(sorted(self.observations, key=lambda row: row.case_id))
        if not observations:
            raise ValueError("evaluation observation set cannot be empty")
        ids = [row.case_id for row in observations]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation observation set contains duplicate case IDs")
        object.__setattr__(self, "observations", observations)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-evaluation-observation-set",
            "schema_version": self.schema_version,
            "evaluation_dataset_id": str(self.evaluation_dataset_id),
            "observations": [row.semantic_payload() for row in self.observations],
        }

    @property
    def observation_set_id(self) -> EvaluationObservationSetId:
        return EvaluationObservationSetId(canonical_sha256(self.semantic_payload()))
