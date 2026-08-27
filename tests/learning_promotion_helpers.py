from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import yaml

from apex_fpl.control.empirical_qualification_admission import LEARNING_POLICY_QUALIFICATION_ID
from apex_fpl.control.learning_evaluator import evaluate_model
from apex_fpl.control.learning_policy_registry import LearningPolicyRegistry
from apex_fpl.control.learning_promotion import (
    apply_model_promotion,
    compare_model_evaluations,
    issue_model_promotion_certificate,
)
from apex_fpl.control.learning_store import store_learning_object
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry_bytes
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import FeatureSnapshotId, ForecastId, ModelArtifactId
from apex_fpl.core.learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningPolicyQualification,
    MetricDirection,
)
from apex_fpl.core.learning_dataset import EvaluationCase, EvaluationDataset
from apex_fpl.core.learning_observations import EvaluationObservation, EvaluationObservationSet
from apex_fpl.core.learning_policy import (
    LearningEvaluationPolicy,
    MetricPromotionRule,
    MetricRequirement,
)
from apex_fpl.core.learning_promotion import ModelRegistryGeneration
from apex_fpl.core.learning_training import ModelTrainingRun
from apex_fpl.core.outcome_truth import OutcomeTarget

from empirical_qualification_helpers import synthetic_supported_qualification_artifact


ROOT = Path(__file__).resolve().parents[1]
PREDICTED_AT = "2026-08-10T08:00:00Z"
OUTCOME_AT = "2026-08-11T08:00:00Z"


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
    stored_policy = store_learning_object(policy, store=store)
    registry = LearningPolicyRegistry(
        season=season,
        policies=(policy,),
        champion_policy_id=policy.policy_id,
    )
    registry_payload = {
        "schema_version": 1,
        "season": season,
        "champion_policy_id": str(policy.policy_id),
        "policies": [policy.semantic_payload()],
    }
    registry_artifact = store.put_bytes(
        yaml.safe_dump(registry_payload, sort_keys=True).encode("utf-8")
    ).artifact_id
    return policy, stored_policy.artifact_id, registry, registry_artifact


def _truth(store):
    content = (ROOT / "config" / "outcome_truth_v2.yaml").read_bytes()
    artifact_id = store.put_bytes(content).artifact_id
    return load_outcome_truth_registry_bytes(content), artifact_id


def _official_minutes_outcomes(store) -> tuple[tuple[str, ...], tuple[ExactMetricValue, ...]]:
    actuals = (ExactMetricValue(61), ExactMetricValue(69))
    artifacts: list[str] = []
    for index, actual in enumerate(actuals, start=1):
        value = actual.as_fraction()
        if value.denominator != 1:
            raise AssertionError("synthetic Official FPL minutes must be integer")
        payload = {
            "elements": [
                {
                    "id": index,
                    "stats": {
                        "minutes": value.numerator,
                        "total_points": 0,
                        "goals_scored": 0,
                        "assists": 0,
                    },
                }
            ]
        }
        artifacts.append(
            store.put_bytes(
                json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).artifact_id
        )
    return tuple(artifacts), actuals


def _training(*, store, model_id: ModelArtifactId, label: str):
    dataset_artifact = _source_id(store, f"{label}-training-dataset")
    trainer_artifact = _source_id(store, f"{label}-trainer")
    parameter_artifact = _source_id(store, f"{label}-parameter")
    run = ModelTrainingRun(
        model_artifact_id=model_id,
        training_cutoff="2026-07-31T23:00:00Z",
        first_available_at="2026-08-01T00:00:00Z",
        training_dataset_artifact_ids=(dataset_artifact,),
        trainer_code_artifact_id=trainer_artifact,
        parameter_artifact_ids=(parameter_artifact,),
        source_artifact_ids=(dataset_artifact, trainer_artifact, parameter_artifact),
    )
    return run, store_learning_object(run, store=store).artifact_id


