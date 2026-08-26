"""Dependency-free operational probe evidence for production control-plane backends."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256


def _required(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _strict_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ArtifactStoreProbeEvidence:
    """Observed shared-persistence behavior for one exact ArtifactStore backend."""

    backend_id: str
    qualification_scope: str
    probe_artifact_id: str
    probe_content_sha256: str
    reopened_backend_id: str
    reopened_read_sha256: str
    stable_backend_identity: bool
    shared_visibility: bool
    integrity_verified: bool
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("unsupported ArtifactStoreProbeEvidence schema")
        for field, label in (
            ("backend_id", "artifact backend_id"),
            ("qualification_scope", "artifact qualification_scope"),
            ("probe_artifact_id", "artifact probe_artifact_id"),
            ("probe_content_sha256", "artifact probe_content_sha256"),
            ("reopened_backend_id", "artifact reopened_backend_id"),
            ("reopened_read_sha256", "artifact reopened_read_sha256"),
        ):
            object.__setattr__(self, field, _required(getattr(self, field), label=label))
        for field, label in (
            ("stable_backend_identity", "artifact stable_backend_identity"),
            ("shared_visibility", "artifact shared_visibility"),
            ("integrity_verified", "artifact integrity_verified"),
        ):
            object.__setattr__(self, field, _strict_bool(getattr(self, field), label=label))
        for digest in (self.probe_content_sha256, self.reopened_read_sha256):
            if len(digest) != 64:
                raise ValueError("artifact probe SHA-256 must contain 64 hex characters")
            try:
                int(digest, 16)
            except ValueError as exc:
                raise ValueError("artifact probe SHA-256 is invalid") from exc

    @property
    def supported(self) -> bool:
        return (
            self.stable_backend_identity
            and self.shared_visibility
            and self.integrity_verified
            and self.backend_id == self.reopened_backend_id
            and self.probe_content_sha256 == self.reopened_read_sha256
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-artifact-store-operational-probe",
            "schema_version": self.schema_version,
            "backend_id": self.backend_id,
            "qualification_scope": self.qualification_scope,
            "probe_artifact_id": self.probe_artifact_id,
            "probe_content_sha256": self.probe_content_sha256,
            "reopened_backend_id": self.reopened_backend_id,
            "reopened_read_sha256": self.reopened_read_sha256,
            "stable_backend_identity": self.stable_backend_identity,
            "shared_visibility": self.shared_visibility,
            "integrity_verified": self.integrity_verified,
        }

    @property
    def evidence_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ReleaseRegistryProbeEvidence:
    """Observed immutable-history and CAS behavior for one exact registry backend."""

    backend_id: str
    qualification_scope: str
    probe_season: str
    probe_entry: int
    probe_gameweek: int
    first_release_id: str
    second_release_id: str
    reopened_backend_id: str
    stable_backend_identity: bool
    shared_visibility: bool
    immutable_replay: bool
    forged_identity_rejected: bool
    stale_writer_conflict_observed: bool
    successful_cas_transition: bool
    final_release_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("unsupported ReleaseRegistryProbeEvidence schema")
        for field, label in (
            ("backend_id", "registry backend_id"),
            ("qualification_scope", "registry qualification_scope"),
            ("probe_season", "registry probe_season"),
            ("first_release_id", "registry first_release_id"),
            ("second_release_id", "registry second_release_id"),
            ("reopened_backend_id", "registry reopened_backend_id"),
            ("final_release_id", "registry final_release_id"),
        ):
            object.__setattr__(self, field, _required(getattr(self, field), label=label))
        object.__setattr__(
            self,
            "probe_entry",
            _positive_int(self.probe_entry, label="registry probe_entry"),
        )
        object.__setattr__(
            self,
            "probe_gameweek",
            _positive_int(self.probe_gameweek, label="registry probe_gameweek"),
        )
        for field, label in (
            ("stable_backend_identity", "registry stable_backend_identity"),
            ("shared_visibility", "registry shared_visibility"),
            ("immutable_replay", "registry immutable_replay"),
            ("forged_identity_rejected", "registry forged_identity_rejected"),
            ("stale_writer_conflict_observed", "registry stale_writer_conflict_observed"),
            ("successful_cas_transition", "registry successful_cas_transition"),
        ):
            object.__setattr__(self, field, _strict_bool(getattr(self, field), label=label))

    @property
    def supported(self) -> bool:
        return (
            self.stable_backend_identity
            and self.shared_visibility
            and self.immutable_replay
            and self.forged_identity_rejected
            and self.stale_writer_conflict_observed
            and self.successful_cas_transition
            and self.backend_id == self.reopened_backend_id
            and self.final_release_id == self.second_release_id
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-release-registry-operational-probe",
            "schema_version": self.schema_version,
            "backend_id": self.backend_id,
            "qualification_scope": self.qualification_scope,
            "probe_season": self.probe_season,
            "probe_entry": self.probe_entry,
            "probe_gameweek": self.probe_gameweek,
            "first_release_id": self.first_release_id,
            "second_release_id": self.second_release_id,
            "reopened_backend_id": self.reopened_backend_id,
            "stable_backend_identity": self.stable_backend_identity,
            "shared_visibility": self.shared_visibility,
            "immutable_replay": self.immutable_replay,
            "forged_identity_rejected": self.forged_identity_rejected,
            "stale_writer_conflict_observed": self.stale_writer_conflict_observed,
            "successful_cas_transition": self.successful_cas_transition,
            "final_release_id": self.final_release_id,
        }

    @property
    def evidence_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
