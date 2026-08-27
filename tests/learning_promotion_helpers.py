from __future__ import annotations

from dataclasses import replace

import yaml

from apex_fpl.control.empirical_qualification_admission import LEARNING_POLICY_QUALIFICATION_ID
from apex_fpl.control.learning_policy_registry import LearningPolicyRegistry
from apex_fpl.control.learning_promotion import (
    apply_model_promotion,
    compare_model_evaluations,
    issue_model_promotion_certificate,
)
from apex_fpl.control.learning_store import store_learning_object
from apex_fpl.core.ids import (
    EvaluationDatasetId,
    EvaluationObservationSetId,
    EvaluationRealizedTruthSetId,
    EvaluationTruthSetId,
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
from apex_fpl.core.learning_evaluation import EvaluationMetricResult, ModelEvaluationReport
from apex_fpl.core.learning_policy import (
    LearningEvaluationPolicy,
    MetricPromotionRule,
    MetricRequirement,
)
from apex_fpl.core.learning_promotion import ModelRegistryGeneration
from apex_fpl.core.outcome_truth import OutcomeTarget

from empirical_qualification_helpers import synthetic_supported_qualification_artifact


def _source_id(store, label: str) -> str:
    return store.put_bytes(f"synthetic-learning-promotion:{label}".encode()).artifact_id


def _policy_bundle(*, store, season: str):
    rule_artifact = _source_id(store, "promotion-rules")
    requirement = MetricRequirement(
        metric=EvaluationMetric.MINUTES_MAE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        minimum_cases=2,
        require_interval=False,
    )
    rule = MetricPromotionRule(
        metric=EvaluationMetric.MINUTES_MAE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        direction=MetricDirection.LOWER_IS_BETTER,
        minimum_improvement=ExactMetricValue(2),
        require_interval_superiority=False,
    )
    policy = LearningEvaluationPolicy(
        policy_name="synthetic-champion-learning-policy",
        policy_version="1",
        qualification_state=LearningPolicyQualification.QUALIFIED,
        qualification_artifact_id=_source_id(store, "qualification-placeholder"),
        promotion_rule_artifact_id=rule_artifact,
        first_available_at="2026-08-01T00:00:00Z",
        valid_seasons=(season,),
        requirements=(requirement,),
        promotion_rules=(rule,),
    )
    qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=policy.semantic_payload(),
        subject_kind="apex.learning-policy",
        proof_id=LEARNING_POLICY_QUALIFICATION_ID,
        season=season,
        valid_until="2026-10-31T00:00:00Z",
    )
    policy = replace(policy, qualification_artifact_id=qualification)
    store_learning_object(policy, store=store)
    registry = LearningPolicyRegistry(
        season=season,
        policies=(policy,),
        champion_policy_id=policy.policy_id,
    )
    payload = {
        "schema_version": 1,
        "season": season,
        "champion_policy_id": str(policy.policy_id),
        "policies": [policy.semantic_payload()],
    }
    registry_artifact = store.put_bytes(
        yaml.safe_dump(payload, sort_keys=True).encode("utf-8")
    ).artifact_id
    return policy, registry, registry_artifact


def _evaluation(
    *,
    store,
    model_id: ModelArtifactId,
    policy,
    truth_set_id: EvaluationTruthSetId,
    realized_truth_set_id: EvaluationRealizedTruthSetId,
    value: int,
    label: str,
):
    metric_source = _source_id(store, f"{label}-metric-source")
    metric = EvaluationMetricResult(
        metric=EvaluationMetric.MINUTES_MAE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        direction=MetricDirection.LOWER_IS_BETTER,
        sample_count=2,
        value=ExactMetricValue(value),
        interval_lower=None,
        interval_upper=None,
        source_artifact_ids=(metric_source,),
    )
    report = ModelEvaluationReport(
        candidate_model_id=model_id,
        training_run_id=TrainingRunId(_source_id(store, f"{label}-training-run")),
        evaluation_dataset_id=EvaluationDatasetId(_source_id(store, f"{label}-dataset")),
        evaluation_truth_set_id=truth_set_id,
        evaluation_realized_truth_set_id=realized_truth_set_id,
        observation_set_id=EvaluationObservationSetId(
            _source_id(store, f"{label}-observations")
        ),
        policy_id=policy.policy_id,
        use_mode=LearningUseMode.PRODUCTION,
        metrics=(metric,),
        status=LearningEvaluationStatus.COMPLETE,
        blockers=(),
        source_artifact_ids=(metric_source,),
    )
    stored = store_learning_object(report, store=store)
    return report, stored.artifact_id


