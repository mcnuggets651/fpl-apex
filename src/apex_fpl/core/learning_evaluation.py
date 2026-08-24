"""Immutable model evaluation and comparison reports for Apex V2 Slice 11."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .ids import (
    EvaluationDatasetId,
    EvaluationObservationSetId,
    LearningPolicyId,
    ModelArtifactId,
    ModelComparisonId,
    ModelEvaluationId,
    TrainingRunId,
)
from .learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningEvaluationStatus,
    MetricDirection,
    artifact_id,
    positive_int,
)
from .outcome_truth import OutcomeTarget


@dataclass(frozen=True, slots=True)
class EvaluationMetricResult:
    metric: EvaluationMetric
    target: OutcomeTarget
    cohort: str
    direction: MetricDirection
    sample_count: int
    value: ExactMetricValue
    interval_lower: ExactMetricValue | None
    interval_upper: ExactMetricValue | None
    source_artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.metric, EvaluationMetric):
            raise ValueError("evaluation metric must be typed")
        if not isinstance(self.target, OutcomeTarget):
            raise ValueError("metric target must be typed OutcomeTarget")
        if not isinstance(self.direction, MetricDirection):
            raise ValueError("metric direction must be typed")
        cohort = str(self.cohort).strip()
        if not cohort:
            raise ValueError("metric cohort cannot be empty")
        positive_int(self.sample_count, label="metric sample_count")
        if (self.interval_lower is None) != (self.interval_upper is None):
            raise ValueError("metric interval must provide both lower and upper bounds")
        if self.interval_lower is not None and self.interval_upper is not None:
            if self.interval_lower.as_fraction() > self.interval_upper.as_fraction():
                raise ValueError("metric interval lower bound exceeds upper bound")
        sources = tuple(sorted({artifact_id(item, label="metric source artifact") for item in self.source_artifact_ids}))
        if not sources:
            raise ValueError("evaluation metric requires immutable source evidence")
        object.__setattr__(self, "cohort", cohort)
        object.__setattr__(self, "source_artifact_ids", sources)

    @property
    def key(self) -> tuple[EvaluationMetric, OutcomeTarget, str]:
        return self.metric, self.target, self.cohort

    def semantic_payload(self) -> dict[str, object]:
        def value_payload(value: ExactMetricValue | None) -> dict[str, int] | None:
            return None if value is None else value.semantic_payload()

        return {
            "metric": self.metric.value,
            "target": self.target.value,
            "cohort": self.cohort,
            "direction": self.direction.value,
            "sample_count": self.sample_count,
            "value": self.value.semantic_payload(),
            "interval_lower": value_payload(self.interval_lower),
            "interval_upper": value_payload(self.interval_upper),
            "source_artifact_ids": list(self.source_artifact_ids),
        }


@dataclass(frozen=True, slots=True)
class ModelEvaluationReport:
    candidate_model_id: ModelArtifactId
    training_run_id: TrainingRunId
    evaluation_dataset_id: EvaluationDatasetId
    observation_set_id: EvaluationObservationSetId
    policy_id: LearningPolicyId
    metrics: tuple[EvaluationMetricResult, ...]
    status: LearningEvaluationStatus
    blockers: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported ModelEvaluationReport schema_version")
        if not isinstance(self.status, LearningEvaluationStatus):
            raise ValueError("model evaluation status must be typed")
        metrics = tuple(sorted(self.metrics, key=lambda row: (row.metric.value, row.target.value, row.cohort)))
        if len({row.key for row in metrics}) != len(metrics):
            raise ValueError("model evaluation contains duplicate metric/cohort rows")
        blockers = tuple(str(item).strip() for item in self.blockers if str(item).strip())
        sources = tuple(sorted({artifact_id(item, label="model evaluation source artifact") for item in self.source_artifact_ids}))
        metric_sources = {item for row in metrics for item in row.source_artifact_ids}
        if not metric_sources.issubset(set(sources)):
            raise ValueError("model evaluation lineage must include all metric source artifacts")
        if self.status is LearningEvaluationStatus.COMPLETE:
            if blockers or not metrics:
                raise ValueError("COMPLETE model evaluation requires metrics and no blockers")
        elif not blockers:
            raise ValueError(f"{self.status.value} model evaluation requires blocker detail")
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-evaluation-report",
            "schema_version": self.schema_version,
            "candidate_model_id": str(self.candidate_model_id),
            "training_run_id": str(self.training_run_id),
            "evaluation_dataset_id": str(self.evaluation_dataset_id),
            "observation_set_id": str(self.observation_set_id),
            "policy_id": str(self.policy_id),
            "metrics": [row.semantic_payload() for row in self.metrics],
            "status": self.status.value,
            "blockers": list(self.blockers),
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def evaluation_id(self) -> ModelEvaluationId:
        return ModelEvaluationId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class MetricComparisonResult:
    metric: EvaluationMetric
    target: OutcomeTarget
    cohort: str
    direction: MetricDirection
    candidate_value: ExactMetricValue
    incumbent_value: ExactMetricValue
    improvement: ExactMetricValue
    candidate_sample_count: int
    incumbent_sample_count: int
    interval_superiority: bool | None

    def __post_init__(self) -> None:
        if not isinstance(self.metric, EvaluationMetric) or not isinstance(self.target, OutcomeTarget):
            raise ValueError("metric comparison requires typed metric and target")
        if not isinstance(self.direction, MetricDirection):
            raise ValueError("metric comparison direction must be typed")
        cohort = str(self.cohort).strip()
        if not cohort:
            raise ValueError("metric comparison cohort cannot be empty")
        positive_int(self.candidate_sample_count, label="candidate sample count")
        positive_int(self.incumbent_sample_count, label="incumbent sample count")
        if self.interval_superiority is not None and not isinstance(self.interval_superiority, bool):
            raise ValueError("interval_superiority must be boolean or None")
        object.__setattr__(self, "cohort", cohort)

    @property
    def key(self) -> tuple[EvaluationMetric, OutcomeTarget, str]:
        return self.metric, self.target, self.cohort

    def semantic_payload(self) -> dict[str, object]:
        return {
            "metric": self.metric.value,
            "target": self.target.value,
            "cohort": self.cohort,
            "direction": self.direction.value,
            "candidate_value": self.candidate_value.semantic_payload(),
            "incumbent_value": self.incumbent_value.semantic_payload(),
            "improvement": self.improvement.semantic_payload(),
            "candidate_sample_count": self.candidate_sample_count,
            "incumbent_sample_count": self.incumbent_sample_count,
            "interval_superiority": self.interval_superiority,
        }


@dataclass(frozen=True, slots=True)
class ModelComparisonReport:
    candidate_model_id: ModelArtifactId
    incumbent_model_id: ModelArtifactId
    candidate_evaluation_id: ModelEvaluationId
    incumbent_evaluation_id: ModelEvaluationId
    policy_id: LearningPolicyId
    comparisons: tuple[MetricComparisonResult, ...]
    status: LearningEvaluationStatus
    blockers: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ModelComparisonReport schema_version")
        if self.candidate_model_id == self.incumbent_model_id:
            raise ValueError("comparison candidate cannot equal incumbent")
        comparisons = tuple(sorted(self.comparisons, key=lambda row: (row.metric.value, row.target.value, row.cohort)))
        if len({row.key for row in comparisons}) != len(comparisons):
            raise ValueError("model comparison contains duplicate metric/cohort rows")
        blockers = tuple(str(item).strip() for item in self.blockers if str(item).strip())
        sources = tuple(sorted({artifact_id(item, label="model comparison source artifact") for item in self.source_artifact_ids}))
        if not sources:
            raise ValueError("model comparison requires immutable source evidence")
        if self.status is LearningEvaluationStatus.COMPLETE:
            if blockers or not comparisons:
                raise ValueError("COMPLETE model comparison requires comparison rows and no blockers")
        elif not blockers:
            raise ValueError(f"{self.status.value} model comparison requires blocker detail")
        object.__setattr__(self, "comparisons", comparisons)
        object.__setattr__(self, "blockers", blockers)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-comparison-report",
            "schema_version": self.schema_version,
            "candidate_model_id": str(self.candidate_model_id),
            "incumbent_model_id": str(self.incumbent_model_id),
            "candidate_evaluation_id": str(self.candidate_evaluation_id),
            "incumbent_evaluation_id": str(self.incumbent_evaluation_id),
            "policy_id": str(self.policy_id),
            "comparisons": [row.semantic_payload() for row in self.comparisons],
            "status": self.status.value,
            "blockers": list(self.blockers),
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def comparison_id(self) -> ModelComparisonId:
        return ModelComparisonId(canonical_sha256(self.semantic_payload()))
