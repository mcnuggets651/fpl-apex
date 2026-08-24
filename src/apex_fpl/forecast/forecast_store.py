"""Persist and replay compiled probabilistic forecasts."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.forecast import (
    DiscreteIntegerDistribution,
    Forecast,
    ForecastAbstention,
    ForecastUncertainty,
    ForecastUseMode,
    ModelQualificationState,
    PlayerFixtureForecast,
    PlayerFixtureTarget,
    UncertaintyKind,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    FeatureSnapshotId,
    ForecastId,
    GlobalWorldId,
    ModelArtifactId,
    PredictionBatchId,
    RuleSetId,
)


FORECAST_SCHEMA = "apex-probabilistic-forecast-envelope"
FORECAST_SCHEMA_VERSION = 1


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("forecast artifact ID must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("forecast artifact digest is invalid") from exc
    return text


@dataclass(frozen=True, slots=True)
class StoredForecast:
    forecast: Forecast
    artifact_id: str


def store_forecast(forecast: Forecast, *, store: ArtifactStore) -> StoredForecast:
    envelope = {
        "schema_name": FORECAST_SCHEMA,
        "schema_version": FORECAST_SCHEMA_VERSION,
        "forecast_id": str(forecast.forecast_id),
        "forecast": forecast.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=FORECAST_SCHEMA,
        schema_version=str(FORECAST_SCHEMA_VERSION),
    )
    return StoredForecast(forecast=forecast, artifact_id=ref.artifact_id)


def _target(payload: dict[str, object]) -> PlayerFixtureTarget:
    is_home = payload.get("is_home")
    if not isinstance(is_home, bool):
        raise ValueError("stored forecast target is_home is malformed")
    return PlayerFixtureTarget(
        fixture_id=int(payload["fixture_id"]),
        gameweek=int(payload["gameweek"]),
        player_id=OfficialPlayerId(int(payload["player_id"])),
        team_id=int(payload["team_id"]),
        opponent_team_id=int(payload["opponent_team_id"]),
        is_home=is_home,
        position=str(payload["position"]),
    )


def _distribution(value: object) -> DiscreteIntegerDistribution:
    if not isinstance(value, list):
        raise ValueError("stored forecast distribution must be an array")
    rows: list[tuple[int, int]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            raise ValueError("stored forecast distribution row is malformed")
        rows.append((int(item[0]), int(item[1])))
    return DiscreteIntegerDistribution(tuple(rows))


def _uncertainty(payload: dict[str, object]) -> ForecastUncertainty:
    return ForecastUncertainty(
        uncertainty_kind=UncertaintyKind(str(payload["uncertainty_kind"])),
        deterministic_reason=(
            None
            if payload.get("deterministic_reason") is None
            else str(payload["deterministic_reason"])
        ),
        scenario_count=int(payload["scenario_count"]),
        minutes_p10=int(payload["minutes_p10"]),
        minutes_p50=int(payload["minutes_p50"]),
        minutes_p90=int(payload["minutes_p90"]),
        points_p10=int(payload["points_p10"]),
        points_p50=int(payload["points_p50"]),
        points_p90=int(payload["points_p90"]),
        appearance_probability_bps=int(payload["appearance_probability_bps"]),
        sixty_plus_probability_bps=int(payload["sixty_plus_probability_bps"]),
    )


def _row(payload: dict[str, object]) -> PlayerFixtureForecast:
    target = payload.get("target")
    uncertainty = payload.get("uncertainty")
    if not isinstance(target, dict) or not isinstance(uncertainty, dict):
        raise ValueError("stored forecast row is malformed")
    return PlayerFixtureForecast(
        target=_target(dict(target)),
        prediction_row_id=str(payload["prediction_row_id"]),
        minutes_distribution=_distribution(payload.get("minutes_distribution")),
        points_distribution=_distribution(payload.get("points_distribution")),
        uncertainty=_uncertainty(dict(uncertainty)),
    )


def _abstention(payload: dict[str, object]) -> ForecastAbstention:
    target = payload.get("target")
    if not isinstance(target, dict):
        raise ValueError("stored forecast abstention target is malformed")
    return ForecastAbstention(
        target=_target(dict(target)),
        prediction_row_id=str(payload["prediction_row_id"]),
        reason=str(payload["reason"]),
    )


def load_forecast(artifact_id: str, *, store: ArtifactStore) -> StoredForecast:
    current = _artifact_id(artifact_id)
    raw = store.read_bytes(current)
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("forecast artifact is not UTF-8 JSON") from exc
    if not isinstance(envelope, dict) or envelope.get("schema_name") != FORECAST_SCHEMA:
        raise ValueError("not an Apex probabilistic forecast artifact")
    if int(envelope.get("schema_version", -1)) != FORECAST_SCHEMA_VERSION:
        raise ValueError("unsupported stored forecast schema_version")
    payload = envelope.get("forecast")
    if not isinstance(payload, dict):
        raise ValueError("forecast envelope is incomplete")
    rows_raw = payload.get("rows")
    abstentions_raw = payload.get("abstentions")
    if not isinstance(rows_raw, list) or not isinstance(abstentions_raw, list):
        raise ValueError("stored forecast row arrays are malformed")
    rows = tuple(_row(dict(item)) for item in rows_raw if isinstance(item, dict))
    abstentions = tuple(
        _abstention(dict(item)) for item in abstentions_raw if isinstance(item, dict)
    )
    if len(rows) != len(rows_raw) or len(abstentions) != len(abstentions_raw):
        raise ValueError("stored forecast contains malformed rows")
    forecast = Forecast(
        season=str(payload["season"]),
        feature_snapshot_id=FeatureSnapshotId(str(payload["feature_snapshot_id"])),
        feature_cutoff=str(payload["feature_cutoff"]),
        global_world_id=GlobalWorldId(str(payload["global_world_id"])),
        ruleset_id=RuleSetId(str(payload["ruleset_id"])),
        model_artifact_id=ModelArtifactId(str(payload["model_artifact_id"])),
        prediction_batch_id=PredictionBatchId(str(payload["prediction_batch_id"])),
        use_mode=ForecastUseMode(str(payload["use_mode"])),
        model_qualification_state=ModelQualificationState(
            str(payload["model_qualification_state"])
        ),
        rows=rows,
        abstentions=abstentions,
        schema_version=int(payload.get("schema_version", -1)),
    )
    declared = ForecastId(str(envelope.get("forecast_id") or ""))
    if declared != forecast.forecast_id:
        raise ValueError("forecast semantic identity mismatch")
    return StoredForecast(forecast=forecast, artifact_id=current)
