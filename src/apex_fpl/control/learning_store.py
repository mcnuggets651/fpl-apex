"""Strict content-addressed persistence for Apex V2 Slice 11 learning objects."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.learning_dataset import EvaluationDataset
from apex_fpl.core.learning_evaluation import ModelComparisonReport, ModelEvaluationReport
from apex_fpl.core.learning_observations import EvaluationObservationSet
from apex_fpl.core.learning_policy import LearningEvaluationPolicy
from apex_fpl.core.learning_promotion import ModelPromotionCertificate, ModelRegistryGeneration
from apex_fpl.core.learning_training import ModelTrainingRun


LearningObject = (
    ModelTrainingRun
    | EvaluationDataset
    | EvaluationObservationSet
    | LearningEvaluationPolicy
    | ModelEvaluationReport
    | ModelComparisonReport
    | ModelPromotionCertificate
    | ModelRegistryGeneration
)


@dataclass(frozen=True, slots=True)
class StoredLearningObject:
    object_type: str
    semantic_id: str
    artifact_id: str
    payload: dict[str, object]
    parent_artifact_ids: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]


_OBJECT_TYPES = {
    ModelTrainingRun: "MODEL_TRAINING_RUN",
    EvaluationDataset: "EVALUATION_DATASET",
    EvaluationObservationSet: "EVALUATION_OBSERVATION_SET",
    LearningEvaluationPolicy: "LEARNING_EVALUATION_POLICY",
    ModelEvaluationReport: "MODEL_EVALUATION_REPORT",
    ModelComparisonReport: "MODEL_COMPARISON_REPORT",
    ModelPromotionCertificate: "MODEL_PROMOTION_CERTIFICATE",
    ModelRegistryGeneration: "MODEL_REGISTRY_GENERATION",
}


def _semantic_id(value: LearningObject) -> str:
    if isinstance(value, ModelTrainingRun):
        return str(value.training_run_id)
    if isinstance(value, EvaluationDataset):
        return str(value.dataset_id)
    if isinstance(value, EvaluationObservationSet):
        return str(value.observation_set_id)
    if isinstance(value, LearningEvaluationPolicy):
        return str(value.policy_id)
    if isinstance(value, ModelEvaluationReport):
        return str(value.evaluation_id)
    if isinstance(value, ModelComparisonReport):
        return str(value.comparison_id)
    if isinstance(value, ModelPromotionCertificate):
        return str(value.promotion_id)
    if isinstance(value, ModelRegistryGeneration):
        return str(value.generation_id)
    raise TypeError(f"unsupported learning object: {type(value)!r}")


def _source_artifacts(value: LearningObject) -> tuple[str, ...]:
    if isinstance(value, LearningEvaluationPolicy):
        return tuple(
            sorted(
                item
                for item in (value.qualification_artifact_id, value.promotion_rule_artifact_id)
                if item is not None
            )
        )
    source_ids = getattr(value, "source_artifact_ids", ())
    return tuple(sorted(set(source_ids)))


def _verify(store: ArtifactStore, artifact_ids: tuple[str, ...], *, label: str) -> None:
    for artifact_id in artifact_ids:
        if not store.verify(artifact_id):
            raise ValueError(f"{label} missing/corrupt: {artifact_id}")


def _matching_promotion_sources(
    *,
    promotion_id: str,
    source_artifact_ids: tuple[str, ...],
    store: ArtifactStore,
) -> tuple[str, ...]:
    matches: list[str] = []
    for source_artifact_id in source_artifact_ids:
        try:
            load_learning_object(
                source_artifact_id,
                store=store,
                expected_object_type="MODEL_PROMOTION_CERTIFICATE",
                expected_semantic_id=promotion_id,
            )
        except (ValueError, FileNotFoundError):
            continue
        matches.append(source_artifact_id)
    return tuple(matches)


def _verify_registry_promotion_binding(
    *,
    promotion_id: object,
    source_artifact_ids: tuple[str, ...],
    store: ArtifactStore,
) -> None:
    if promotion_id is None:
        return
    if not isinstance(promotion_id, str) or not promotion_id.strip():
        raise ValueError("model registry generation has invalid promotion_id")
    matches = _matching_promotion_sources(
        promotion_id=promotion_id,
        source_artifact_ids=source_artifact_ids,
        store=store,
    )
    if len(matches) != 1:
        raise ValueError(
            "model registry champion must bind exactly one retained promotion certificate artifact"
        )


def store_learning_object(
    value: LearningObject,
    *,
    store: ArtifactStore,
    parent_artifact_ids: tuple[str, ...] = (),
) -> StoredLearningObject:
    object_type = _OBJECT_TYPES.get(type(value))
    if object_type is None:
        raise TypeError(f"unsupported learning object: {type(value)!r}")
    parents = tuple(sorted(set(parent_artifact_ids)))
    sources = _source_artifacts(value)
    _verify(store, parents, label="learning parent artifact")
    _verify(store, sources, label="learning source artifact")
    if isinstance(value, ModelRegistryGeneration):
        _verify_registry_promotion_binding(
            promotion_id=(None if value.promotion_id is None else str(value.promotion_id)),
            source_artifact_ids=sources,
            store=store,
        )
    payload = value.semantic_payload()
    semantic_id = _semantic_id(value)
    if canonical_sha256(payload) != semantic_id:
        raise ValueError("learning object semantic identity does not match canonical payload")
    envelope = {
        "schema_name": "apex-stored-learning-object",
        "schema_version": 1,
        "object_type": object_type,
        "semantic_id": semantic_id,
        "parent_artifact_ids": list(parents),
        "source_artifact_ids": list(sources),
        "payload": payload,
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-learning-object",
        schema_version="1",
    )
    return StoredLearningObject(
        object_type,
        semantic_id,
        ref.artifact_id,
        payload,
        parents,
        sources,
    )


def load_learning_object(
    artifact_id: str,
    *,
    store: ArtifactStore,
    expected_object_type: str | None = None,
    expected_semantic_id: str | None = None,
) -> StoredLearningObject:
    try:
        raw = json.loads(store.read_bytes(artifact_id).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("stored learning object is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("stored learning object must be JSON object")
    if raw.get("schema_name") != "apex-stored-learning-object" or raw.get("schema_version") != 1:
        raise ValueError("unsupported stored learning object schema")
    object_type = raw.get("object_type")
    semantic_id = raw.get("semantic_id")
    payload = raw.get("payload")
    parents = raw.get("parent_artifact_ids")
    sources = raw.get("source_artifact_ids")
    if not isinstance(object_type, str) or object_type not in set(_OBJECT_TYPES.values()):
        raise ValueError("stored learning object has invalid object_type")
    if not isinstance(semantic_id, str) or not semantic_id.strip():
        raise ValueError("stored learning object has invalid semantic_id")
    if not isinstance(payload, dict):
        raise ValueError("stored learning object payload must be object")
    if not isinstance(parents, list) or any(not isinstance(item, str) for item in parents):
        raise ValueError("stored learning object parents must be string array")
    if not isinstance(sources, list) or any(not isinstance(item, str) for item in sources):
        raise ValueError("stored learning object sources must be string array")
    parent_ids = tuple(sorted(set(parents)))
    source_ids = tuple(sorted(set(sources)))
    if len(parent_ids) != len(parents) or len(source_ids) != len(sources):
        raise ValueError("stored learning object parent/source arrays must be canonical unique sets")
    if canonical_sha256(payload) != semantic_id:
        raise ValueError("stored learning object semantic identity mismatch")
    if expected_object_type is not None and object_type != expected_object_type:
        raise ValueError("stored learning object type mismatch")
    if expected_semantic_id is not None and semantic_id != expected_semantic_id:
        raise ValueError("stored learning object does not match expected semantic identity")
    _verify(store, parent_ids, label="stored learning parent artifact")
    _verify(store, source_ids, label="stored learning source artifact")
    if object_type == "MODEL_REGISTRY_GENERATION":
        _verify_registry_promotion_binding(
            promotion_id=payload.get("promotion_id"),
            source_artifact_ids=source_ids,
            store=store,
        )
    return StoredLearningObject(
        object_type,
        semantic_id,
        artifact_id,
        dict(payload),
        parent_ids,
        source_ids,
    )