def synthetic_promoted_model_registry_generation(
    *,
    store,
    season: str,
    candidate_model_id: str,
    authorized_at: str,
) -> str:
    """Create a mechanism-only registry through the real V2 promotion functions."""

    policy, registry, registry_artifact = _policy_bundle(store=store, season=season)
    candidate_id = ModelArtifactId(candidate_model_id)
    incumbent_id = ModelArtifactId(_source_id(store, "incumbent-model"))
    truth_set_id = EvaluationTruthSetId(_source_id(store, "shared-truth-set"))
    realized_truth_set_id = EvaluationRealizedTruthSetId(
        _source_id(store, "shared-realized-truth-set")
    )
    candidate, candidate_artifact = _evaluation(
        store=store,
        model_id=candidate_id,
        policy=policy,
        truth_set_id=truth_set_id,
        realized_truth_set_id=realized_truth_set_id,
        value=1,
        label="candidate",
    )
    incumbent, incumbent_artifact = _evaluation(
        store=store,
        model_id=incumbent_id,
        policy=policy,
        truth_set_id=truth_set_id,
        realized_truth_set_id=realized_truth_set_id,
        value=6,
        label="incumbent",
    )
    comparison = compare_model_evaluations(
        candidate=candidate,
        incumbent=incumbent,
        candidate_report_artifact_id=candidate_artifact,
        incumbent_report_artifact_id=incumbent_artifact,
        policy=policy,
        policy_registry=registry,
        policy_registry_artifact_id=registry_artifact,
        policy_cutoff=authorized_at,
        store=store,
        production=True,
    )
    comparison_artifact = store_learning_object(
        comparison,
        store=store,
        parent_artifact_ids=(candidate_artifact, incumbent_artifact),
    ).artifact_id
    promotion = issue_model_promotion_certificate(
        comparison=comparison,
        comparison_artifact_id=comparison_artifact,
        candidate=candidate,
        candidate_report_artifact_id=candidate_artifact,
        incumbent=incumbent,
        incumbent_report_artifact_id=incumbent_artifact,
        policy=policy,
        policy_registry=registry,
        policy_registry_artifact_id=registry_artifact,
        promotion_cutoff=authorized_at,
        store=store,
    )
    promotion_artifact = store_learning_object(
        promotion,
        store=store,
        parent_artifact_ids=(comparison_artifact,),
    ).artifact_id
    bootstrap = ModelRegistryGeneration(
        season=season,
        generation=1,
        parent_generation_id=None,
        registered_model_ids=(candidate_id, incumbent_id),
        champion_model_id=None,
        promotion_id=None,
        source_artifact_ids=(_source_id(store, "registry-bootstrap"),),
    )
    bootstrap_artifact = store_learning_object(bootstrap, store=store).artifact_id
    promoted = apply_model_promotion(
        current=bootstrap,
        promotion=promotion,
        expected_parent_generation_id=bootstrap.generation_id,
        current_generation_artifact_id=bootstrap_artifact,
        promotion_artifact_id=promotion_artifact,
        store=store,
    )
    return store_learning_object(
        promoted,
        store=store,
        parent_artifact_ids=(bootstrap_artifact,),
    ).artifact_id
