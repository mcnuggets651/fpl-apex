"""Immutable model-training provenance for Apex V2 Slice 11."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .ids import ModelArtifactId, TrainingRunId
from .learning_common import artifact_id, aware_iso, instant


@dataclass(frozen=True, slots=True)
class ModelTrainingRun:
    model_artifact_id: ModelArtifactId
    training_cutoff: str
    first_available_at: str
    training_dataset_artifact_ids: tuple[str, ...]
    trainer_code_artifact_id: str
    parameter_artifact_ids: tuple[str, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ModelTrainingRun schema_version")
        if not isinstance(self.model_artifact_id, ModelArtifactId):
            raise ValueError("model training run model_artifact_id must be typed")
        cutoff = aware_iso(self.training_cutoff, label="training_cutoff")
        available = aware_iso(self.first_available_at, label="training first_available_at")
        if instant(cutoff) > instant(available):
            raise ValueError("model cannot be available before its training cutoff")
        datasets = tuple(
            sorted(
                {
                    artifact_id(item, label="training dataset artifact")
                    for item in self.training_dataset_artifact_ids
                }
            )
        )
        parameters = tuple(
            sorted(
                {
                    artifact_id(item, label="training parameter artifact")
                    for item in self.parameter_artifact_ids
                }
            )
        )
        sources = tuple(
            sorted(
                {
                    artifact_id(item, label="training source artifact")
                    for item in self.source_artifact_ids
                }
            )
        )
        trainer = artifact_id(self.trainer_code_artifact_id, label="trainer code artifact")
        if not datasets or not parameters or not sources:
            raise ValueError("training run requires dataset, parameter and source artifacts")
        if not set(datasets).issubset(set(sources)):
            raise ValueError("training dataset artifacts must be included in source lineage")
        if not set(parameters).issubset(set(sources)):
            raise ValueError("training parameter artifacts must be included in source lineage")
        if trainer not in sources:
            raise ValueError("trainer code artifact must be included in source lineage")
        object.__setattr__(self, "training_cutoff", cutoff)
        object.__setattr__(self, "first_available_at", available)
        object.__setattr__(self, "training_dataset_artifact_ids", datasets)
        object.__setattr__(self, "parameter_artifact_ids", parameters)
        object.__setattr__(self, "trainer_code_artifact_id", trainer)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-model-training-run",
            "schema_version": self.schema_version,
            "model_artifact_id": str(self.model_artifact_id),
            "training_cutoff": self.training_cutoff,
            "first_available_at": self.first_available_at,
            "training_dataset_artifact_ids": list(self.training_dataset_artifact_ids),
            "trainer_code_artifact_id": self.trainer_code_artifact_id,
            "parameter_artifact_ids": list(self.parameter_artifact_ids),
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def training_run_id(self) -> TrainingRunId:
        return TrainingRunId(canonical_sha256(self.semantic_payload()))
