"""Immutable storage and strict replay for exact ForecastModelArtifact semantics."""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.forecast import ForecastModelArtifact, ModelQualificationState
from apex_fpl.core.ids import ModelArtifactId


def _object(content: bytes) -> dict[str, object]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("forecast model artifact is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("forecast model artifact must be a JSON object")
    return dict(value)


def _int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _string_array(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    return tuple(value)


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be string or null")
    return value


def store_forecast_model(model: ForecastModelArtifact, *, store: ArtifactStore) -> str:
    """Store semantic bytes so the ArtifactStore ID is exactly ModelArtifactId."""

    ref = store.put_bytes(
        canonical_json_bytes(model.semantic_payload()),
        media_type="application/json",
        schema_name="apex-forecast-model-artifact",
        schema_version=str(model.schema_version),
    )
    if ref.artifact_id != str(model.model_artifact_id):
        raise ValueError("stored forecast model identity does not match semantic identity")
    return ref.artifact_id


def load_forecast_model(
    model_id: ModelArtifactId | str,
    *,
    store: ArtifactStore,
) -> ForecastModelArtifact:
    expected = ModelArtifactId(str(model_id))
    raw = _object(store.read_bytes(str(expected)))
    if raw.get("schema_name") != "apex-forecast-model-artifact":
        raise ValueError("not an Apex ForecastModelArtifact")
    model = ForecastModelArtifact(
        model_name=str(raw.get("model_name") or ""),
        model_version=str(raw.get("model_version") or ""),
        feature_contract=str(raw.get("feature_contract") or ""),
        prediction_contract=str(raw.get("prediction_contract") or ""),
        parameter_artifact_ids=_string_array(
            raw.get("parameter_artifact_ids"), label="model parameter_artifact_ids"
        ),
        qualification_state=ModelQualificationState(
            str(raw.get("qualification_state") or "")
        ),
        qualification_artifact_id=_optional_text(
            raw.get("qualification_artifact_id"),
            label="model qualification_artifact_id",
        ),
        valid_seasons=_string_array(raw.get("valid_seasons"), label="model valid_seasons"),
        trained_through=str(raw.get("trained_through") or ""),
        first_available_at=str(raw.get("first_available_at") or ""),
        max_horizon_gameweeks=_int(
            raw.get("max_horizon_gameweeks"), label="model max_horizon_gameweeks"
        ),
        schema_version=_int(raw.get("schema_version"), label="model schema_version"),
    )
    if model.model_artifact_id != expected:
        raise ValueError("forecast model semantic identity mismatch")
    return model
