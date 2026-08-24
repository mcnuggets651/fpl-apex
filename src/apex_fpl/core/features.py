"""Point-in-time feature contracts for Apex V2.

A FeatureSnapshot is a sealed semantic view of facts and derived observations that were
actually knowable by a decision cutoff. Feature values use explicit integer/categorical
representations and explicit missingness; feature construction never invents neutral
numeric defaults.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .canonical import canonical_sha256
from .ids import FeatureSnapshotId, GlobalWorldId


class FeatureScope(str, Enum):
    PLAYER = "PLAYER"
    TEAM = "TEAM"
    MATCH = "MATCH"
    GLOBAL = "GLOBAL"


class FeatureValueKind(str, Enum):
    INTEGER = "INTEGER"
    BOOLEAN = "BOOLEAN"
    CATEGORICAL = "CATEGORICAL"
    MISSING = "MISSING"


def _aware_iso(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
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
        raise ValueError(f"invalid feature artifact ID: {value!r}")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"invalid feature artifact digest: {value!r}") from exc
    return text


@dataclass(frozen=True, slots=True)
class FeatureValue:
    kind: FeatureValueKind
    integer_value: int | None = None
    boolean_value: bool | None = None
    categorical_value: str | None = None
    unit: str | None = None
    missing_reason: str | None = None

    def __post_init__(self) -> None:
        if self.kind is FeatureValueKind.INTEGER:
            if isinstance(self.integer_value, bool) or not isinstance(self.integer_value, int):
                raise ValueError("INTEGER feature requires integer_value")
            if self.boolean_value is not None or self.categorical_value is not None:
                raise ValueError("INTEGER feature cannot carry other value types")
            unit = str(self.unit or "").strip()
            if not unit:
                raise ValueError("INTEGER feature requires an explicit unit/scale")
            if self.missing_reason is not None:
                raise ValueError("present INTEGER feature cannot have missing_reason")
            object.__setattr__(self, "unit", unit)
        elif self.kind is FeatureValueKind.BOOLEAN:
            if not isinstance(self.boolean_value, bool):
                raise ValueError("BOOLEAN feature requires boolean_value")
            if self.integer_value is not None or self.categorical_value is not None:
                raise ValueError("BOOLEAN feature cannot carry other value types")
            if self.unit is not None or self.missing_reason is not None:
                raise ValueError("BOOLEAN feature cannot carry unit/missing_reason")
        elif self.kind is FeatureValueKind.CATEGORICAL:
            value = str(self.categorical_value or "").strip()
            if not value:
                raise ValueError("CATEGORICAL feature requires categorical_value")
            if self.integer_value is not None or self.boolean_value is not None:
                raise ValueError("CATEGORICAL feature cannot carry other value types")
            if self.unit is not None or self.missing_reason is not None:
                raise ValueError("CATEGORICAL feature cannot carry unit/missing_reason")
            object.__setattr__(self, "categorical_value", value)
        elif self.kind is FeatureValueKind.MISSING:
            reason = str(self.missing_reason or "").strip()
            if not reason:
                raise ValueError("MISSING feature requires missing_reason")
            if any(
                value is not None
                for value in (self.integer_value, self.boolean_value, self.categorical_value, self.unit)
            ):
                raise ValueError("MISSING feature cannot carry a fabricated value")
            object.__setattr__(self, "missing_reason", reason)
        else:
            raise ValueError(f"unsupported FeatureValueKind: {self.kind!r}")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "kind": self.kind.value,
            "integer_value": self.integer_value,
            "boolean_value": self.boolean_value,
            "categorical_value": self.categorical_value,
            "unit": self.unit,
            "missing_reason": self.missing_reason,
        }


@dataclass(frozen=True, slots=True)
class FeatureObservation:
    feature_name: str
    scope: FeatureScope
    entity_id: str
    value: FeatureValue
    observed_at: str
    first_known_at: str
    source_artifact_ids: tuple[str, ...]
    derivation_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported FeatureObservation schema_version")
        feature_name = str(self.feature_name).strip()
        entity_id = str(self.entity_id).strip()
        derivation_id = str(self.derivation_id).strip()
        if not feature_name or not entity_id or not derivation_id:
            raise ValueError("feature name, entity ID and derivation ID cannot be empty")
        observed = _aware_iso(self.observed_at, label="observed_at")
        first_known = _aware_iso(self.first_known_at, label="first_known_at")
        if _point(observed) > _point(first_known):
            raise ValueError("feature observed_at cannot be after first_known_at")
        artifacts = tuple(sorted({_artifact_id(item) for item in self.source_artifact_ids}))
        if not artifacts:
            raise ValueError("feature observation requires immutable source artifacts")
        object.__setattr__(self, "feature_name", feature_name)
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "derivation_id", derivation_id)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "first_known_at", first_known)
        object.__setattr__(self, "source_artifact_ids", artifacts)

    @property
    def feature_key(self) -> tuple[str, str, str]:
        return (self.scope.value, self.entity_id, self.feature_name)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-feature-observation",
            "schema_version": self.schema_version,
            "feature_name": self.feature_name,
            "scope": self.scope.value,
            "entity_id": self.entity_id,
            "value": self.value.semantic_payload(),
            "observed_at": self.observed_at,
            "first_known_at": self.first_known_at,
            "source_artifact_ids": list(self.source_artifact_ids),
            "derivation_id": self.derivation_id,
        }

    @property
    def observation_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    season: str
    cutoff: str
    global_world_id: GlobalWorldId
    observations: tuple[FeatureObservation, ...]
    input_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported FeatureSnapshot schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("feature snapshot season cannot be empty")
        cutoff = _aware_iso(self.cutoff, label="feature cutoff")
        artifacts = tuple(sorted({_artifact_id(item) for item in self.input_artifact_ids}))
        if not artifacts:
            raise ValueError("feature snapshot requires immutable input artifacts")
        observations = tuple(sorted(self.observations, key=lambda item: item.feature_key))
        keys = [item.feature_key for item in observations]
        if len(keys) != len(set(keys)):
            raise ValueError("feature snapshot contains duplicate canonical feature keys")
        artifact_set = set(artifacts)
        for observation in observations:
            if _point(observation.first_known_at) > _point(cutoff):
                raise ValueError(
                    f"feature {observation.feature_key} was first known after snapshot cutoff"
                )
            if not set(observation.source_artifact_ids).issubset(artifact_set):
                raise ValueError("feature observation lineage is absent from snapshot inputs")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "cutoff", cutoff)
        object.__setattr__(self, "observations", observations)
        object.__setattr__(self, "input_artifact_ids", artifacts)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-feature-snapshot",
            "schema_version": self.schema_version,
            "season": self.season,
            "cutoff": self.cutoff,
            "global_world_id": str(self.global_world_id),
            "observation_ids": [item.observation_id for item in self.observations],
            "input_artifact_ids": list(self.input_artifact_ids),
        }

    @property
    def snapshot_id(self) -> FeatureSnapshotId:
        return FeatureSnapshotId(canonical_sha256(self.semantic_payload()))

    def get(self, *, scope: FeatureScope, entity_id: str, feature_name: str) -> FeatureObservation | None:
        key = (scope.value, str(entity_id), str(feature_name))
        return next((item for item in self.observations if item.feature_key == key), None)
