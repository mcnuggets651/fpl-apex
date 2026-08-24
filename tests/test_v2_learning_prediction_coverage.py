from __future__ import annotations

import json
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.learning_evaluator import evaluate_model
from apex_fpl.control.learning_policy_registry import LearningPolicyRegistry
from apex_fpl.control.learning_store import store_learning_object
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry_bytes
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import FeatureSnapshotId, ForecastId, ModelArtifactId
from apex_fpl.core.learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningEvaluationStatus,
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
from apex_fpl.core.learning_training import ModelTrainingRun
from apex_fpl.core.outcome_truth import OutcomeTarget

ROOT = Path(__file__).resolve().parents[1]
SEASON = "2026-2027"


def _put(store: FileSystemArtifactStore, value: str) -> str:
    return store.put_bytes(value.encode("utf-8")).artifact_id


def _minutes_truth(store: FileSystemArtifactStore, *, player_id: int, minutes: int) -> str:
    payload = {
        "elements": [
            {
                "id": player_id,
                "stats": {
                    "minutes": minutes,
                    "total_points": 0,
                    "goals_scored": 0,
                    "assists": 0,
                },
            }
        ]
    }
    return store.put_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).artifact_id


def test_prediction_coverage_keeps_complete_realized_truth_with_explicit_missing_prediction(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth_bytes = (ROOT / "config" / "outcome_truth_v2.yaml").read_bytes()
    truth_artifact = store.put_bytes(truth_bytes).artifact_id
    truth_registry = load_outcome_truth_registry_bytes(truth_bytes)

    qualification = _put(store, "coverage-policy-qualification")
    rule_artifact = _put(store, "coverage-policy-rules")
    requirement = MetricRequirement(
        metric=EvaluationMetric.PREDICTION_COVERAGE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        minimum_cases=2,
    )
    rule = MetricPromotionRule(
        metric=EvaluationMetric.PREDICTION_COVERAGE,
        target=OutcomeTarget.MINUTES,
        cohort="ALL",
        direction=MetricDirection.HIGHER_IS_BETTER,
        minimum_improvement=ExactMetricValue(0),
    )
    policy = LearningEvaluationPolicy(
        policy_name="coverage-policy",
        policy_version="v1",
        qualification_state=LearningPolicyQualification.QUALIFIED,
        qualification_artifact_id=qualification,
        promotion_rule_artifact_id=rule_artifact,
        first_available_at="2026-08-01T00:00:00Z",
        valid_seasons=(SEASON,),
        requirements=(requirement,),
        promotion_rules=(rule,),
    )
    policy_artifact = store_learning_object(policy, store=store).artifact_id
    registry = LearningPolicyRegistry(
        season=SEASON,
        policies=(policy,),
        champion_policy_id=policy.policy_id,
    )
    registry_payload = {
        "schema_version": 1,
        "season": SEASON,
        "champion_policy_id": str(policy.policy_id),
        "policies": [policy.semantic_payload()],
    }
    registry_artifact = store.put_bytes(
        yaml.safe_dump(registry_payload, sort_keys=True).encode("utf-8")
    ).artifact_id

    model_id = ModelArtifactId("coverage-model")
    train_data = _put(store, "coverage-train-data")
    train_code = _put(store, "coverage-train-code")
    parameters = _put(store, "coverage-parameters")
    training = ModelTrainingRun(
        model_artifact_id=model_id,
        training_cutoff="2026-07-31T23:00:00Z",
        first_available_at="2026-08-01T00:00:00Z",
        training_dataset_artifact_ids=(train_data,),
        trainer_code_artifact_id=train_code,
        parameter_artifact_ids=(parameters,),
        source_artifact_ids=(train_data, train_code, parameters),
    )
    training_artifact = store_learning_object(training, store=store).artifact_id

    outcome_a = _minutes_truth(store, player_id=1, minutes=61)
    outcome_b = _minutes_truth(store, player_id=2, minutes=72)
    prediction_a = _put(store, "coverage-prediction-a")
    prediction_b = _put(store, "coverage-prediction-missing-marker")
    cases = (
        EvaluationCase(
            forecast_id=ForecastId("coverage-forecast-a"),
            feature_snapshot_id=FeatureSnapshotId("coverage-features-a"),
            model_artifact_id=model_id,
            target=OutcomeTarget.MINUTES,
            player_id=OfficialPlayerId(1),
            gameweek=1,
            prediction_sealed_at="2026-08-10T08:00:00Z",
            outcome_first_available_at="2026-08-11T08:00:00Z",
            prediction_artifact_id=prediction_a,
            outcome_artifact_id=outcome_a,
        ),
        EvaluationCase(
            forecast_id=ForecastId("coverage-forecast-b"),
            feature_snapshot_id=FeatureSnapshotId("coverage-features-b"),
            model_artifact_id=model_id,
            target=OutcomeTarget.MINUTES,
            player_id=OfficialPlayerId(2),
            gameweek=1,
            prediction_sealed_at="2026-08-10T08:00:00Z",
            outcome_first_available_at="2026-08-11T08:00:00Z",
            prediction_artifact_id=prediction_b,
            outcome_artifact_id=outcome_b,
        ),
    )
    dataset = EvaluationDataset(
        season=SEASON,
        truth_registry_id=truth_registry.truth_registry_id,
        cases=cases,
        source_artifact_ids=(prediction_a, prediction_b, outcome_a, outcome_b),
    )
    dataset_artifact = store_learning_object(dataset, store=store).artifact_id
    observations = EvaluationObservationSet(
        evaluation_dataset_id=dataset.dataset_id,
        evaluation_truth_set_id=dataset.truth_set_id,
        observations=(
            EvaluationObservation(
                case_id=cases[0].case_id,
                truth_case_id=cases[0].truth_case_id,
                target=OutcomeTarget.MINUTES,
                predicted_value=ExactMetricValue(60),
                actual_value=ExactMetricValue(61),
            ),
            EvaluationObservation(
                case_id=cases[1].case_id,
                truth_case_id=cases[1].truth_case_id,
                target=OutcomeTarget.MINUTES,
                predicted_value=None,
                actual_value=ExactMetricValue(72),
            ),
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
        truth_registry_artifact_id=truth_artifact,
        policy=policy,
        policy_artifact_id=policy_artifact,
        policy_registry=registry,
        policy_registry_artifact_id=registry_artifact,
        store=store,
        production=True,
    )

    assert report.status is LearningEvaluationStatus.COMPLETE
    assert report.metrics[0].value == ExactMetricValue(1, 2)
    assert report.metrics[0].sample_count == 2
    assert len(observations.observations) == 2
    assert observations.realized_truth_set_id == report.evaluation_realized_truth_set_id
