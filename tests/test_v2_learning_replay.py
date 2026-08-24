from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.learning_store import load_learning_object, store_learning_object
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.ids import ModelArtifactId
from apex_fpl.core.learning_training import ModelTrainingRun


def _put(store: FileSystemArtifactStore, text: str) -> str:
    return store.put_bytes(text.encode("utf-8")).artifact_id


def _training(store: FileSystemArtifactStore) -> ModelTrainingRun:
    dataset = _put(store, "training-dataset")
    trainer = _put(store, "trainer")
    parameter = _put(store, "parameter")
    return ModelTrainingRun(
        model_artifact_id=ModelArtifactId("replay-model"),
        training_cutoff="2026-07-31T23:00:00Z",
        first_available_at="2026-08-01T00:00:00Z",
        training_dataset_artifact_ids=(dataset,),
        trainer_code_artifact_id=trainer,
        parameter_artifact_ids=(parameter,),
        source_artifact_ids=(dataset, trainer, parameter),
    )


def test_learning_object_replay_preserves_exact_semantic_identity(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    run = _training(store)
    stored = store_learning_object(run, store=store)
    replayed = load_learning_object(
        stored.artifact_id,
        store=store,
        expected_object_type="MODEL_TRAINING_RUN",
        expected_semantic_id=str(run.training_run_id),
    )
    assert replayed.semantic_id == str(run.training_run_id)
    assert replayed.payload == run.semantic_payload()


def test_learning_replay_rejects_declared_semantic_identity_tamper(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    run = _training(store)
    envelope = {
        "schema_name": "apex-stored-learning-object",
        "schema_version": 1,
        "object_type": "MODEL_TRAINING_RUN",
        "semantic_id": "wrong-id",
        "parent_artifact_ids": [],
        "source_artifact_ids": list(run.source_artifact_ids),
        "payload": run.semantic_payload(),
    }
    forged = store.put_bytes(canonical_json_bytes(envelope)).artifact_id
    with pytest.raises(ValueError, match="semantic identity mismatch"):
        load_learning_object(forged, store=store)


def test_learning_replay_rejects_missing_parent_even_when_payload_is_valid(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    run = _training(store)
    missing_parent = "sha256:" + "a" * 64
    envelope = {
        "schema_name": "apex-stored-learning-object",
        "schema_version": 1,
        "object_type": "MODEL_TRAINING_RUN",
        "semantic_id": str(run.training_run_id),
        "parent_artifact_ids": [missing_parent],
        "source_artifact_ids": list(run.source_artifact_ids),
        "payload": run.semantic_payload(),
    }
    forged = store.put_bytes(canonical_json_bytes(envelope)).artifact_id
    with pytest.raises(ValueError, match="parent artifact"):
        load_learning_object(forged, store=store)


def test_learning_replay_rejects_valid_object_used_as_wrong_type(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    run = _training(store)
    stored = store_learning_object(run, store=store)
    with pytest.raises(ValueError, match="type mismatch"):
        load_learning_object(
            stored.artifact_id,
            store=store,
            expected_object_type="MODEL_EVALUATION_REPORT",
        )


def test_learning_envelope_is_canonical_json_without_floats(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    run = _training(store)
    stored = store_learning_object(run, store=store)
    raw = store.read_bytes(stored.artifact_id)
    parsed = json.loads(raw.decode("utf-8"))
    assert raw == canonical_json_bytes(parsed)
    assert b"NaN" not in raw and b"Infinity" not in raw
