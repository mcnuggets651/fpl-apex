"""Immutable feature-batch boundary for historical, preseason and derived facts.

A batch binds the observation rows, their source artifacts and the control-plane time at
which the batch became available.  A FeatureSnapshot may consume the batch only at a
cutoff at or after that knowledge time; editing a database later creates a new batch
artifact rather than mutating historical features.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.features import (
    FeatureObservation,
    FeatureScope,
    FeatureValue,
    FeatureValueKind,
)


FEATURE_BATCH_SCHEMA = "apex-point-in-time-feature-batch"
FEATURE_BATCH_SCHEMA_VERSION = 1


def _aware_iso(value: str, *, label: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _point(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("feature batch artifact ID must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("feature batch artifact digest is invalid") from exc
    return text


@dataclass(frozen=True, slots=True)
class FeatureBatch:
    batch_kind: str
    available_at: str
    observations: tuple[FeatureObservation, ...]
    source_artifact_ids: tuple[str, ...]
    producer_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported FeatureBatch schema_version")
        batch_kind = str(self.batch_kind).strip()
        producer_id = str(self.producer_id).strip()
        if not batch_kind or not producer_id:
            raise ValueError("feature batch kind and producer cannot be empty")
        available = _aware_iso(self.available_at, label="feature batch available_at")
        source_artifacts = tuple(sorted({_artifact_id(item) for item in self.source_artifact_ids}))
        if not source_artifacts:
            raise ValueError("feature batch requires immutable source artifacts")
        observations = tuple(sorted(self.observations, key=lambda row: row.feature_key))
        keys = [row.feature_key for row in observations]
        if len(keys) != len(set(keys)):
            raise ValueError("feature batch contains duplicate feature keys")
        source_set = set(source_artifacts)
        for observation in observations:
            if _point(observation.first_known_at) > _point(available):
                raise ValueError("feature observation cannot be first-known after its batch availability")
            if not set(observation.source_artifact_ids).issubset(source_set):
                raise ValueError("feature observation lineage is outside feature batch sources")
        object.__setattr__(self, "batch_kind", batch_kind)
        object.__setattr__(self, "producer_id", producer_id)
        object.__setattr__(self, "available_at", available)
        object.__setattr__(self, "source_artifact_ids", source_artifacts)
        object.__setattr__(self, "observations", observations)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": FEATURE_BATCH_SCHEMA,
            "schema_version": self.schema_version,
            "batch_kind": self.batch_kind,
            "available_at": self.available_at,
            "observation_ids": [row.observation_id for row in self.observations],
            "source_artifact_ids": list(self.source_artifact_ids),
            "producer_id": self.producer_id,
        }

    @property
    def batch_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class StoredFeatureBatch:
    batch: FeatureBatch
    artifact_id: str


def _value(payload: dict[str, object]) -> FeatureValue:
    return FeatureValue(
        kind=FeatureValueKind(str(payload["kind"])),
        integer_value=None if payload.get("integer_value") is None else int(payload["integer_value"]),
        boolean_value=None if payload.get("boolean_value") is None else bool(payload["boolean_value"]),
        categorical_value=None if payload.get("categorical_value") is None else str(payload["categorical_value"]),
        unit=None if payload.get("unit") is None else str(payload["unit"]),
        missing_reason=None if payload.get("missing_reason") is None else str(payload["missing_reason"]),
    )


def _observation(payload: dict[str, object]) -> FeatureObservation:
    value = payload.get("value")
    artifacts = payload.get("source_artifact_ids")
    if not isinstance(value, dict) or not isinstance(artifacts, list):
        raise ValueError("stored feature batch observation is malformed")
    return FeatureObservation(
        feature_name=str(payload["feature_name"]),
        scope=FeatureScope(str(payload["scope"])),
        entity_id=str(payload["entity_id"]),
        value=_value(dict(value)),
        observed_at=str(payload["observed_at"]),
        first_known_at=str(payload["first_known_at"]),
        source_artifact_ids=tuple(str(item) for item in artifacts),
        derivation_id=str(payload["derivation_id"]),
        schema_version=int(payload.get("schema_version", -1)),
    )


def store_feature_batch(batch: FeatureBatch, *, store: ArtifactStore) -> StoredFeatureBatch:
    for artifact in batch.source_artifact_ids:
        if not store.verify(artifact):
            raise ValueError(f"feature batch source artifact is missing/corrupt: {artifact}")
    envelope = {
        "schema_name": FEATURE_BATCH_SCHEMA,
        "schema_version": FEATURE_BATCH_SCHEMA_VERSION,
        "batch_id": batch.batch_id,
        "batch": batch.semantic_payload(),
        "observations": [row.semantic_payload() for row in batch.observations],
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=FEATURE_BATCH_SCHEMA,
        schema_version=str(FEATURE_BATCH_SCHEMA_VERSION),
    )
    return StoredFeatureBatch(batch, ref.artifact_id)


def load_feature_batch(
    artifact_id: str,
    *,
    cutoff: str,
    store: ArtifactStore,
) -> StoredFeatureBatch:
    current = _artifact_id(artifact_id)
    raw = store.read_bytes(current)
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("feature batch artifact is not UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_name") != FEATURE_BATCH_SCHEMA:
        raise ValueError("not an Apex feature batch artifact")
    semantic = payload.get("batch")
    rows = payload.get("observations")
    if not isinstance(semantic, dict) or not isinstance(rows, list):
        raise ValueError("feature batch envelope is incomplete")
    sources = semantic.get("source_artifact_ids")
    if not isinstance(sources, list):
        raise ValueError("feature batch source lineage is malformed")
    observations = tuple(_observation(dict(row)) for row in rows if isinstance(row, dict))
    if len(observations) != len(rows):
        raise ValueError("feature batch contains malformed observation rows")
    batch = FeatureBatch(
        batch_kind=str(semantic["batch_kind"]),
        available_at=str(semantic["available_at"]),
        observations=observations,
        source_artifact_ids=tuple(str(item) for item in sources),
        producer_id=str(semantic["producer_id"]),
        schema_version=int(semantic.get("schema_version", -1)),
    )
    if str(payload.get("batch_id") or "") != batch.batch_id:
        raise ValueError("feature batch semantic identity mismatch")
    if list(semantic.get("observation_ids", [])) != [row.observation_id for row in batch.observations]:
        raise ValueError("feature batch observation identity list mismatch")
    cutoff_iso = _aware_iso(cutoff, label="feature cutoff")
    if _point(batch.available_at) > _point(cutoff_iso):
        raise ValueError("feature batch was not available at requested cutoff")
    for artifact in batch.source_artifact_ids:
        if not store.verify(artifact):
            raise ValueError(f"feature batch source artifact is missing/corrupt: {artifact}")
    return StoredFeatureBatch(batch, current)
