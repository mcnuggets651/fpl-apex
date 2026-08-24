"""No-hindsight evaluation dataset contracts for Apex V2 Slice 11."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .identity import OfficialPlayerId
from .ids import (
    EvaluationDatasetId,
    EvaluationTruthSetId,
    FeatureSnapshotId,
    ForecastId,
    ModelArtifactId,
    OutcomeTruthRegistryId,
)
from .learning_common import artifact_id, aware_iso, instant, positive_int
from .outcome_truth import OutcomeTarget


@dataclass(frozen=True, slots=True)
class EvaluationCase:
    forecast_id: ForecastId
    feature_snapshot_id: FeatureSnapshotId
    model_artifact_id: ModelArtifactId
    target: OutcomeTarget
    player_id: OfficialPlayerId
    gameweek: int
    prediction_sealed_at: str
    outcome_first_available_at: str
    prediction_artifact_id: str
    outcome_artifact_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, OutcomeTarget):
            raise ValueError("evaluation target must be typed OutcomeTarget")
        positive_int(self.gameweek, label="evaluation gameweek")
        predicted = aware_iso(self.prediction_sealed_at, label="prediction_sealed_at")
        outcome = aware_iso(self.outcome_first_available_at, label="outcome_first_available_at")
        if instant(outcome) <= instant(predicted):
            raise ValueError("post-event outcome must become available strictly after prediction seal")
        prediction_artifact = artifact_id(self.prediction_artifact_id, label="evaluation prediction artifact")
        outcome_artifact = artifact_id(self.outcome_artifact_id, label="evaluation outcome artifact")
        if prediction_artifact == outcome_artifact:
            raise ValueError("prediction and outcome artifacts must be separate evidence")
        object.__setattr__(self, "prediction_sealed_at", predicted)
        object.__setattr__(self, "outcome_first_available_at", outcome)
        object.__setattr__(self, "prediction_artifact_id", prediction_artifact)
        object.__setattr__(self, "outcome_artifact_id", outcome_artifact)

    def truth_payload(self) -> dict[str, object]:
        """Outcome-side identity shared by every model evaluated on the same truth case."""
        return {
            "target": self.target.value,
            "player_id": int(self.player_id),
            "gameweek": self.gameweek,
            "outcome_first_available_at": self.outcome_first_available_at,
            "outcome_artifact_id": self.outcome_artifact_id,
        }

    def semantic_payload(self) -> dict[str, object]:
        return {
            "forecast_id": str(self.forecast_id),
            "feature_snapshot_id": str(self.feature_snapshot_id),
            "model_artifact_id": str(self.model_artifact_id),
            **self.truth_payload(),
            "prediction_sealed_at": self.prediction_sealed_at,
            "prediction_artifact_id": self.prediction_artifact_id,
        }

    @property
    def case_id(self) -> str:
        return canonical_sha256({"schema_name": "apex-evaluation-case", **self.semantic_payload()})


@dataclass(frozen=True, slots=True)
class EvaluationDataset:
    season: str
    truth_registry_id: OutcomeTruthRegistryId
    cases: tuple[EvaluationCase, ...]
    source_artifact_ids: tuple[str, ...]
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported EvaluationDataset schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("evaluation dataset requires season")
        cases = tuple(
            sorted(
                self.cases,
                key=lambda row: (row.gameweek, int(row.player_id), row.target.value, row.case_id),
            )
        )
        if not cases:
            raise ValueError("evaluation dataset requires at least one case")
        case_ids = [row.case_id for row in cases]
        if len(case_ids) != len(set(case_ids)):
            raise ValueError("evaluation dataset contains duplicate cases")
        truth_keys = [canonical_sha256(row.truth_payload()) for row in cases]
        if len(truth_keys) != len(set(truth_keys)):
            raise ValueError("evaluation dataset contains duplicate model-independent truth cases")
        if len({row.model_artifact_id for row in cases}) != 1:
            raise ValueError("one evaluation dataset must evaluate one exact model artifact")
        sources = tuple(
            sorted({artifact_id(item, label="evaluation dataset source artifact") for item in self.source_artifact_ids})
        )
        required = {
            artifact
            for row in cases
            for artifact in (row.prediction_artifact_id, row.outcome_artifact_id)
        }
        if not required.issubset(set(sources)):
            raise ValueError("evaluation dataset lineage must include every prediction/outcome artifact")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "cases", cases)
        object.__setattr__(self, "source_artifact_ids", sources)

    @property
    def model_artifact_id(self) -> ModelArtifactId:
        return self.cases[0].model_artifact_id

    @property
    def first_outcome_available_at(self) -> str:
        return min((row.outcome_first_available_at for row in self.cases), key=instant)

    @property
    def truth_set_id(self) -> EvaluationTruthSetId:
        return EvaluationTruthSetId(
            canonical_sha256(
                {
                    "schema_name": "apex-evaluation-truth-set",
                    "schema_version": 1,
                    "season": self.season,
                    "truth_registry_id": str(self.truth_registry_id),
                    "cases": [row.truth_payload() for row in self.cases],
                }
            )
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-evaluation-dataset",
            "schema_version": self.schema_version,
            "season": self.season,
            "truth_registry_id": str(self.truth_registry_id),
            "truth_set_id": str(self.truth_set_id),
            "cases": [row.semantic_payload() for row in self.cases],
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def dataset_id(self) -> EvaluationDatasetId:
        return EvaluationDatasetId(canonical_sha256(self.semantic_payload()))
