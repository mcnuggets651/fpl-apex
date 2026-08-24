"""Admission registry for probabilistic forecast model artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.forecast import ForecastModelArtifact, ModelQualificationState
from apex_fpl.core.ids import ModelArtifactId


@dataclass(frozen=True, slots=True)
class ForecastModelRegistry:
    models: tuple[ForecastModelArtifact, ...]
    champion_model_id: ModelArtifactId | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported forecast model registry schema_version")
        ids = [model.model_artifact_id for model in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("forecast model registry contains duplicate model artifacts")
        if self.champion_model_id is not None:
            champion = self.get(self.champion_model_id)
            if champion is None:
                raise ValueError("forecast champion_model_id is not registered")
            if champion.qualification_state is not ModelQualificationState.QUALIFIED:
                raise ValueError("forecast champion must be QUALIFIED")

    def get(self, model_artifact_id: ModelArtifactId) -> ForecastModelArtifact | None:
        return next(
            (model for model in self.models if model.model_artifact_id == model_artifact_id),
            None,
        )

    def champion(self) -> ForecastModelArtifact | None:
        if self.champion_model_id is None:
            return None
        return self.get(self.champion_model_id)

    def verify_model_artifacts(
        self,
        model: ForecastModelArtifact,
        *,
        store: ArtifactStore,
        production: bool,
    ) -> None:
        if self.get(model.model_artifact_id) is None:
            raise ValueError("forecast model is not registered")
        for artifact_id in model.parameter_artifact_ids:
            if not store.verify(artifact_id):
                raise ValueError(f"forecast model parameter artifact is missing/corrupt: {artifact_id}")
        qualification = model.qualification_artifact_id
        if qualification is not None and not store.verify(qualification):
            raise ValueError("forecast model qualification artifact is missing/corrupt")
        if production:
            if model.qualification_state is not ModelQualificationState.QUALIFIED:
                raise ValueError("production forecast model is not QUALIFIED")
            if qualification is None:
                raise ValueError("production forecast model has no qualification artifact")
            if self.champion_model_id != model.model_artifact_id:
                raise ValueError("production forecast model is not the registered champion")


def _models(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("forecast models must be an array of objects")
    return [dict(row) for row in value]


def load_forecast_model_registry(path: str | Path) -> ForecastModelRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or int(payload.get("schema_version", -1)) != 1:
        raise ValueError("forecast model registry requires schema_version 1")
    models = tuple(
        ForecastModelArtifact(
            model_name=str(row.get("model_name") or ""),
            model_version=str(row.get("model_version") or ""),
            feature_contract=str(row.get("feature_contract") or ""),
            prediction_contract=str(row.get("prediction_contract") or ""),
            parameter_artifact_ids=tuple(
                str(item) for item in (row.get("parameter_artifact_ids") or [])
            ),
            qualification_state=ModelQualificationState(
                str(row.get("qualification_state") or "")
            ),
            qualification_artifact_id=(
                None
                if row.get("qualification_artifact_id") is None
                else str(row.get("qualification_artifact_id"))
            ),
            valid_seasons=tuple(str(item) for item in (row.get("valid_seasons") or [])),
            trained_through=str(row.get("trained_through") or ""),
            first_available_at=str(row.get("first_available_at") or ""),
            max_horizon_gameweeks=int(row.get("max_horizon_gameweeks") or 0),
        )
        for row in _models(payload.get("models"))
    )
    champion_raw = payload.get("champion_model_id")
    champion = None if champion_raw is None else ModelArtifactId(str(champion_raw))
    return ForecastModelRegistry(
        models=models,
        champion_model_id=champion,
        schema_version=1,
    )
