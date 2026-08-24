"""Build, persist and replay immutable point-in-time FeatureSnapshots."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.features import (
    FeatureObservation,
    FeatureScope,
    FeatureSnapshot,
    FeatureValue,
    FeatureValueKind,
)
from apex_fpl.core.ids import FeatureSnapshotId, GlobalWorldId


FEATURE_SNAPSHOT_SCHEMA = "apex-feature-snapshot-envelope"
FEATURE_SNAPSHOT_SCHEMA_VERSION = 1


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("feature snapshot artifact ID must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("feature snapshot artifact digest is invalid") from exc
    return text


@dataclass(frozen=True, slots=True)
class StoredFeatureSnapshot:
    snapshot: FeatureSnapshot
    artifact_id: str


def build_and_store_feature_snapshot(
    *,
    season: str,
    cutoff: str,
    global_world_id: GlobalWorldId,
    observations: tuple[FeatureObservation, ...],
    input_artifact_ids: tuple[str, ...],
    store: ArtifactStore,
) -> StoredFeatureSnapshot:
    artifacts = tuple(_artifact_id(item) for item in input_artifact_ids)
    for artifact in artifacts:
        if not store.verify(artifact):
            raise ValueError(f"feature snapshot input artifact is missing/corrupt: {artifact}")
    snapshot = FeatureSnapshot(
        season=season,
        cutoff=cutoff,
        global_world_id=global_world_id,
        observations=observations,
        input_artifact_ids=artifacts,
    )
    envelope = {
        "schema_name": FEATURE_SNAPSHOT_SCHEMA,
        "schema_version": FEATURE_SNAPSHOT_SCHEMA_VERSION,
        "feature_snapshot_id": str(snapshot.snapshot_id),
        "snapshot": snapshot.semantic_payload(),
        "observations": [row.semantic_payload() for row in snapshot.observations],
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=FEATURE_SNAPSHOT_SCHEMA,
        schema_version=str(FEATURE_SNAPSHOT_SCHEMA_VERSION),
    )
    return StoredFeatureSnapshot(snapshot=snapshot, artifact_id=ref.artifact_id)


def _feature_value(payload: dict[str, object]) -> FeatureValue:
    return FeatureValue(
        kind=FeatureValueKind(str(payload["kind"])),
        integer_value=(
            None if payload.get("integer_value") is None else int(payload["integer_value"])
        ),
        boolean_value=(
            None if payload.get("boolean_value") is None else bool(payload["boolean_value"])
        ),
        categorical_value=(
            None if payload.get("categorical_value") is None else str(payload["categorical_value"])
        ),
        unit=None if payload.get("unit") is None else str(payload["unit"]),
        missing_reason=(
            None if payload.get("missing_reason") is None else str(payload["missing_reason"])
        ),
    )


def _observation(payload: dict[str, object]) -> FeatureObservation:
    value = payload.get("value")
    artifacts = payload.get("source_artifact_ids")
    if not isinstance(value, dict) or not isinstance(artifacts, list):
        raise ValueError("stored feature observation is malformed")
    return FeatureObservation(
        feature_name=str(payload["feature_name"]),
        scope=FeatureScope(str(payload["scope"])),
        entity_id=str(payload["entity_id"]),
        value=_feature_value(dict(value)),
        observed_at=str(payload["observed_at"]),
        first_known_at=str(payload["first_known_at"]),
        source_artifact_ids=tuple(str(item) for item in artifacts),
        derivation_id=str(payload["derivation_id"]),
        schema_version=int(payload.get("schema_version", -1)),
    )


def load_feature_snapshot(artifact_id: str, *, store: ArtifactStore) -> StoredFeatureSnapshot:
    current = _artifact_id(artifact_id)
    raw = store.read_bytes(current)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("feature snapshot artifact is not UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_name") != FEATURE_SNAPSHOT_SCHEMA:
        raise ValueError("not an Apex feature snapshot artifact")
    if int(payload.get("schema_version", -1)) != FEATURE_SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported stored feature snapshot schema_version")
    semantic = payload.get("snapshot")
    rows = payload.get("observations")
    if not isinstance(semantic, dict) or not isinstance(rows, list):
        raise ValueError("feature snapshot envelope is incomplete")
    inputs = semantic.get("input_artifact_ids")
    if not isinstance(inputs, list):
        raise ValueError("feature snapshot input lineage is malformed")
    observations = tuple(_observation(dict(row)) for row in rows if isinstance(row, dict))
    if len(observations) != len(rows):
        raise ValueError("feature snapshot contains malformed observation rows")
    snapshot = FeatureSnapshot(
        season=str(semantic["season"]),
        cutoff=str(semantic["cutoff"]),
        global_world_id=GlobalWorldId(str(semantic["global_world_id"])),
        observations=observations,
        input_artifact_ids=tuple(str(item) for item in inputs),
        schema_version=int(semantic.get("schema_version", -1)),
    )
    declared = FeatureSnapshotId(str(payload.get("feature_snapshot_id") or ""))
    if declared != snapshot.snapshot_id:
        raise ValueError("feature snapshot semantic identity mismatch")
    if [row.observation_id for row in snapshot.observations] != list(
        semantic.get("observation_ids", [])
    ):
        raise ValueError("feature snapshot observation identity list mismatch")
    for artifact in snapshot.input_artifact_ids:
        if not store.verify(artifact):
            raise ValueError(f"feature snapshot lineage artifact is missing/corrupt: {artifact}")
    return StoredFeatureSnapshot(snapshot=snapshot, artifact_id=current)
