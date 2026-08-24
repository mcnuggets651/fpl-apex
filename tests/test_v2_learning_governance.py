from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.learning_evaluator import evaluate_model
from apex_fpl.control.learning_policy_registry import (
    LearningPolicyRegistry,
    load_learning_policy_registry,
)
from apex_fpl.control.learning_promotion import (
    apply_model_promotion,
    compare_model_evaluations,
    issue_model_promotion_certificate,
)
from apex_fpl.control.learning_store import store_learning_object
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry_bytes
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import FeatureSnapshotId, ForecastId, ModelArtifactId, ModelRegistryGenerationId
from apex_fpl.core.learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningEvaluationStatus,
    LearningPolicyQualification,
    MetricDirection,
    ModelPromotionDecision,
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

ROOT = Path(__file__).resolve().parents[1]
SEASON = "2026-2027"
PREDICTED_AT = "2026-08-10T08:00:00Z"
OUTCOME_AT = "2026-08-11T08:00:00Z"


def _put(store: FileSystemArtifactStore, text: str) -> str:
    return store.put_bytes(text.encode("utf-8")).artifact_id


def _truth(store: FileSystemArtifactStore):
    content = (ROOT / "config" / "outcome_truth_v2.yaml").read_bytes()
    artifact_id = store.put_bytes(content).artifact_id
    return load_outcome_truth_registry_bytes(content), artifact_id


def _policy_bundle(
    store: FileSystemArtifactStore,
    *,
    metric: EvaluationMetric = EvaluationMetric.MINUTES_MAE,
    target: OutcomeTarget = OutcomeTarget.MINUTES,
    minimum_cases: int = 2,
    minimum_improvement: ExactMetricValue = ExactMetricValue(2),
    direction: MetricDirection = MetricDirection.LOWER_IS_BETTER,
    first_available_at: str = "2026-08-01T00:00:00Z",
    require_interval: bool = False,
    require_interval_superiority: bool = False,
    champion: bool = True,
):
    qualification = _put(store, f"qualification-{metric.value}-{target.value}-{minimum_cases}")
    rule_artifact = _put(store, f"promotion-rules-{metric.value}-{target.value}-{minimum_cases}")
    requirement = MetricRequirement(
        metric=metric,
        target=target,
        cohort="ALL",
        minimum_cases=minimum_cases,
        require_interval=require_interval,
    )
    rule = MetricPromotionRule(
        metric=metric,
        target=target,
        cohort="ALL",
        direction=direction,
        minimum_improvement=minimum_improvement,
        require_interval_superiority=require_interval_superiority,
    )
    policy = LearningEvaluationPolicy(
        policy_name="synthetic-learning-policy",
        policy_version=f"1-{metric.value}-{target.value}-{minimum_cases}",
        qualification_state=LearningPolicyQualification.QUALIFIED,
        qualification_artifact_id=qualification,
        promotion_rule_artifact_id=rule_artifact,
        first_available_at=first_available_at,
        valid_seasons=(SEASON,),
        requirements=(requirement,),
        promotion_rules=(rule,),
    )
    stored_policy = store_learning_object(policy, store=store)
    registry = LearningPolicyRegistry(
        season=SEASON,
        policies=(policy,),
        champion_policy_id=policy.policy_id if champion else None,
    )
    registry_payload = {
        "schema_version": 1,
        "season": SEASON,
        "champion_policy_id": None if registry.champion_policy_id is None else str(registry.champion_policy_id),
        "policies": [policy.semantic_payload()],
    }
    registry_artifact = store.put_bytes(
        yaml.safe_dump(registry_payload, sort_keys=True).encode("utf-8")
    ).artifact_id
    return policy, stored_policy.artifact_id, registry, registry_artifact


def _training(store: FileSystemArtifactStore, model_id: ModelArtifactId, *, available_at: str = "2026-08-01T00:00:00Z"):
    dataset_artifact = _put(store, f"training-data-{model_id}")
    trainer_artifact = _put(store, f"trainer-code-{model_id}")
    parameter_artifact = _put(store, f"parameters-{model_id}")
    run = ModelTrainingRun(
        model_artifact_id=model_id,
        training_cutoff="2026-07-31T23:00:00Z",
        first_available_at=available_at,
        training_dataset_artifact_ids=(dataset_artifact,),
        trainer_code_artifact_id=trainer_artifact,
        parameter_artifact_ids=(parameter_artifact,),
        source_artifact_ids=(dataset_artifact, trainer_artifact, parameter_artifact),
    )
    return run, store_learning_object(run, store=store).artifact_id


