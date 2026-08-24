from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.learning_store import load_learning_object, store_learning_object
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


def _promotion(store: FileSystemArtifactStore) -> tuple[ModelPromotionCertificate, str]:
    evidence = _put(store, "promotion-evidence")
    promotion = ModelPromotionCertificate(
        candidate_model_id=ModelArtifactId("candidate"),
        incumbent_model_id=ModelArtifactId("incumbent"),
        candidate_evaluation_id=ModelEvaluationId("candidate-eval"),
        incumbent_evaluation_id=ModelEvaluationId("incumbent-eval"),
        comparison_id=ModelComparisonId("comparison"),
        policy_id=LearningPolicyId("policy"),
        decision=ModelPromotionDecision.PROMOTE,
        reason="qualified synthetic promotion",
        source_artifact_ids=(evidence,),
    )
    artifact_id = store_learning_object(promotion, store=store).artifact_id
    return promotion, artifact_id


def test_registry_generation_binds_exact_retained_promotion_certificate(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    promotion, promotion_artifact = _promotion(store)
    bootstrap = _put(store, "registry-bootstrap")
    generation = ModelRegistryGeneration(
        season="2026-2027",
        generation=1,
        parent_generation_id=None,
        registered_model_ids=(promotion.candidate_model_id, promotion.incumbent_model_id),
        champion_model_id=promotion.candidate_model_id,
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


def test_registry_generation_rejects_promotion_id_without_matching_promotion_artifact(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    promotion, _ = _promotion(store)
    unrelated = _put(store, "valid-but-unrelated-registry-source")
    generation = ModelRegistryGeneration(
        season="2026-2027",
        generation=1,
        parent_generation_id=None,
        registered_model_ids=(promotion.candidate_model_id, promotion.incumbent_model_id),
        champion_model_id=promotion.candidate_model_id,
        promotion_id=promotion.promotion_id,
        source_artifact_ids=(unrelated,),
    )
    with pytest.raises(ValueError, match="exactly one retained promotion certificate"):
        store_learning_object(generation, store=store)
