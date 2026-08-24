"""Exact normalized observations used by Slice 11 offline evaluation."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .ids import (
    EvaluationDatasetId,
    EvaluationObservationSetId,
    EvaluationRealizedTruthSetId,
    EvaluationTruthSetId,
)
from .learning_common import ExactMetricValue
from .outcome_truth import OutcomeTarget


def _exact(value: object, *, label: str) -> ExactMetricValue:
    if not isinstance(value, ExactMetricValue):
        raise ValueError(f"{label} must be ExactMetricValue")
    return value


@dataclass(frozen=True, slots=True)
class EvaluationObservation:
    case_id: str
    truth_case_id: str
    target: OutcomeTarget
    predicted_value: ExactMetricValue | None
    actual_value: ExactMetricValue
    interval_lower: ExactMetricValue | None = None
    interval_upper: ExactMetricValue | None = None

    def __post_init__(self) -> None:
        case_id = str(self.case_id).strip()
        truth_case_id = str(self.truth_case_id).strip()
        if not case_id or not truth_case_id:
            raise ValueError("evaluation observation requires case_id and truth_case_id")
        if not isinstance(self.target, OutcomeTarget):
            raise ValueError("evaluation observation target must be typed")
        if self.predicted_value is not None:
            _exact(self.predicted_value, label="evaluation predicted value")
        _exact(self.actual_value, label="evaluation actual value")
        if self.interval_lower is not None:
            _exact(self.interval_lower, label="evaluation interval lower")
        if self.interval_upper is not None:
            _exact(self.interval_upper, label="evaluation interval upper")
        if self.predicted_value is None and (
            self.interval_lower is not None or self.interval_upper is not None
        ):
            raise ValueError("missing prediction cannot carry a prediction interval")
        if (self.interval_lower is None) != (self.interval_upper is None):
            raise ValueError("evaluation observation interval requires both bounds")
        if self.interval_lower is not None and self.interval_upper is not None:
            if self.interval_lower.as_fraction() > self.interval_upper.as_fraction():
                raise ValueError("evaluation observation lower interval exceeds upper")
        object.__setattr__(self, "case_id", case_id)
        object.__setattr__(self, "truth_case_id", truth_case_id)

    @property
    def has_prediction(self) -> bool:
        return self.predicted_value is not None

    def realized_truth_payload(self) -> dict[str, object]:
        return {
            "truth_case_id": self.truth_case_id,
            "target": self.target.value,
            "actual_value": self.actual_value.semantic_payload(),
        }

    def semantic_payload(self) -> dict[str, object]:
        def metric(value: ExactMetricValue | None) -> dict[str, int] | None:
            return None if value is None else value.semantic_payload()

        return {
            "case_id": self.case_id,
            "truth_case_id": self.truth_case_id,
            "target": self.target.value,
            "predicted_value": metric(self.predicted_value),
            "actual_value": self.actual_value.semantic_payload(),
            "interval_lower": metric(self.interval_lower),
            "interval_upper": metric(self.interval_upper),
        }


@dataclass(frozen=True, slots=True)
class EvaluationObservationSet:
    evaluation_dataset_id: EvaluationDatasetId
    evaluation_truth_set_id: EvaluationTruthSetId
    observations: tuple[EvaluationObservation, ...]
    schema_version: int = 3

    def __post_init__(self) -> None:
        if self.schema_version != 3:
            raise ValueError("unsupported EvaluationObservationSet schema_version")
        if not isinstance(self.evaluation_dataset_id, EvaluationDatasetId):
            raise ValueError("evaluation observation set dataset ID must be typed")
        if not isinstance(self.evaluation_truth_set_id, EvaluationTruthSetId):
            raise ValueError("evaluation observation set truth-set ID must be typed")
        if any(not isinstance(row, EvaluationObservation) for row in self.observations):
            raise ValueError("evaluation observation set rows must be typed")
        observations = tuple(sorted(self.observations, key=lambda row: row.case_id))
        if not observations:
            raise ValueError("evaluation observation set cannot be empty")
        ids = [row.case_id for row in observations]
        if len(ids) != len(set(ids)):
            raise ValueError("evaluation observation set contains duplicate case IDs")
        truth_ids = [row.truth_case_id for row in observations]
        if len(truth_ids) != len(set(truth_ids)):
            raise ValueError("evaluation observation set contains duplicate truth-case IDs")
        object.__setattr__(self, "observations", observations)

    @property
    def realized_truth_set_id(self) -> EvaluationRealizedTruthSetId:
        model_independent_truth = sorted(
            (row.realized_truth_payload() for row in self.observations),
            key=lambda row: str(row["truth_case_id"]),
        )
        return EvaluationRealizedTruthSetId(
            canonical_sha256(
                {
                    "schema_name": "apex-evaluation-realized-truth-set",
                    "schema_version": 1,
                    "evaluation_truth_set_id": str(self.evaluation_truth_set_id),
                    "actuals": model_independent_truth,
                }
            )
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-evaluation-observation-set",
            "schema_version": self.schema_version,
            "evaluation_dataset_id": str(self.evaluation_dataset_id),
            "evaluation_truth_set_id": str(self.evaluation_truth_set_id),
            "realized_truth_set_id": str(self.realized_truth_set_id),
            "observations": [row.semantic_payload() for row in self.observations],
        }

    @property
    def observation_set_id(self) -> EvaluationObservationSetId:
        return EvaluationObservationSetId(canonical_sha256(self.semantic_payload()))
