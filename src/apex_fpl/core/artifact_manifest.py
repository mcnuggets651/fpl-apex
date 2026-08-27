"""Typed release-level artifact closure for Apex V2 production publication.

A content-addressed object is not, by itself, proof that a complete production release
closure exists. ``ArtifactManifest`` binds the exact decision/runtime scope to a
role-unique set of retained content-addressed artifacts. The manifest is itself stored
as its canonical semantic payload, so ``manifest_id`` is also its ArtifactStore identity.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256


def _text(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _sha256_id(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


class ArtifactManifestRole(StrEnum):
    """Decision-critical artifact roles that must be unique inside one release closure."""

    PLANNING_BUNDLE = "PLANNING_BUNDLE"
    WORLD = "WORLD"
    ASSURANCE_CASE = "ASSURANCE_CASE"
    PROOF_OBLIGATIONS = "PROOF_OBLIGATIONS"
    BACKEND_QUALIFICATION = "BACKEND_QUALIFICATION"
    AUTHORITY_ROOT_REGISTRY_QUALIFICATION = "AUTHORITY_ROOT_REGISTRY_QUALIFICATION"
    CHAMPION_GENERATION = "CHAMPION_GENERATION"
    AUTHORITY_ROOT = "AUTHORITY_ROOT"
    BUILD_MANIFEST = "BUILD_MANIFEST"
    RULESET = "RULESET"
    LEARNING_POLICY_REGISTRY = "LEARNING_POLICY_REGISTRY"
    OUTCOME_TRUTH_REGISTRY = "OUTCOME_TRUTH_REGISTRY"
    REFERENCE_SOLVER_AUTHORIZATION = "REFERENCE_SOLVER_AUTHORIZATION"


REQUIRED_PRODUCTION_MANIFEST_ROLES = frozenset(ArtifactManifestRole)


@dataclass(frozen=True, slots=True)
class ArtifactManifestEntry:
    role: ArtifactManifestRole
    artifact_id: str
    semantic_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ArtifactManifestEntry schema_version")
        if not isinstance(self.role, ArtifactManifestRole):
            raise ValueError("artifact manifest entry role must be typed")
        object.__setattr__(
            self,
            "artifact_id",
            _sha256_id(self.artifact_id, label=f"{self.role.value} artifact"),
        )
        if self.semantic_id is not None:
            object.__setattr__(
                self,
                "semantic_id",
                _sha256_id(self.semantic_id, label=f"{self.role.value} semantic identity"),
            )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "role": self.role.value,
            "artifact_id": self.artifact_id,
            "semantic_id": self.semantic_id,
        }


@dataclass(frozen=True, slots=True)
class ArtifactManifest:
    """Self-addressing complete artifact closure for one production decision scope."""

    season: str
    entry: int
    gameweek: int
    bundle_id: str
    world_id: str
    runtime_digest: str
    authority_root_artifact_id: str
    entries: tuple[ArtifactManifestEntry, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ArtifactManifest schema_version")
        object.__setattr__(self, "season", _text(self.season, label="manifest season"))
        if isinstance(self.entry, bool) or not isinstance(self.entry, int) or self.entry <= 0:
            raise ValueError("artifact manifest entry must be positive integer")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ValueError("artifact manifest gameweek must be positive integer")
        object.__setattr__(self, "bundle_id", _sha256_id(self.bundle_id, label="manifest bundle"))
        object.__setattr__(self, "world_id", _sha256_id(self.world_id, label="manifest world"))
        object.__setattr__(
            self,
            "runtime_digest",
            _sha256_id(self.runtime_digest, label="manifest runtime digest"),
        )
        object.__setattr__(
            self,
            "authority_root_artifact_id",
            _sha256_id(self.authority_root_artifact_id, label="manifest authority root"),
        )
        entries = tuple(self.entries)
        if not entries:
            raise ValueError("artifact manifest entries cannot be empty")
        roles = tuple(item.role for item in entries)
        if len(set(roles)) != len(roles):
            raise ValueError("artifact manifest roles must be unique")
        missing = REQUIRED_PRODUCTION_MANIFEST_ROLES.difference(roles)
        if missing:
            missing_names = ",".join(sorted(role.value for role in missing))
            raise ValueError(f"artifact manifest missing required roles: {missing_names}")
        canonical_entries = tuple(sorted(entries, key=lambda item: item.role.value))
        if canonical_entries != entries:
            raise ValueError("artifact manifest entries must be sorted by role")
        by_role = {item.role: item for item in entries}
        if by_role[ArtifactManifestRole.PLANNING_BUNDLE].artifact_id != self.bundle_id:
            raise ValueError("artifact manifest planning bundle does not match bundle_id")
        if by_role[ArtifactManifestRole.WORLD].artifact_id != self.world_id:
            raise ValueError("artifact manifest world member does not match world_id")
        if by_role[ArtifactManifestRole.AUTHORITY_ROOT].artifact_id != self.authority_root_artifact_id:
            raise ValueError("artifact manifest authority-root member does not match scope")
        object.__setattr__(self, "entries", entries)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-artifact-manifest",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry": self.entry,
            "gameweek": self.gameweek,
            "bundle_id": self.bundle_id,
            "world_id": self.world_id,
            "runtime_digest": self.runtime_digest,
            "authority_root_artifact_id": self.authority_root_artifact_id,
            "entries": [item.semantic_payload() for item in self.entries],
        }

    @property
    def manifest_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    def require_role(self, role: ArtifactManifestRole) -> ArtifactManifestEntry:
        for item in self.entries:
            if item.role is role:
                return item
        raise ValueError(f"artifact manifest lacks required role {role.value}")
