from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.forecast_model_registry import ForecastModelRegistry
from apex_fpl.core.forecast import ForecastModelArtifact, ModelQualificationState
from apex_fpl.forecast.engine import compile_sealed_forecast
from apex_fpl.forecast.forecast_store import load_forecast
from apex_fpl.forecast.prediction_store import load_prediction_batch
from apex_fpl.forecast.targets import build_official_forecast_targets


def _qualified_model(store: FileSystemArtifactStore) -> ForecastModelArtifact:
    parameter = store.put_bytes(b"release-parameter").artifact_id
    qualification = store.put_bytes(b"release-qualification").artifact_id
    return ForecastModelArtifact(
        model_name="release-contract-test",
        model_version="1",
        feature_contract="FeatureSnapshot.v1",
        prediction_contract="PredictionBatch.v1",
        parameter_artifact_ids=(parameter,),
        qualification_state=ModelQualificationState.QUALIFIED,
        qualification_artifact_id=qualification,
        valid_seasons=("2026-2027",),
        trained_through="2026-08-23T00:00:00Z",
        first_available_at="2026-08-23T01:00:00Z",
        max_horizon_gameweeks=8,
    )


def _object_path(root: Path, artifact_id: str) -> Path:
    digest = artifact_id.removeprefix("sha256:")
    return root / "objects" / "sha256" / digest[:2] / digest


def test_forecast_replay_and_compile_apis_expose_no_transport_or_clock_port():
    replay_prediction = set(inspect.signature(load_prediction_batch).parameters)
    replay_forecast = set(inspect.signature(load_forecast).parameters)
    target_builder = set(inspect.signature(build_official_forecast_targets).parameters)
    compiler = set(inspect.signature(compile_sealed_forecast).parameters)

    for parameters in (replay_prediction, replay_forecast, target_builder, compiler):
        assert "transport" not in parameters
        assert "clock" not in parameters
        assert "session" not in parameters
        assert "http" not in parameters

    assert replay_prediction == {"artifact_id", "store"}
    assert replay_forecast == {"artifact_id", "store"}


def test_corrupt_model_parameter_artifact_blocks_even_registered_qualified_model(tmp_path: Path):
    root = tmp_path / "artifacts"
    store = FileSystemArtifactStore(root)
    model = _qualified_model(store)
    registry = ForecastModelRegistry(
        models=(model,),
        champion_model_id=model.model_artifact_id,
    )
    parameter_id = model.parameter_artifact_ids[0]
    _object_path(root, parameter_id).write_bytes(b"corrupt")

    with pytest.raises(Exception, match="parameter artifact|integrity|digest|corrupt"):
        registry.verify_model_artifacts(model, store=store, production=True)


def test_missing_or_corrupt_qualification_artifact_blocks_production(tmp_path: Path):
    root = tmp_path / "artifacts"
    store = FileSystemArtifactStore(root)
    model = _qualified_model(store)
    registry = ForecastModelRegistry(
        models=(model,),
        champion_model_id=model.model_artifact_id,
    )
    assert model.qualification_artifact_id is not None
    _object_path(root, model.qualification_artifact_id).write_bytes(b"corrupt")

    with pytest.raises(Exception, match="qualification artifact|integrity|digest|corrupt"):
        registry.verify_model_artifacts(model, store=store, production=True)


def test_registered_but_nonchampion_qualified_model_cannot_produce(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    champion = _qualified_model(store)
    challenger_parameter = store.put_bytes(b"challenger-parameter").artifact_id
    challenger_qualification = store.put_bytes(b"challenger-qualification").artifact_id
    challenger = ForecastModelArtifact(
        model_name="challenger",
        model_version="1",
        feature_contract="FeatureSnapshot.v1",
        prediction_contract="PredictionBatch.v1",
        parameter_artifact_ids=(challenger_parameter,),
        qualification_state=ModelQualificationState.QUALIFIED,
        qualification_artifact_id=challenger_qualification,
        valid_seasons=("2026-2027",),
        trained_through="2026-08-23T00:00:00Z",
        first_available_at="2026-08-23T01:00:00Z",
        max_horizon_gameweeks=8,
    )
    registry = ForecastModelRegistry(
        models=(champion, challenger),
        champion_model_id=champion.model_artifact_id,
    )

    with pytest.raises(ValueError, match="not the registered champion"):
        registry.verify_model_artifacts(challenger, store=store, production=True)
