"""No-hindsight replay, evaluation and model-promotion contracts for Apex V2 Slice 11.

Learning is offline. These dependency-free types preserve the separation between a
training run, a prediction sealed before an outcome, the later truth join, an evaluation
report, and any subsequent promotion decision. Evaluation never mutates a production
registry by itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import gcd

from .canonical import canonical_sha256
from .identity import OfficialPlayerId
from .ids import (
    EvaluationDatasetId,
    FeatureSnapshotId,
    ForecastId,
    LearningPolicyId,
    ModelArtifactId,
    ModelEvaluationId,
    ModelPromotionId,
    ModelRegistryGenerationId,
    OutcomeTruthRegistryId,
    TrainingRunId,
)
from .outcome_truth import OutcomeTarget


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


def _aware_iso(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _point(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


@dataclass(frozen=True, slots=True)
class ExactMetricValue:
    """Exact reduced rational used for durable evaluation metrics."""

    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise ValueError("metric numerator must be integer")
        if (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, int)
            or self.denominator <= 0
        ):
            raise ValueError("metric denominator must be positive integer")
        divisor = gcd(abs(self.numerator), self.denominator)
        object.__setattr__(self, "numerator", self.numerator // divisor)
        object.__setattr__(self, "denominator", self.denominator // divisor)

    def semantic_payload(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


class LearningPolicyQualification(StrEnum):
    SHADOW = "SHADOW"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


class LearningEvaluationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"


class ModelPromotionDecision(StrEnum):
    PROMOTE = "PROMOTE"
    RETAIN = "RETAIN"
    INCONCLUSIVE = "INCONCLUSIVE"


class MetricDirection(StrEnum):
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"


class EvaluationMetric(StrEnum):
    START_BRIER = "START_BRIER"
    MINUTES_MAE = "MINUTES_MAE"
    MINUTES_MSE = "MINUTES_MSE"
    POINTS_MAE = "POINTS_MAE"
    POINTS_MEAN_BIAS = "POINTS_MEAN_BIAS"
    INTERVAL_COVERAGE = "INTERVAL_COVERAGE"
    PREDICTION_COVERAGE = "PREDICTION_COVERAGE"
    DECISION_REALIZED_POINTS_DELTA = "DECISION_REALIZED_POINTS_DELTA"


@dataclass(frozen=True, slots=True)
class ModelTrainingRun:
    model_artifact_id: ModelArtifactId
    training_cutoff: str
    first_available_at: str
    training_dataset_artifact_ids: tuple[str, ...]
    trainer_code_artifact_id: str
    parameter_artifact_ids: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ModelTrainingRun schema_version")
        cutoff = _aware_iso(self.training_cutoff, label="training_cutoff")
        available = _aware_iso(self.first_available_at, label="training first_available_at")
        if _point(cutoff) > _point(available):
            raise ValueError("model cannot be available before its training cutoff")
        datasets = tuple(
            sorted({_artifact_id(item, label="training dataset artifact") for item in self.training_dataset_artifact_ids})
        )
        parameters = tuple(
            sorted({_artifact_id(item, label="training parameter artifact") for item in self.parameter_artifact_ids})
        )
        sources = tuple(
            sorted({_artifact_id(item, label="training source artifact") for item in self.source_artifact_ids})
        )
        trainer = _artifact_id(self.trainer_code_artifact_id, label="trainer code artifact")
        if not datasets or not parameters or not sources:
            raise ValueError("training run requires dataset, parameter and source artifacts")
        if not set(datasets).issubset(set(sources)):
            raise ValueError("training dataset artifacts must be included in source lineage")
        if not set(parameters).issubset(set(sources)):
            raise ValueError("training parameter artifacts must be included in source lineage")
        if trainer not in sources:
            raise ValueError("trainer code artifact must be included in source lineage")
        object.__setattr__(self, "training_cutoff", cutoff)
        object.__setattr__(self, "first_available_at", available)
        object.__setattr__(self, "training_dataset_artifact_ids", datasets)
        object.__setattr__(self, "parameter_artifact_ids", parameters)
        object.__setattr__(self, "trainer_code_artifact_id", trainer)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-training-run",
            "schema_version": self.schema_version,
            "model_artifact_id": str(self.model_artifact_id),
            "training_cutoff": self.training_cutoff,
            "first_available_at": self.first_available_at,
            "training_dataset_artifact_ids": list(self.training_dataset_artifact_ids),
            "trainer_code_artifact_id": self.trainer_code_artifact_id,
            "parameter_artifact_ids": list(self.parameter_artifact_ids),
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def training_run_id(self) -> TrainingRunId:
        return TrainingRunId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    forecast_id: ForecastId
    feature_snapshot_id: FeatureSnapshotId
    model_artifact_id: ModelArtifactId
    target: OutcomeTarget
    player_id: OfficialPlayerId
    gameweek: int
    prediction_sealed_at: str
    outcome_first_available_at: str
    prediction_artifact_id: str
    outcome_artifact_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, OutcomeTarget):
            raise ValueError("evaluation target must be typed OutcomeTarget")
        _positive_int(self.gameweek, label="evaluation gameweek")
        predicted = _aware_iso(self.prediction_sealed_at, label="prediction_sealed_at")
        outcome = _aware_iso(self.outcome_first_available_at, label="outcome_first_available_at")
        if _point(outcome) <= _point(predicted):
            raise ValueError("post-event outcome must become available strictly after prediction seal")
        prediction_artifact = _artifact_id(
            self.prediction_artifact_id,
            label="evaluation prediction artifact",
        )
        outcome_artifact = _artifact_id(
            self.outcome_artifact_id,
            label="evaluation outcome artifact",
        )
        if prediction_artifact == outcome_artifact:
            raise ValueError("prediction and outcome artifacts must be separate evidence")
        object.__setattr__(self, "prediction_sealed_at", predicted)
        object.__setattr__(self, "outcome_first_available_at", outcome)
        object.__setattr__(self, "prediction_artifact_id", prediction_artifact)
        object.__setattr__(self, "outcome_artifact_id", outcome_artifact)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "forecast_id": str(self.forecast_id),
            "feature_snapshot_id": str(self.feature_snapshot_id),
            "model_artifact_id": str(self.model_artifact_id),
            "target": self.target.value,
            "player_id": int(self.player_id),
            "gameweek": self.gameweek,
            "prediction_sealed_at": self.prediction_sealed_at,
            "outcome_first_available_at": self.outcome_first_available_at,
            "prediction_artifact_id": self.prediction_artifact_id,
            "outcome_artifact_id": self.outcome_artifact_id,
        }

    @property
    def case_id(self) -> str:
        return canonical_sha256({"schema_name": "apex-evaluation-case", **self.semantic_payload()})


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    season: str
    truth_registry_id: OutcomeTruthRegistryId
    cases: tuple[EvaluationCase, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported EvaluationDataset schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("evaluation dataset requires season")
        cases = tuple(
            sorted(
                self.cases,
                key=lambda row: (row.gameweek, int(row.player_id), row.target.value, row.case_id),
            )
        )
        if not cases:
            raise ValueError("evaluation dataset requires at least one case")
        case_ids = [row.case_id for row in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation dataset contains duplicate cases")
        models = {row.model_artifact_id for row in cases}
        if len(models) != 1:
            raise ValueError("one evaluation dataset must evaluate one exact model artifact")
        sources = tuple(
            sorted({_artifact_id(item, label="evaluation dataset source artifact") for item in self.source_artifact_ids})
        )
        required = {
            artifact
            for row in cases
            for artifact in (row.prediction_artifact_id, row.outcome_artifact_id)
        }
        if not required.issubset(set(sources)):
            raise ValueError("evaluation dataset lineage must include every prediction/outcome artifact")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "source_artifact_ids", sources)

    @property
    def model_artifact_id(self) -> ModelArtifactId:
        return self.cases[0].model_artifact_id

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-evaluation-dataset",
            "schema_version": self.schema_version,
            "season": self.season,
            "truth_registry_id": str(self.truth_registry_id),
            "cases": [row.semantic_payload() for row in self.cases],
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def dataset_id(self) -> EvaluationDatasetId:
        return EvaluationDatasetId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class LearningEvaluationPolicy:
    policy_name: str
    policy_version: str
    qualification_state: LearningPolicyQualification
    qualification_artifact_id: str | None
    first_available_at: str
    minimum_cases: int
    required_metrics: tuple[EvaluationMetric, ...]
    promotion_rule_artifact_id: str | None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported LearningEvaluationPolicy schema_version")
        for label in ("policy_name", "policy_version"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise ValueError(f"learning policy {label} cannot be empty")
            object.__setattr__(self, label, text)
        if not isinstance(self.qualification_state, LearningPolicyQualification):
            raise ValueError("learning policy qualification must be typed")
        _positive_int(self.minimum_cases, label="learning minimum_cases")
        metrics = tuple(sorted(set(self.required_metrics), key=lambda item: item.value))
        if not metrics:
            raise ValueError("learning policy requires at least one metric")
        available = _aware_iso(self.first_available_at, label="learning policy first_available_at")
        qualification = self.qualification_artifact_id
        if qualification is not None:
            qualification = _artifact_id(qualification, label="learning policy qualification artifact")
        rule = self.promotion_rule_artifact_id
        if rule is not None:
            rule = _artifact_id(rule, label="learning promotion rule artifact")
        if self.qualification_state is LearningPolicyQualification.QUALIFIED:
            if qualification is None or rule is None:
                raise ValueError("qualified learning policy requires qualification and promotion-rule artifacts")
        object.__setattr__(self, "required_metrics", metrics)
        object.__setattr__(self, "first_available_at", available)
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "promotion_rule_artifact_id", rule)

    @property
    def production_qualified(self) -> bool:
        return (
            self.qualification_state is LearningPolicyQualification.QUALIFIED
            and self.qualification_artifact_id is not None
            and self.promotion_rule_artifact_id is not None
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-learning-evaluation-policy",
            "schema_version": self.schema_version,
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "qualification_state": self.qualification_state.value,
            "qualification_artifact_id": self.qualification_artifact_id,
            "first_available_at": self.first_available_at,
            "minimum_cases": self.minimum_cases,
            "required_metrics": [item.value for item in self.required_metrics],
            "promotion_rule_artifact_id": self.promotion_rule_artifact_id,
        }

    @property
    def policy_id(self) -> LearningPolicyId:
        return LearningPolicyId(canonical_sha256(self.semantic_payload()))


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
        _positive_int(self.sample_count, label="metric sample_count")
        if (self.interval_lower is None) != (self.interval_upper is None):
            raise ValueError("metric interval must provide both lower and upper bounds")
        if self.interval_lower is not None and self.interval_upper is not None:
            lower = self.interval_lower.numerator * self.interval_upper.denominator
            upper = self.interval_upper.numerator * self.interval_lower.denominator
            if lower > upper:
                raise ValueError("metric interval lower bound exceeds upper bound")
        sources = tuple(
            sorted({_artifact_id(item, label="metric source artifact") for item in self.source_artifact_ids})
        )
        if not sources:
            raise ValueError("evaluation metric requires immutable source evidence")
        object.__setattr__(self, "cohort", cohort)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        def metric_value(value: ExactMetricValue | None) -> dict[str, int] | None:
            return None if value is None else value.semantic_payload()

        return {
            "metric": self.metric.value,
            "target": self.target.value,
            "cohort": self.cohort,
            "direction": self.direction.value,
            "sample_count": self.sample_count,
            "value": self.value.semantic_payload(),
            "interval_lower": metric_value(self.interval_lower),
            "interval_upper": metric_value(self.interval_upper),
            "source_artifact_ids": list(self.source_artifact_ids),
        }


@dataclass(frozen=True, slots=True)
class ModelEvaluationReport:
    candidate_model_id: ModelArtifactId
    baseline_model_id: ModelArtifactId | None
    training_run_id: TrainingRunId
    evaluation_dataset_id: EvaluationDatasetId
    policy_id: LearningPolicyId
    metrics: tuple[EvaluationMetricResult, ...]
    status: LearningEvaluationStatus
    blockers: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ModelEvaluationReport schema_version")
        if not isinstance(self.status, LearningEvaluationStatus):
            raise ValueError("model evaluation status must be typed")
        if self.baseline_model_id == self.candidate_model_id:
            raise ValueError("evaluation baseline cannot be the candidate model")
        metrics = tuple(
            sorted(
                self.metrics,
                key=lambda row: (row.metric.value, row.target.value, row.cohort),
            )
        )
        metric_keys = [(row.metric, row.target, row.cohort) for row in metrics]
        if len(metric_keys) != len(set(metric_keys)):
            raise ValueError("model evaluation contains duplicate metric/cohort rows")
        blockers = tuple(str(item).strip() for item in self.blockers if str(item).strip())
        sources = tuple(
            sorted({_artifact_id(item, label="model evaluation source artifact") for item in self.source_artifact_ids})
        )
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
            "baseline_model_id": None if self.baseline_model_id is None else str(self.baseline_model_id),
            "training_run_id": str(self.training_run_id),
            "evaluation_dataset_id": str(self.evaluation_dataset_id),
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
class ModelPromotionCertificate:
    candidate_model_id: ModelArtifactId
    incumbent_model_id: ModelArtifactId | None
    evaluation_id: ModelEvaluationId
    policy_id: LearningPolicyId
    decision: ModelPromotionDecision
    reason: str
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ModelPromotionCertificate schema_version")
        if not isinstance(self.decision, ModelPromotionDecision):
            raise ValueError("model promotion decision must be typed")
        if self.incumbent_model_id == self.candidate_model_id:
            raise ValueError("promotion candidate cannot equal incumbent")
        reason = str(self.reason).strip()
        if not reason:
            raise ValueError("model promotion certificate requires reason")
        sources = tuple(
            sorted({_artifact_id(item, label="model promotion source artifact") for item in self.source_artifact_ids})
        )
        if not sources:
            raise ValueError("model promotion certificate requires immutable source evidence")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-promotion-certificate",
            "schema_version": self.schema_version,
            "candidate_model_id": str(self.candidate_model_id),
            "incumbent_model_id": None if self.incumbent_model_id is None else str(self.incumbent_model_id),
            "evaluation_id": str(self.evaluation_id),
            "policy_id": str(self.policy_id),
            "decision": self.decision.value,
            "reason": self.reason,
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def promotion_id(self) -> ModelPromotionId:
        return ModelPromotionId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class ModelRegistryGeneration:
    season: str
    generation: int
    parent_generation_id: ModelRegistryGenerationId | None
    registered_model_ids: tuple[ModelArtifactId, ...]
    champion_model_id: ModelArtifactId | None
    promotion_id: ModelPromotionId | None
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ModelRegistryGeneration schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("model registry generation requires season")
        generation = _positive_int(self.generation, label="model registry generation")
        models = tuple(sorted(set(self.registered_model_ids), key=str))
        if not models:
            raise ValueError("model registry generation requires registered models")
        if generation == 1 and self.parent_generation_id is not None:
            raise ValueError("first model registry generation cannot have parent")
        if generation > 1 and self.parent_generation_id is None:
            raise ValueError("later model registry generation requires parent identity")
        if self.champion_model_id is not None:
            if self.champion_model_id not in models:
                raise ValueError("model registry champion must be registered")
            if self.promotion_id is None:
                raise ValueError("model registry champion requires promotion certificate identity")
        elif self.promotion_id is not None:
            raise ValueError("promotion certificate cannot exist without resulting champion")
        sources = tuple(
            sorted({_artifact_id(item, label="model registry generation source artifact") for item in self.source_artifact_ids})
        )
        if not sources:
            raise ValueError("model registry generation requires immutable source evidence")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "registered_model_ids", models)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-registry-generation",
            "schema_version": self.schema_version,
            "season": self.season,
            "generation": self.generation,
            "parent_generation_id": (
                None if self.parent_generation_id is None else str(self.parent_generation_id)
            ),
            "registered_model_ids": [str(item) for item in self.registered_model_ids],
            "champion_model_id": None if self.champion_model_id is None else str(self.champion_model_id),
            "promotion_id": None if self.promotion_id is None else str(self.promotion_id),
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def generation_id(self) -> ModelRegistryGenerationId:
        return ModelRegistryGenerationId(canonical_sha256(self.semantic_payload()))
