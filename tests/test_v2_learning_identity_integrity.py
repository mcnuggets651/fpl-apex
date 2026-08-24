from __future__ import annotations

import pytest

from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    FeatureSnapshotId,
    ForecastId,
    ModelArtifactId,
    OutcomeTruthRegistryId,
)
from apex_fpl.core.learning_dataset import EvaluationCase, EvaluationDataset
from apex_fpl.core.learning_training import ModelTrainingRun
from apex_fpl.core.outcome_truth import OutcomeTarget

ARTIFACT_A = "sha256:" + "a" * 64
ARTIFACT_B = "sha256:" + "b" * 64
ARTIFACT_C = "sha256:" + "c" * 64


def _case() -> EvaluationCase:
    return EvaluationCase(
        forecast_id=ForecastId("forecast"),
        feature_snapshot_id=FeatureSnapshotId("features"),
        model_artifact_id=ModelArtifactId("model"),
        target=OutcomeTarget.MINUTES,
        player_id=OfficialPlayerId(7),
        gameweek=1,
        prediction_sealed_at="2026-08-10T08:00:00Z",
        outcome_first_available_at="2026-08-11T08:00:00Z",
        prediction_artifact_id=ARTIFACT_A,
        outcome_artifact_id=ARTIFACT_B,
    )


def test_evaluation_case_rejects_raw_player_and_semantic_ids() -> None:
    kwargs = {
        "forecast_id": ForecastId("forecast"),
        "feature_snapshot_id": FeatureSnapshotId("features"),
        "model_artifact_id": ModelArtifactId("model"),
        "target": OutcomeTarget.MINUTES,
        "player_id": OfficialPlayerId(7),
        "gameweek": 1,
        "prediction_sealed_at": "2026-08-10T08:00:00Z",
        "outcome_first_available_at": "2026-08-11T08:00:00Z",
        "prediction_artifact_id": ARTIFACT_A,
        "outcome_artifact_id": ARTIFACT_B,
    }
    EvaluationCase(**kwargs)

    with pytest.raises(ValueError, match="player_id must be typed"):
        EvaluationCase(**{**kwargs, "player_id": 7})  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="forecast_id must be typed"):
        EvaluationCase(**{**kwargs, "forecast_id": "forecast"})  # type: ignore[arg-type]


def test_evaluation_dataset_rejects_raw_truth_registry_and_untyped_cases() -> None:
    case = _case()
    EvaluationDataset(
        season="2026-2027",
        truth_registry_id=OutcomeTruthRegistryId("truth-registry"),
        cases=(case,),
        source_artifact_ids=(ARTIFACT_A, ARTIFACT_B),
    )
    with pytest.raises(ValueError, match="truth_registry_id must be typed"):
        EvaluationDataset(
            season="2026-2027",
            truth_registry_id="truth-registry",  # type: ignore[arg-type]
            cases=(case,),
            source_artifact_ids=(ARTIFACT_A, ARTIFACT_B),
        )
    with pytest.raises(ValueError, match="cases must be typed"):
        EvaluationDataset(
            season="2026-2027",
            truth_registry_id=OutcomeTruthRegistryId("truth-registry"),
            cases=("case",),  # type: ignore[arg-type]
            source_artifact_ids=(ARTIFACT_A, ARTIFACT_B),
        )


def test_training_run_rejects_raw_model_identity() -> None:
    with pytest.raises(ValueError, match="model_artifact_id must be typed"):
        ModelTrainingRun(
            model_artifact_id="model",  # type: ignore[arg-type]
            training_cutoff="2026-07-31T23:00:00Z",
            first_available_at="2026-08-01T00:00:00Z",
            training_dataset_artifact_ids=(ARTIFACT_A,),
            trainer_code_artifact_id=ARTIFACT_B,
            parameter_artifact_ids=(ARTIFACT_C,),
            source_artifact_ids=(ARTIFACT_A, ARTIFACT_B, ARTIFACT_C),
        )