def _model_inputs(
    store: FileSystemArtifactStore,
    *,
    model_name: str,
    target: OutcomeTarget,
    predicted: tuple[ExactMetricValue, ...],
    actual: tuple[ExactMetricValue, ...],
    truth_registry_id,
    outcome_artifacts: tuple[str, ...] | None = None,
    available_at: str = "2026-08-01T00:00:00Z",
    intervals: tuple[tuple[ExactMetricValue, ExactMetricValue] | None, ...] | None = None,
):
    assert len(predicted) == len(actual)
    model_id = ModelArtifactId(model_name)
    training, training_artifact = _training(store, model_id, available_at=available_at)
    if outcome_artifacts is None:
        outcome_artifacts = tuple(
            _put(store, f"outcome-{target.value}-{index}") for index in range(len(actual))
        )
    prediction_artifacts = tuple(
        _put(store, f"prediction-{model_name}-{target.value}-{index}")
        for index in range(len(actual))
    )
    cases = tuple(
        EvaluationCase(
            forecast_id=ForecastId(f"forecast-{model_name}-{index}"),
            feature_snapshot_id=FeatureSnapshotId(f"features-{model_name}-{index}"),
            model_artifact_id=model_id,
            target=target,
            player_id=OfficialPlayerId(index + 1),
            gameweek=1,
            prediction_sealed_at=PREDICTED_AT,
            outcome_first_available_at=OUTCOME_AT,
            prediction_artifact_id=prediction_artifacts[index],
            outcome_artifact_id=outcome_artifacts[index],
        )
        for index in range(len(actual))
    )
    dataset = EvaluationDataset(
        season=SEASON,
        truth_registry_id=truth_registry_id,
        cases=cases,
        source_artifact_ids=prediction_artifacts + outcome_artifacts,
    )
    dataset_artifact = store_learning_object(dataset, store=store).artifact_id
    intervals = intervals or tuple(None for _ in actual)
    observations = tuple(
        EvaluationObservation(
            case_id=case.case_id,
            target=target,
            predicted_value=predicted[index],
            actual_value=actual[index],
            interval_lower=None if intervals[index] is None else intervals[index][0],
            interval_upper=None if intervals[index] is None else intervals[index][1],
        )
        for index, case in enumerate(cases)
    )
    observation_set = EvaluationObservationSet(dataset.dataset_id, observations)
    observation_artifact = store_learning_object(observation_set, store=store).artifact_id
    return {
        "model_id": model_id,
        "training": training,
        "training_artifact": training_artifact,
        "dataset": dataset,
        "dataset_artifact": dataset_artifact,
        "observation_set": observation_set,
        "observation_artifact": observation_artifact,
        "outcome_artifacts": outcome_artifacts,
    }


def _evaluate(store, inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact, *, production=True):
    return evaluate_model(
        training_run=inputs["training"],
        training_run_artifact_id=inputs["training_artifact"],
        dataset=inputs["dataset"],
        evaluation_dataset_artifact_id=inputs["dataset_artifact"],
        observation_set=inputs["observation_set"],
        observation_set_artifact_id=inputs["observation_artifact"],
        truth_registry=truth,
        truth_registry_artifact_id=truth_artifact,
        policy=policy,
        policy_artifact_id=policy_artifact,
        policy_registry=registry,
        policy_registry_artifact_id=registry_artifact,
        store=store,
        production=production,
    )


def test_default_learning_registry_has_no_fabricated_champion() -> None:
    registry = load_learning_policy_registry(ROOT / "config" / "learning_policies_v2.yaml")
    assert registry.policies == ()
    assert registry.champion() is None


def test_exact_metric_value_reduces_and_no_hindsight_case_is_strict(tmp_path: Path) -> None:
    assert ExactMetricValue(2, 4) == ExactMetricValue(1, 2)
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    prediction = _put(store, "prediction")
    outcome = _put(store, "outcome")
    with pytest.raises(ValueError, match="strictly after"):
        EvaluationCase(
            forecast_id=ForecastId("forecast"),
            feature_snapshot_id=FeatureSnapshotId("features"),
            model_artifact_id=ModelArtifactId("model"),
            target=OutcomeTarget.MINUTES,
            player_id=OfficialPlayerId(1),
            gameweek=1,
            prediction_sealed_at=OUTCOME_AT,
            outcome_first_available_at=OUTCOME_AT,
            prediction_artifact_id=prediction,
            outcome_artifact_id=outcome,
        )