def _evaluation(
    *,
    store,
    season: str,
    model_id: ModelArtifactId,
    policy,
    policy_artifact_id: str,
    registry,
    registry_artifact_id: str,
    truth_registry,
    truth_registry_artifact_id: str,
    outcome_artifacts: tuple[str, ...],
    actuals: tuple[ExactMetricValue, ...],
    predicted: tuple[ExactMetricValue, ...],
    label: str,
):
    if len(actuals) != len(predicted) or len(actuals) != len(outcome_artifacts):
        raise AssertionError("synthetic learning rows must align")
    training, training_artifact = _training(store=store, model_id=model_id, label=label)
    prediction_artifacts = tuple(
        _source_id(store, f"{label}-prediction-{index}")
        for index in range(len(predicted))
    )
    cases = tuple(
        EvaluationCase(
            forecast_id=ForecastId(f"synthetic-{label}-forecast-{index}"),
            feature_snapshot_id=FeatureSnapshotId(f"synthetic-{label}-features-{index}"),
            model_artifact_id=model_id,
            target=OutcomeTarget.MINUTES,
            player_id=OfficialPlayerId(index + 1),
            gameweek=1,
            prediction_sealed_at=PREDICTED_AT,
            outcome_first_available_at=OUTCOME_AT,
            prediction_artifact_id=prediction_artifacts[index],
            outcome_artifact_id=outcome_artifacts[index],
        )
        for index in range(len(predicted))
    )
    dataset = EvaluationDataset(
        season=season,
        truth_registry_id=truth_registry.truth_registry_id,
        cases=cases,
        source_artifact_ids=prediction_artifacts + outcome_artifacts,
    )
    dataset_artifact = store_learning_object(dataset, store=store).artifact_id
    observations = EvaluationObservationSet(
        evaluation_dataset_id=dataset.dataset_id,
        evaluation_truth_set_id=dataset.truth_set_id,
        observations=tuple(
            EvaluationObservation(
                case_id=case.case_id,
                truth_case_id=case.truth_case_id,
                target=OutcomeTarget.MINUTES,
                predicted_value=predicted[index],
                actual_value=actuals[index],
            )
            for index, case in enumerate(cases)
        ),
    )
    observation_artifact = store_learning_object(observations, store=store).artifact_id
    report = evaluate_model(
        training_run=training,
        training_run_artifact_id=training_artifact,
        dataset=dataset,
        evaluation_dataset_artifact_id=dataset_artifact,
        observation_set=observations,
        observation_set_artifact_id=observation_artifact,
        truth_registry=truth_registry,
        truth_registry_artifact_id=truth_registry_artifact_id,
        policy=policy,
        policy_artifact_id=policy_artifact_id,
        policy_registry=registry,
        policy_registry_artifact_id=registry_artifact_id,
        store=store,
        production=True,
    )
    stored_report = store_learning_object(report, store=store)
    return report, stored_report.artifact_id


def synthetic_promoted_model_registry_generation(
    *,
    store,
    season: str,
    candidate_model_id: str,
    authorized_at: str,
) -> str:
    """Create mechanism-only champion lineage through the real truth-governed V2 path."""

    policy, policy_artifact, registry, registry_artifact = _policy_bundle(
        store=store,
        season=season,
    )
    truth_registry, truth_registry_artifact = _truth(store)
    outcome_artifacts, actuals = _official_minutes_outcomes(store)
    candidate_id = ModelArtifactId(candidate_model_id)
    incumbent_id = ModelArtifactId(_source_id(store, "incumbent-model"))
    candidate, candidate_artifact = _evaluation(
        store=store,
        season=season,
        model_id=candidate_id,
        policy=policy,
        policy_artifact_id=policy_artifact,
        registry=registry,
        registry_artifact_id=registry_artifact,
        truth_registry=truth_registry,
        truth_registry_artifact_id=truth_registry_artifact,
        outcome_artifacts=outcome_artifacts,
        actuals=actuals,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        label="candidate",
    )
    incumbent, incumbent_artifact = _evaluation(
        store=store,
        season=season,
        model_id=incumbent_id,
        policy=policy,
        policy_artifact_id=policy_artifact,
        registry=registry,
        registry_artifact_id=registry_artifact,
        truth_registry=truth_registry,
        truth_registry_artifact_id=truth_registry_artifact,
        outcome_artifacts=outcome_artifacts,
        actuals=actuals,
        predicted=(ExactMetricValue(55), ExactMetricValue(75)),
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
