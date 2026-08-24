"""Promotion certificates and immutable registry generations for Apex V2 Slice 11."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .ids import (
    LearningPolicyId,
    ModelArtifactId,
    ModelComparisonId,
    ModelEvaluationId,
    ModelPromotionId,
    ModelRegistryGenerationId,
)
from .learning_common import ModelPromotionDecision, artifact_id, positive_int


@dataclass(frozen=True, slots=True)
class ModelPromotionCertificate:
    candidate_model_id: ModelArtifactId
    incumbent_model_id: ModelArtifactId
    candidate_evaluation_id: ModelEvaluationId
    incumbent_evaluation_id: ModelEvaluationId
    comparison_id: ModelComparisonId
    policy_id: LearningPolicyId
    decision: ModelPromotionDecision
    reason: str
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported ModelPromotionCertificate schema_version")
        if self.candidate_model_id == self.incumbent_model_id:
            raise ValueError("promotion candidate cannot equal incumbent")
        if not isinstance(self.decision, ModelPromotionDecision):
            raise ValueError("model promotion decision must be typed")
        reason = str(self.reason).strip()
        if not reason:
            raise ValueError("model promotion certificate requires reason")
        sources = tuple(
            sorted(
                {
                    artifact_id(item, label="model promotion source artifact")
                    for item in self.source_artifact_ids
                }
            )
        )
        if not sources:
            raise ValueError("model promotion certificate requires immutable source evidence")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-promotion-certificate",
            "schema_version": self.schema_version,
            "candidate_model_id": str(self.candidate_model_id),
            "incumbent_model_id": str(self.incumbent_model_id),
            "candidate_evaluation_id": str(self.candidate_evaluation_id),
            "incumbent_evaluation_id": str(self.incumbent_evaluation_id),
            "comparison_id": str(self.comparison_id),
            "policy_id": str(self.policy_id),
            "decision": self.decision.value,
            "reason": self.reason,
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def promotion_id(self) -> ModelPromotionId:
        return ModelPromotionId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class ModelRegistryGeneration:
    season: str
    generation: int
    parent_generation_id: ModelRegistryGenerationId | None
    registered_model_ids: tuple[ModelArtifactId, ...]
    champion_model_id: ModelArtifactId | None
    promotion_id: ModelPromotionId | None
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported ModelRegistryGeneration schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("model registry generation requires season")
        generation = positive_int(self.generation, label="model registry generation")
        models = tuple(sorted(set(self.registered_model_ids), key=str))
        if not models:
            raise ValueError("model registry generation requires registered models")
        if generation == 1 and self.parent_generation_id is not None:
            raise ValueError("first model registry generation cannot have parent")
        if generation > 1 and self.parent_generation_id is None:
            raise ValueError("later model registry generation requires parent identity")
        if self.champion_model_id is not None:
            if self.champion_model_id not in models:
                raise ValueError("model registry champion must be registered")
            if self.promotion_id is None:
                raise ValueError("model registry champion requires promotion certificate identity")
        elif self.promotion_id is not None:
            raise ValueError("promotion certificate cannot exist without resulting champion")
        sources = tuple(
            sorted(
                {
                    artifact_id(item, label="model registry generation source artifact")
                    for item in self.source_artifact_ids
                }
            )
        )
        if not sources:
            raise ValueError("model registry generation requires immutable source evidence")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "generation", generation)
        object.__setattr__(self, "registered_model_ids", models)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-registry-generation",
            "schema_version": self.schema_version,
            "season": self.season,
            "generation": self.generation,
            "parent_generation_id": (
                None if self.parent_generation_id is None else str(self.parent_generation_id)
            ),
            "registered_model_ids": [str(item) for item in self.registered_model_ids],
            "champion_model_id": (
                None if self.champion_model_id is None else str(self.champion_model_id)
            ),
            "promotion_id": None if self.promotion_id is None else str(self.promotion_id),
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def generation_id(self) -> ModelRegistryGenerationId:
        return ModelRegistryGenerationId(canonical_sha256(self.semantic_payload()))
