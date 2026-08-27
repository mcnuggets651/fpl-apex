from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.learning_promotion_replay import (
    verify_forecast_registry_champion,
    verify_model_evaluation_replay,
)
from apex_fpl.control.learning_store import store_learning_object
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
    LearningUseMode,
    MetricDirection,
)
from apex_fpl.core.learning_evaluation import EvaluationMetricResult, ModelEvaluationReport
from apex_fpl.core.outcome_truth import OutcomeTarget

from learning_promotion_helpers import synthetic_promoted_model_registry_generation


SEASON = "2026-2027"
AS_OF = "2026-08-24T12:00:00Z"


def _store(tmp_path: Path) -> FileSystemArtifactStore:
    return FileSystemArtifactStore(tmp_path / "artifacts")


def _artifact(store: FileSystemArtifactStore, label: str) -> str:
    return store.put_bytes(f"learning-replay-test:{label}".encode("utf-8")).artifact_id


def test_truth_governed_promoted_registry_replays_full_evaluation_and_cas_chain(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    candidate_model_id = _artifact(store, "candidate-model")
    registry_artifact = synthetic_promoted_model_registry_generation(
        store=store,
        season=SEASON,
        candidate_model_id=candidate_model_id,
        authorized_at=AS_OF,
    )

    replayed = verify_forecast_registry_champion(
        registry_artifact,
        season=SEASON,
        as_of=AS_OF,
        store=store,
    )

    assert replayed.champion_model_id == candidate_model_id
    assert replayed.registry_generation.generation == 2
    assert replayed.promotion.certificate.decision.value == "PROMOTE"
    assert replayed.promotion.candidate.report.status is LearningEvaluationStatus.COMPLETE
    assert replayed.promotion.incumbent.report.status is LearningEvaluationStatus.COMPLETE
    assert replayed.promotion.candidate.report.evaluation_truth_set_id == (
        replayed.promotion.incumbent.report.evaluation_truth_set_id
    )
    assert replayed.promotion.candidate.report.evaluation_realized_truth_set_id == (
        replayed.promotion.incumbent.report.evaluation_realized_truth_set_id
    )


def test_structurally_valid_complete_evaluation_without_truth_inputs_cannot_be_replayed(
    tmp_path: Path,
) -> None:
    store = _store(tmp_path)
    metric_source = _artifact(store, "metric-source")
    report = ModelEvaluationReport(
        candidate_model_id=ModelArtifactId(_artifact(store, "model")),
        training_run_id=TrainingRunId(_artifact(store, "training-id-only")),
        evaluation_dataset_id=EvaluationDatasetId(_artifact(store, "dataset-id-only")),
        evaluation_truth_set_id=EvaluationTruthSetId(_artifact(store, "truth-set-id-only")),
        evaluation_realized_truth_set_id=EvaluationRealizedTruthSetId(
            _artifact(store, "realized-truth-id-only")
        ),
        observation_set_id=EvaluationObservationSetId(_artifact(store, "observation-id-only")),
        policy_id=LearningPolicyId(_artifact(store, "policy-id-only")),
        use_mode=LearningUseMode.PRODUCTION,
        metrics=(
            EvaluationMetricResult(
                metric=EvaluationMetric.MINUTES_MAE,
                target=OutcomeTarget.MINUTES,
                cohort="ALL",
                direction=MetricDirection.LOWER_IS_BETTER,
                sample_count=2,
                value=ExactMetricValue(1),
                interval_lower=None,
                interval_upper=None,
                source_artifact_ids=(metric_source,),
            ),
        ),
        status=LearningEvaluationStatus.COMPLETE,
        blockers=(),
        source_artifact_ids=(metric_source,),
    )
    stored = store_learning_object(report, store=store)

    with pytest.raises(ValueError, match="MODEL_TRAINING_RUN"):
        verify_model_evaluation_replay(
            stored.artifact_id,
            season=SEASON,
            as_of=AS_OF,
            store=store,
        )
