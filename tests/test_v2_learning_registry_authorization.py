from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.learning_store import load_learning_object, store_learning_object
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.ids import (
    LearningPolicyId,
    ModelArtifactId,
    ModelComparisonId,
    ModelEvaluationId,
)
from apex_fpl.core.learning_common import ModelPromotionDecision
from apex_fpl.core.learning_promotion import ModelPromotionCertificate, ModelRegistryGeneration


def _put(store: FileSystemArtifactStore, text: str) -> str:
    return store.put_bytes(text.encode("utf-8")).artifact_id


def _promotion(
    store: FileSystemArtifactStore,
    *,
    candidate: str,
    evidence_label: str,
) -> ModelPromotionCertificate:
    evidence = _put(store, evidence_label)
    return ModelPromotionCertificate(
        candidate_model_id=ModelArtifactId(candidate),
        incumbent_model_id=ModelArtifactId("incumbent"),
        candidate_evaluation_id=ModelEvaluationId(f"{candidate}-evaluation"),
        incumbent_evaluation_id=ModelEvaluationId("incumbent-evaluation"),
        comparison_id=ModelComparisonId(f"{candidate}-comparison"),
        policy_id=LearningPolicyId("policy"),
        decision=ModelPromotionDecision.PROMOTE,
        reason="synthetic qualified promotion",
        source_artifact_ids=(evidence,),
    )


def test_model_registry_replay_requires_exact_retained_promotion_certificate(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    promotion = _promotion(store, candidate="candidate", evidence_label="promotion-evidence")
    promotion_artifact = store_learning_object(promotion, store=store).artifact_id
    bootstrap = _put(store, "registry-bootstrap")
    generation = ModelRegistryGeneration(
        season="2026-2027",
        generation=1,
        parent_generation_id=None,
        registered_model_ids=(ModelArtifactId("candidate"), ModelArtifactId("incumbent")),
        champion_model_id=ModelArtifactId("candidate"),
        promotion_id=promotion.promotion_id,
        source_artifact_ids=(bootstrap, promotion_artifact),
    )
    stored = store_learning_object(generation, store=store)
    replayed = load_learning_object(
        stored.artifact_id,
        store=store,
        expected_object_type="MODEL_REGISTRY_GENERATION",
        expected_semantic_id=str(generation.generation_id),
    )
    assert replayed.semantic_id == str(generation.generation_id)


def test_model_registry_replay_rejects_unrelated_valid_promotion_artifact(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    expected = _promotion(store, candidate="candidate", evidence_label="expected-evidence")
    unrelated = _promotion(store, candidate="other-candidate", evidence_label="other-evidence")
    unrelated_artifact = store_learning_object(unrelated, store=store).artifact_id
    bootstrap = _put(store, "registry-bootstrap")

    generation = ModelRegistryGeneration(
        season="2026-2027",
        generation=1,
        parent_generation_id=None,
        registered_model_ids=(ModelArtifactId("candidate"), ModelArtifactId("incumbent")),
        champion_model_id=ModelArtifactId("candidate"),
        promotion_id=expected.promotion_id,
        source_artifact_ids=(bootstrap, unrelated_artifact),
    )
    payload = generation.semantic_payload()
    envelope = {
        "schema_name": "apex-stored-learning-object",
        "schema_version": 1,
        "object_type": "MODEL_REGISTRY_GENERATION",
        "semantic_id": canonical_sha256(payload),
        "parent_artifact_ids": [],
        "source_artifact_ids": list(generation.source_artifact_ids),
        "payload": payload,
    }
    forged = store.put_bytes(canonical_json_bytes(envelope)).artifact_id
    with pytest.raises(ValueError, match="exactly one retained promotion certificate"):
        load_learning_object(forged, store=store)