def test_verified_minutes_evaluation_is_exact_and_complete(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(store)
    inputs = _model_inputs(
        store,
        model_name="candidate",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
    )
    report = _evaluate(
        store, inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact
    )
    assert report.status is LearningEvaluationStatus.COMPLETE
    assert report.metrics[0].value == ExactMetricValue(1)
    assert report.evaluation_truth_set_id == inputs["dataset"].truth_set_id


def test_start_brier_remains_inconclusive_while_start_truth_is_unresolved(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(
        store,
        metric=EvaluationMetric.START_BRIER,
        target=OutcomeTarget.START,
        minimum_cases=1,
        minimum_improvement=ExactMetricValue(0),
    )
    inputs = _model_inputs(
        store,
        model_name="start-model",
        target=OutcomeTarget.START,
        predicted=(ExactMetricValue(1, 2),),
        actual=(ExactMetricValue(1),),
        truth_registry_id=truth.truth_registry_id,
    )
    report = _evaluate(
        store, inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact
    )
    assert report.status is LearningEvaluationStatus.INCONCLUSIVE
    assert any("UNRESOLVED" in blocker for blocker in report.blockers)


def test_insufficient_sample_and_future_policy_stay_inconclusive(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(
        store,
        minimum_cases=3,
        first_available_at="2026-08-12T00:00:00Z",
    )
    inputs = _model_inputs(
        store,
        model_name="small-sample",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
    )
    report = _evaluate(
        store, inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact
    )
    assert report.status is LearningEvaluationStatus.INCONCLUSIVE
    assert any("below required" in blocker for blocker in report.blockers)
    assert any("not available" in blocker for blocker in report.blockers)


def test_future_training_run_cannot_score_past_prediction(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(store)
    inputs = _model_inputs(
        store,
        model_name="future-trained",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
        available_at="2026-08-12T00:00:00Z",
    )
    with pytest.raises(ValueError, match="not available"):
        _evaluate(
            store, inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact
        )


def test_decision_impact_metric_cannot_be_fabricated_by_player_evaluator(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(
        store,
        metric=EvaluationMetric.DECISION_REALIZED_POINTS_DELTA,
        target=OutcomeTarget.FPL_POINTS,
        minimum_cases=1,
        minimum_improvement=ExactMetricValue(1),
        direction=MetricDirection.HIGHER_IS_BETTER,
    )
    inputs = _model_inputs(
        store,
        model_name="decision-impact",
        target=OutcomeTarget.FPL_POINTS,
        predicted=(ExactMetricValue(5),),
        actual=(ExactMetricValue(6),),
        truth_registry_id=truth.truth_registry_id,
    )
    report = _evaluate(
        store, inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact
    )
    assert report.status is LearningEvaluationStatus.INCONCLUSIVE
    assert any("separate sealed decision-impact" in blocker for blocker in report.blockers)


def test_candidate_and_incumbent_must_share_exact_truth_set(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(store)
    candidate_inputs = _model_inputs(
        store,
        model_name="candidate",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
    )
    incumbent_inputs = _model_inputs(
        store,
        model_name="incumbent",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(55), ExactMetricValue(75)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
    )
    candidate = _evaluate(store, candidate_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact)
    incumbent = _evaluate(store, incumbent_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact)
    candidate_artifact = store_learning_object(candidate, store=store).artifact_id
    incumbent_artifact = store_learning_object(incumbent, store=store).artifact_id
    with pytest.raises(ValueError, match="exact same truth set"):
        compare_model_evaluations(
            candidate=candidate,
            incumbent=incumbent,
            candidate_report_artifact_id=candidate_artifact,
            incumbent_report_artifact_id=incumbent_artifact,
            policy=policy,
            policy_registry=registry,
            policy_registry_artifact_id=registry_artifact,
            policy_cutoff=OUTCOME_AT,
            store=store,
            production=True,
        )


def test_shadow_complete_evidence_cannot_be_promoted_as_production(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(store)
    shared_outcomes = (_put(store, "shared-o1"), _put(store, "shared-o2"))
    candidate_inputs = _model_inputs(
        store,
        model_name="candidate",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
        outcome_artifacts=shared_outcomes,
    )
    incumbent_inputs = _model_inputs(
        store,
        model_name="incumbent",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(55), ExactMetricValue(75)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
        outcome_artifacts=shared_outcomes,
    )
    candidate = _evaluate(store, candidate_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact, production=False)
    incumbent = _evaluate(store, incumbent_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact, production=False)
    assert candidate.status is LearningEvaluationStatus.COMPLETE
    candidate_artifact = store_learning_object(candidate, store=store).artifact_id
    incumbent_artifact = store_learning_object(incumbent, store=store).artifact_id
    comparison = compare_model_evaluations(
        candidate=candidate,
        incumbent=incumbent,
        candidate_report_artifact_id=candidate_artifact,
        incumbent_report_artifact_id=incumbent_artifact,
        policy=policy,
        policy_registry=registry,
        policy_registry_artifact_id=registry_artifact,
        policy_cutoff=OUTCOME_AT,
        store=store,
        production=True,
    )
    assert comparison.status is LearningEvaluationStatus.INCONCLUSIVE
    assert any("mode" in blocker for blocker in comparison.blockers)


def test_exact_promotion_rules_and_cas_registry_transition(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(store)
    shared_outcomes = (_put(store, "same-o1"), _put(store, "same-o2"))
    candidate_inputs = _model_inputs(
        store,
        model_name="candidate",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
        outcome_artifacts=shared_outcomes,
    )
    incumbent_inputs = _model_inputs(
        store,
        model_name="incumbent",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(55), ExactMetricValue(75)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
        outcome_artifacts=shared_outcomes,
    )
    candidate = _evaluate(store, candidate_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact)
    incumbent = _evaluate(store, incumbent_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact)
    candidate_artifact = store_learning_object(candidate, store=store).artifact_id
    incumbent_artifact = store_learning_object(incumbent, store=store).artifact_id
    comparison = compare_model_evaluations(
        candidate=candidate,
        incumbent=incumbent,
        candidate_report_artifact_id=candidate_artifact,
        incumbent_report_artifact_id=incumbent_artifact,
        policy=policy,
        policy_registry=registry,
        policy_registry_artifact_id=registry_artifact,
        policy_cutoff=OUTCOME_AT,
        store=store,
        production=True,
    )
    assert comparison.status is LearningEvaluationStatus.COMPLETE
    assert comparison.comparisons[0].improvement == ExactMetricValue(4)
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
        promotion_cutoff="2026-08-12T00:00:00Z",
        store=store,
    )
    assert promotion.decision is ModelPromotionDecision.PROMOTE
    promotion_artifact = store_learning_object(
        promotion,
        store=store,
        parent_artifact_ids=(comparison_artifact,),
    ).artifact_id
    bootstrap = _put(store, "registry-bootstrap")
    current = ModelRegistryGeneration(
        season=SEASON,
        generation=1,
        parent_generation_id=None,
        registered_model_ids=(candidate.candidate_model_id, incumbent.candidate_model_id),
        champion_model_id=None,
        promotion_id=None,
        source_artifact_ids=(bootstrap,),
    )
    current_artifact = store_learning_object(current, store=store).artifact_id
    next_generation = apply_model_promotion(
        current=current,
        promotion=promotion,
        expected_parent_generation_id=current.generation_id,
        current_generation_artifact_id=current_artifact,
        promotion_artifact_id=promotion_artifact,
        store=store,
    )
    assert next_generation.champion_model_id == candidate.candidate_model_id
    assert next_generation.parent_generation_id == current.generation_id
    with pytest.raises(ValueError, match="stale"):
        apply_model_promotion(
            current=current,
            promotion=promotion,
            expected_parent_generation_id=ModelRegistryGenerationId("stale"),
            current_generation_artifact_id=current_artifact,
            promotion_artifact_id=promotion_artifact,
            store=store,
        )


def test_valid_but_unrelated_evaluation_artifact_cannot_launder_identity(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    truth, truth_artifact = _truth(store)
    policy, policy_artifact, registry, registry_artifact = _policy_bundle(store)
    shared_outcomes = (_put(store, "launder-o1"), _put(store, "launder-o2"))
    candidate_inputs = _model_inputs(
        store,
        model_name="candidate-a",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(60), ExactMetricValue(70)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
        outcome_artifacts=shared_outcomes,
    )
    other_inputs = _model_inputs(
        store,
        model_name="candidate-b",
        target=OutcomeTarget.MINUTES,
        predicted=(ExactMetricValue(59), ExactMetricValue(71)),
        actual=(ExactMetricValue(61), ExactMetricValue(69)),
        truth_registry_id=truth.truth_registry_id,
        outcome_artifacts=shared_outcomes,
    )
    candidate = _evaluate(store, candidate_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact)
    other = _evaluate(store, other_inputs, truth, truth_artifact, policy, policy_artifact, registry, registry_artifact)
    candidate_artifact = store_learning_object(candidate, store=store).artifact_id
    other_artifact = store_learning_object(other, store=store).artifact_id
    with pytest.raises(ValueError, match="expected semantic"):
        compare_model_evaluations(
            candidate=candidate,
            incumbent=other,
            candidate_report_artifact_id=other_artifact,
            incumbent_report_artifact_id=candidate_artifact,
            policy=policy,
            policy_registry=registry,
            policy_registry_artifact_id=registry_artifact,
            policy_cutoff=OUTCOME_AT,
            store=store,
            production=True,
        )
