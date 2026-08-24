from __future__ import annotations

import pytest

from apex_fpl.core.ids import (
    LearningPolicyId,
    ModelArtifactId,
    ModelComparisonId,
    ModelEvaluationId,
    ModelPromotionId,
    ModelRegistryGenerationId,
)
from apex_fpl.core.learning_common import ModelPromotionDecision
from apex_fpl.core.learning_promotion import ModelPromotionCertificate, ModelRegistryGeneration

ARTIFACT = "sha256:" + "a" * 64


def _promotion_kwargs() -> dict[str, object]:
    return {
        "candidate_model_id": ModelArtifactId("candidate"),
        "incumbent_model_id": ModelArtifactId("incumbent"),
        "candidate_evaluation_id": ModelEvaluationId("candidate-evaluation"),
        "incumbent_evaluation_id": ModelEvaluationId("incumbent-evaluation"),
        "comparison_id": ModelComparisonId("comparison"),
        "policy_id": LearningPolicyId("policy"),
        "decision": ModelPromotionDecision.PROMOTE,
        "reason": "qualified comparison passed",
        "source_artifact_ids": (ARTIFACT,),
    }


def test_model_promotion_rejects_raw_semantic_ids() -> None:
    ModelPromotionCertificate(**_promotion_kwargs())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="candidate_model_id must be typed"):
        ModelPromotionCertificate(
            **{**_promotion_kwargs(), "candidate_model_id": "candidate"}  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="comparison_id must be typed"):
        ModelPromotionCertificate(
            **{**_promotion_kwargs(), "comparison_id": "comparison"}  # type: ignore[arg-type]
        )


def test_model_registry_generation_rejects_raw_parent_champion_and_registered_ids() -> None:
    base = {
        "season": "2026-2027",
        "generation": 2,
        "parent_generation_id": ModelRegistryGenerationId("parent"),
        "registered_model_ids": (ModelArtifactId("candidate"), ModelArtifactId("incumbent")),
        "champion_model_id": ModelArtifactId("candidate"),
        "promotion_id": ModelPromotionId("promotion"),
        "source_artifact_ids": (ARTIFACT,),
    }
    ModelRegistryGeneration(**base)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="parent_generation_id must be typed"):
        ModelRegistryGeneration(
            **{**base, "parent_generation_id": "parent"}  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="registered_model_ids must be typed"):
        ModelRegistryGeneration(
            **{**base, "registered_model_ids": ("candidate", "incumbent")}  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="champion_model_id must be typed"):
        ModelRegistryGeneration(
            **{**base, "champion_model_id": "candidate"}  # type: ignore[arg-type]
        )
