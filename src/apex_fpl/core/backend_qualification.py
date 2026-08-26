"""Dependency-free qualification evidence for production control-plane backends."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256


REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS = frozenset(
    {
        "RETENTION",
        "ACCESS_CONTROL",
        "CREDENTIAL_SEPARATION",
        "BACKUP",
        "RESTORE",
        "DISASTER_RECOVERY",
        "AVAILABILITY",
        "GEOGRAPHIC_DURABILITY",
    }
)


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


@dataclass(frozen=True, slots=True)
class BackendDeploymentEvidenceItem:
    """One retained operational/deployment proof item for a concrete backend deployment."""

    evidence_kind: str
    evidence_artifact_id: str
    issuer: str
    observed_at: str
    outcome: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("unsupported BackendDeploymentEvidenceItem schema")
        kind = _required(self.evidence_kind, label="deployment evidence_kind").upper()
        if kind not in REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS:
            raise ValueError(f"unsupported deployment evidence kind: {kind}")
        artifact_id = _required(
            self.evidence_artifact_id,
            label="deployment evidence artifact_id",
        )
        issuer = _required(self.issuer, label="deployment evidence issuer")
        observed_at = _required(self.observed_at, label="deployment evidence observed_at")
        outcome = _required(self.outcome, label="deployment evidence outcome").upper()
        if outcome not in {"PASS", "FAIL"}:
            raise ValueError("deployment evidence outcome must be PASS or FAIL")
        object.__setattr__(self, "evidence_kind", kind)
        object.__setattr__(self, "evidence_artifact_id", artifact_id)
        object.__setattr__(self, "issuer", issuer)
        object.__setattr__(self, "observed_at", observed_at)
        object.__setattr__(self, "outcome", outcome)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-backend-deployment-evidence-item",
            "schema_version": self.schema_version,
            "evidence_kind": self.evidence_kind,
            "evidence_artifact_id": self.evidence_artifact_id,
            "issuer": self.issuer,
            "observed_at": self.observed_at,
            "outcome": self.outcome,
        }


@dataclass(frozen=True, slots=True)
class BackendDeploymentQualificationEvidence:
    """Retained non-probe evidence that a concrete shared deployment is production durable.

    Fresh-connection probes deliberately cannot create this evidence. A production deployment
    must retain all required operational proof classes, each backed by an immutable artifact.
    GitHub Actions/database-service fixtures are mechanism tests and must never be registered as
    real deployment evidence.
    """

    artifact_store_backend_id: str
    release_registry_backend_id: str
    qualification_scope: str
    deployment_id: str
    environment_class: str
    evaluated_at: str
    evidence_items: tuple[BackendDeploymentEvidenceItem, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != 1:
            raise ValueError("unsupported BackendDeploymentQualificationEvidence schema")
        for field, label in (
            ("artifact_store_backend_id", "deployment artifact-store backend_id"),
            ("release_registry_backend_id", "deployment release-registry backend_id"),
            ("qualification_scope", "deployment qualification_scope"),
            ("deployment_id", "deployment_id"),
            ("evaluated_at", "deployment evaluated_at"),
        ):
            object.__setattr__(self, field, _required(getattr(self, field), label=label))
        environment = _required(
            self.environment_class,
            label="deployment environment_class",
        ).upper()
        if environment not in {"PRODUCTION", "TEST"}:
            raise ValueError("deployment environment_class must be PRODUCTION or TEST")
        object.__setattr__(self, "environment_class", environment)
        items = tuple(self.evidence_items)
        kinds = [item.evidence_kind for item in items]
        if len(kinds) != len(set(kinds)):
            raise ValueError("deployment evidence contains duplicate evidence_kind")
        object.__setattr__(self, "evidence_items", tuple(sorted(items, key=lambda item: item.evidence_kind)))

    @property
    def complete(self) -> bool:
        return {
            item.evidence_kind for item in self.evidence_items
        } == REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS

    @property
    def supported(self) -> bool:
        return (
            self.environment_class == "PRODUCTION"
            and self.complete
            and all(item.outcome == "PASS" for item in self.evidence_items)
        )

    @property
    def evidence_artifact_ids(self) -> tuple[str, ...]:
        return tuple(item.evidence_artifact_id for item in self.evidence_items)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-backend-deployment-qualification-evidence",
            "schema_version": self.schema_version,
            "artifact_store_backend_id": self.artifact_store_backend_id,
            "release_registry_backend_id": self.release_registry_backend_id,
            "qualification_scope": self.qualification_scope,
            "deployment_id": self.deployment_id,
            "environment_class": self.environment_class,
            "evaluated_at": self.evaluated_at,
            "evidence_items": [item.semantic_payload() for item in self.evidence_items],
            "complete": self.complete,
            "supported": self.supported,
        }

    @property
    def evidence_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
