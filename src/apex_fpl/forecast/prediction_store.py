"""Persist and replay model prediction batches before FPL scoring compilation."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.forecast import (
    PredictionBatch,
    PredictionDisposition,
    PredictionRow,
    PlayerFixtureScenario,
    PlayerFixtureTarget,
    PlayerMatchOutcome,
    UncertaintyKind,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import FeatureSnapshotId, GlobalWorldId, ModelArtifactId, PredictionBatchId


PREDICTION_BATCH_SCHEMA = "apex-prediction-batch-envelope"
PREDICTION_BATCH_SCHEMA_VERSION = 1


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("prediction batch artifact ID must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("prediction batch artifact digest is invalid") from exc
    return text


@dataclass(frozen=True, slots=True)
class StoredPredictionBatch:
    batch: PredictionBatch
    artifact_id: str


def store_prediction_batch(
    batch: PredictionBatch,
    *,
    store: ArtifactStore,
) -> StoredPredictionBatch:
    envelope = {
        "schema_name": PREDICTION_BATCH_SCHEMA,
        "schema_version": PREDICTION_BATCH_SCHEMA_VERSION,
        "prediction_batch_id": str(batch.prediction_batch_id),
        "batch": batch.semantic_payload(),
        "rows": [row.semantic_payload() for row in batch.rows],
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=PREDICTION_BATCH_SCHEMA,
        schema_version=str(PREDICTION_BATCH_SCHEMA_VERSION),
    )
    return StoredPredictionBatch(batch=batch, artifact_id=ref.artifact_id)


def _target(payload: dict[str, object]) -> PlayerFixtureTarget:
    return PlayerFixtureTarget(
        fixture_id=int(payload["fixture_id"]),
        gameweek=int(payload["gameweek"]),
        player_id=OfficialPlayerId(int(payload["player_id"])),
        team_id=int(payload["team_id"]),
        opponent_team_id=int(payload["opponent_team_id"]),
        is_home=bool(payload["is_home"]),
        position=str(payload["position"]),
    )


def _outcome(payload: dict[str, object]) -> PlayerMatchOutcome:
    return PlayerMatchOutcome(
        minutes=int(payload["minutes"]),
        goals=int(payload.get("goals", 0)),
        assists=int(payload.get("assists", 0)),
        goals_conceded_while_on_pitch=int(payload.get("goals_conceded_while_on_pitch", 0)),
        goalkeeper_saves=int(payload.get("goalkeeper_saves", 0)),
        penalty_saves=int(payload.get("penalty_saves", 0)),
        penalty_misses=int(payload.get("penalty_misses", 0)),
        defensive_contributions=int(payload.get("defensive_contributions", 0)),
        yellow_cards=int(payload.get("yellow_cards", 0)),
        red_cards=int(payload.get("red_cards", 0)),
        own_goals=int(payload.get("own_goals", 0)),
        bonus_points=int(payload.get("bonus_points", 0)),
    )


def _scenario(payload: dict[str, object]) -> PlayerFixtureScenario:
    outcome = payload.get("outcome")
    if not isinstance(outcome, dict):
        raise ValueError("stored prediction scenario outcome is malformed")
    return PlayerFixtureScenario(
        scenario_id=str(payload["scenario_id"]),
        probability_bps=int(payload["probability_bps"]),
        outcome=_outcome(dict(outcome)),
    )


def _row(payload: dict[str, object]) -> PredictionRow:
    target = payload.get("target")
    scenarios = payload.get("scenarios")
    if not isinstance(target, dict) or not isinstance(scenarios, list):
        raise ValueError("stored prediction row is malformed")
    uncertainty_raw = payload.get("uncertainty_kind")
    return PredictionRow(
        target=_target(dict(target)),
        disposition=PredictionDisposition(str(payload["disposition"])),
        scenarios=tuple(
            _scenario(dict(item))
            for item in scenarios
            if isinstance(item, dict)
        ),
        abstention_reason=(
            None
            if payload.get("abstention_reason") is None
            else str(payload["abstention_reason"])
        ),
        uncertainty_kind=(
            None if uncertainty_raw is None else UncertaintyKind(str(uncertainty_raw))
        ),
        deterministic_reason=(
            None
            if payload.get("deterministic_reason") is None
            else str(payload["deterministic_reason"])
        ),
    )


def load_prediction_batch(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredPredictionBatch:
    current = _artifact_id(artifact_id)
    raw = store.read_bytes(current)
    try:
        envelope = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("prediction batch artifact is not UTF-8 JSON") from exc
    if not isinstance(envelope, dict) or envelope.get("schema_name") != PREDICTION_BATCH_SCHEMA:
        raise ValueError("not an Apex prediction batch artifact")
    if int(envelope.get("schema_version", -1)) != PREDICTION_BATCH_SCHEMA_VERSION:
        raise ValueError("unsupported stored prediction batch schema_version")
    semantic = envelope.get("batch")
    rows_raw = envelope.get("rows")
    if not isinstance(semantic, dict) or not isinstance(rows_raw, list):
        raise ValueError("prediction batch envelope is incomplete")
    rows = tuple(_row(dict(item)) for item in rows_raw if isinstance(item, dict))
    if len(rows) != len(rows_raw):
        raise ValueError("prediction batch contains malformed row entries")
    gameweeks = semantic.get("gameweeks")
    if not isinstance(gameweeks, list):
        raise ValueError("prediction batch gameweeks are malformed")
    batch = PredictionBatch(
        season=str(semantic["season"]),
        feature_snapshot_id=FeatureSnapshotId(str(semantic["feature_snapshot_id"])),
        feature_cutoff=str(semantic["feature_cutoff"]),
        global_world_id=GlobalWorldId(str(semantic["global_world_id"])),
        model_artifact_id=ModelArtifactId(str(semantic["model_artifact_id"])),
        gameweeks=tuple(int(item) for item in gameweeks),
        rows=rows,
        schema_version=int(semantic.get("schema_version", -1)),
    )
    declared = PredictionBatchId(str(envelope.get("prediction_batch_id") or ""))
    if declared != batch.prediction_batch_id:
        raise ValueError("prediction batch semantic identity mismatch")
    declared_rows = semantic.get("prediction_row_ids")
    if not isinstance(declared_rows, list) or [row.prediction_row_id for row in batch.rows] != declared_rows:
        raise ValueError("prediction batch row identity list mismatch")
    return StoredPredictionBatch(batch=batch, artifact_id=current)
