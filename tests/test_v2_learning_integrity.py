from __future__ import annotations

import pytest

from apex_fpl.core.ids import (
    EvaluationDatasetId,
    EvaluationObservationSetId,
    EvaluationRealizedTruthSetId,
    EvaluationTruthSetId,
    LearningPolicyId,
    ModelArtifactId,
    TrainingRunId,
)
from apex_fpl.core.learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningEvaluationStatus,
    LearningPolicyQualification,
    LearningUseMode,
    MetricDirection,
)
from apex_fpl.core.learning_evaluation import (
    EvaluationMetricResult,
    MetricComparisonResult,
    ModelEvaluationReport,
)
from apex_fpl.core.learning_policy import LearningEvaluationPolicy, MetricPromotionRule, MetricRequirement
from apex_fpl.core.outcome_truth import OutcomeTarget

ARTIFACT = "sha256:" + "a" * 64


def _metric_result() -> EvaluationMetricResult:
    return EvaluationMetricResult(
        metric=EvaluationMetric.MINUTES_MAE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        direction=MetricDirection.LOWER_IS_BETTER,
        sample_count=10,
        value=ExactMetricValue(3),
        interval_lower=None,
        interval_upper=None,
        source_artifact_ids=(ARTIFACT,),
    )


def test_evaluation_metric_rejects_non_exact_value_and_interval() -> None:
    with pytest.raises(ValueError, match="must be ExactMetricValue"):
        EvaluationMetricResult(
            metric=EvaluationMetric.MINUTES_MAE,
            target=OutcomeTarget.MINUTES,
            cohort="ALL",
            direction=MetricDirection.LOWER_IS_BETTER,
            sample_count=10,
            value=3,  # type: ignore[arg-type]
            interval_lower=None,
            interval_upper=None,
            source_artifact_ids=(ARTIFACT,),
        )

    with pytest.raises(ValueError, match="interval lower"):
        EvaluationMetricResult(
            metric=EvaluationMetric.MINUTES_MAE,
            target=OutcomeTarget.MINUTES,
            cohort="ALL",
            direction=MetricDirection.LOWER_IS_BETTER,
            sample_count=10,
            value=ExactMetricValue(3),
            interval_lower=1,  # type: ignore[arg-type]
            interval_upper=ExactMetricValue(5),
            source_artifact_ids=(ARTIFACT,),
        )


def test_metric_comparison_rejects_forged_improvement_arithmetic() -> None:
    with pytest.raises(ValueError, match="does not reconcile"):
        MetricComparisonResult(
            metric=EvaluationMetric.MINUTES_MAE,
            target=OutcomeTarget.MINUTES,
            cohort="ALL",
            direction=MetricDirection.LOWER_IS_BETTER,
            candidate_value=ExactMetricValue(3),
            incumbent_value=ExactMetricValue(7),
            improvement=ExactMetricValue(99),
            candidate_sample_count=10,
            incumbent_sample_count=10,
            interval_superiority=None,
        )

    valid = MetricComparisonResult(
        metric=EvaluationMetric.MINUTES_MAE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        direction=MetricDirection.LOWER_IS_BETTER,
        candidate_value=ExactMetricValue(3),
        incumbent_value=ExactMetricValue(7),
        improvement=ExactMetricValue(4),
        candidate_sample_count=10,
        incumbent_sample_count=10,
        interval_superiority=None,
    )
    assert valid.improvement == ExactMetricValue(4)


def test_model_evaluation_report_rejects_untyped_status_and_ids() -> None:
    kwargs = {
        "candidate_model_id": ModelArtifactId("candidate"),
        "training_run_id": TrainingRunId("training"),
        "evaluation_dataset_id": EvaluationDatasetId("dataset"),
        "evaluation_truth_set_id": EvaluationTruthSetId("truth"),
        "evaluation_realized_truth_set_id": EvaluationRealizedTruthSetId("realized"),
        "observation_set_id": EvaluationObservationSetId("observations"),
        "policy_id": LearningPolicyId("policy"),
        "use_mode": LearningUseMode.PRODUCTION,
        "metrics": (_metric_result(),),
        "status": LearningEvaluationStatus.COMPLETE,
        "blockers": (),
        "source_artifact_ids": (ARTIFACT,),
    }
    ModelEvaluationReport(**kwargs)

    with pytest.raises(ValueError, match="status must be typed"):
        ModelEvaluationReport(**{**kwargs, "status": "COMPLETE"})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="candidate_model_id must be typed"):
        ModelEvaluationReport(**{**kwargs, "candidate_model_id": "candidate"})  # type: ignore[arg-type]


def test_promotion_policy_rejects_non_exact_threshold_and_untyped_rows() -> None:
    requirement = MetricRequirement(
        metric=EvaluationMetric.MINUTES_MAE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        minimum_cases=10,
    )
    with pytest.raises(ValueError, match="must be ExactMetricValue"):
        MetricPromotionRule(
            metric=EvaluationMetric.MINUTES_MAE,
            target=OutcomeTarget.MINUTES,
            cohort="ALL",
            direction=MetricDirection.LOWER_IS_BETTER,
            minimum_improvement=1,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="requirements must be typed"):
        LearningEvaluationPolicy(
            policy_name="bad-policy",
            policy_version="v1",
            qualification_state=LearningPolicyQualification.SHADOW,
            qualification_artifact_id=None,
            promotion_rule_artifact_id=None,
            first_available_at="2026-08-01T00:00:00Z",
            valid_seasons=("2026-2027",),
            requirements=("bad",),  # type: ignore[arg-type]
            promotion_rules=(),
        )

    assert requirement.minimum_cases == 10
