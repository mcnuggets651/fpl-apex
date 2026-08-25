"""Dependency-free production-cutover contracts for Apex V2 Slice 13."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256
from .ids import BundleId, GlobalWorldId, ReleaseId


MANDATORY_PRODUCTION_PROOF_IDS = frozenset(
    {
        "PO-RUNTIME-IDENTITY-001",
        "PO-ARTIFACT-INTEGRITY-001",
        "PO-RELEASE-CAS-001",
        "PO-GLOBAL-WORLD-SEAL-001",
        "PO-OFFICIAL-PLAYER-IDENTITY-001",
        "PO-RULESET-PROVENANCE-001",
        "PO-MANAGER-PUBLIC-SEAL-001",
        "PO-INITIAL-MANAGER-BASIS-001",
        "PO-MANAGER-STATE-001",
        "PO-SOURCE-GOVERNANCE-001",
        "PO-EVIDENCE-LEDGER-001",
        "PO-FEATURE-TIME-TRAVEL-001",
        "PO-OUTCOME-TRUTH-001",
        "PO-MINUTES-FEATURE-INPUT-001",
        "PO-FORECAST-LINEAGE-001",
        "PO-FORECAST-SCORING-001",
        "PO-FORECAST-COVERAGE-001",
        "PO-FORECAST-QUALIFICATION-001",
        "PO-FOOTBALL-UNCERTAINTY-001",
        "PO-FPL-LEGALITY-001",
        "PO-DECISION-MECHANICS-001",
        "PO-DECISION-SOLVER-EXACTNESS-001",
        "PO-DECISION-POLICY-QUALIFICATION-001",
        "PO-CANDIDATE-UNIVERSE-001",
        "PO-DECISION-REPLAY-001",
        "PO-SCENARIO-CONVERGENCE-001",
        "PO-MECHANICS-RECONCILIATION-001",
        "PO-REFERENCE-SOLVER-PARITY-001",
        "PO-LEARNING-NO-HINDSIGHT-001",
        "PO-MODEL-EVALUATION-001",
        "PO-MODEL-PROMOTION-001",
        "PO-SHADOW-PRODUCTION-001",
        "PO-PRODUCTION-CUTOVER-001",
    }
)

REFERENCE_PRODUCTION_BACKEND_IDS = frozenset(
    {
        "apex.reference.filesystem-artifact-store.v1",
        "apex.reference.filesystem-release-registry.v1",
    }
)


class ProductionCutoverStatus(StrEnum):
    """Outcome of one explicit production publication attempt."""

    PUBLISHED = "PUBLISHED"
    WITHHELD = "WITHHELD"


@dataclass(frozen=True, slots=True)
class ProductionBackendQualification:
    """Operational qualification for the exact production control-plane adapters."""

    artifact_store_backend_id: str
    release_registry_backend_id: str
    artifact_store_qualification_artifact_id: str
    release_registry_qualification_artifact_id: str
    durable_shared_artifact_store: bool
    durable_shared_release_registry: bool
    atomic_compare_and_swap: bool
    immutable_release_history: bool
    qualification_scope: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProductionBackendQualification schema_version")
        artifact_backend = str(self.artifact_store_backend_id).strip()
        registry_backend = str(self.release_registry_backend_id).strip()
        artifact_qualification = str(self.artifact_store_qualification_artifact_id).strip()
        registry_qualification = str(self.release_registry_qualification_artifact_id).strip()
        scope = str(self.qualification_scope).strip()
        for label, value in (
            ("artifact store backend identity", artifact_backend),
            ("release registry backend identity", registry_backend),
            ("artifact store qualification", artifact_qualification),
            ("release registry qualification", registry_qualification),
            ("qualification scope", scope),
        ):
            if not value:
                raise ValueError(f"production {label} is required")
        object.__setattr__(self, "artifact_store_backend_id", artifact_backend)
        object.__setattr__(self, "release_registry_backend_id", registry_backend)
        object.__setattr__(
            self,
            "artifact_store_qualification_artifact_id",
            artifact_qualification,
        )
        object.__setattr__(
            self,
            "release_registry_qualification_artifact_id",
            registry_qualification,
        )
        object.__setattr__(self, "qualification_scope", scope)

    @property
    def qualified(self) -> bool:
        backend_ids = {
            self.artifact_store_backend_id,
            self.release_registry_backend_id,
        }
        return (
            backend_ids.isdisjoint(REFERENCE_PRODUCTION_BACKEND_IDS)
            and self.durable_shared_artifact_store
            and self.durable_shared_release_registry
            and self.atomic_compare_and_swap
            and self.immutable_release_history
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-backend-qualification",
            "schema_version": self.schema_version,
            "artifact_store_backend_id": self.artifact_store_backend_id,
            "release_registry_backend_id": self.release_registry_backend_id,
            "artifact_store_qualification_artifact_id": self.artifact_store_qualification_artifact_id,
            "release_registry_qualification_artifact_id": self.release_registry_qualification_artifact_id,
            "durable_shared_artifact_store": self.durable_shared_artifact_store,
            "durable_shared_release_registry": self.durable_shared_release_registry,
            "atomic_compare_and_swap": self.atomic_compare_and_swap,
            "immutable_release_history": self.immutable_release_history,
            "qualification_scope": self.qualification_scope,
        }

    @property
    def qualification_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ProductionPublicationAuthorization:
    """Immutable proof-derived authorization embedded in every V2 production release."""

    season: str
    entry: int
    gameweek: int
    bundle_id: BundleId | None
    world_id: GlobalWorldId | None
    runtime_digest: str
    created_at: str
    valid_until: str | None
    artifact_manifest_id: str
    assurance_case_id: str
    assurance_case_artifact_id: str
    proof_obligations_artifact_id: str
    release_certificate_status: str
    release_certificate_blockers: tuple[str, ...]
    cutover_blockers: tuple[str, ...]
    backend_qualification_id: str
    artifact_store_backend_id: str
    release_registry_backend_id: str
    backend_qualification_snapshot_artifact_id: str
    backend_qualification_artifact_ids: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProductionPublicationAuthorization schema_version")
        season = str(self.season).strip()
        runtime_digest = str(self.runtime_digest).strip()
        created_at = str(self.created_at).strip()
        valid_until = None if self.valid_until is None else str(self.valid_until).strip()
        manifest_id = str(self.artifact_manifest_id).strip()
        case_id = str(self.assurance_case_id).strip()
        case_artifact = str(self.assurance_case_artifact_id).strip()
        proof_artifact = str(self.proof_obligations_artifact_id).strip()
        backend_id = str(self.backend_qualification_id).strip()
        artifact_backend = str(self.artifact_store_backend_id).strip()
        registry_backend = str(self.release_registry_backend_id).strip()
        backend_snapshot = str(self.backend_qualification_snapshot_artifact_id).strip()
        if not season or not runtime_digest or not created_at or not manifest_id:
            raise ValueError("production authorization requires season/runtime/time/manifest")
        if self.valid_until is not None and not valid_until:
            raise ValueError("production authorization valid_until cannot be empty")
        if isinstance(self.entry, bool) or not isinstance(self.entry, int) or self.entry <= 0:
            raise ValueError("production authorization entry must be positive integer")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ValueError("production authorization gameweek must be positive integer")
        if not all(
            (
                case_id,
                case_artifact,
                proof_artifact,
                backend_id,
                artifact_backend,
                registry_backend,
                backend_snapshot,
            )
        ):
            raise ValueError("production authorization requires complete proof/backend identities")
        if self.release_certificate_status not in {"PASS", "FAIL"}:
            raise ValueError("production authorization certificate status must be PASS or FAIL")
        certificate_blockers = tuple(
            str(item).strip()
            for item in self.release_certificate_blockers
            if str(item).strip()
        )
        cutover_blockers = tuple(
            str(item).strip() for item in self.cutover_blockers if str(item).strip()
        )
        backend_artifacts = tuple(
            sorted(
                set(
                    str(item).strip()
                    for item in self.backend_qualification_artifact_ids
                    if str(item).strip()
                )
            )
        )
        if len(backend_artifacts) != 2:
            raise ValueError("production authorization requires both backend qualification artifacts")
        if self.release_certificate_status == "PASS" and certificate_blockers:
            raise ValueError("PASS production authorization cannot retain certificate blockers")
        if self.release_certificate_status == "FAIL" and not certificate_blockers:
            raise ValueError("FAIL production authorization requires certificate blockers")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "runtime_digest", runtime_digest)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "valid_until", valid_until)
        object.__setattr__(self, "artifact_manifest_id", manifest_id)
        object.__setattr__(self, "assurance_case_id", case_id)
        object.__setattr__(self, "assurance_case_artifact_id", case_artifact)
        object.__setattr__(self, "proof_obligations_artifact_id", proof_artifact)
        object.__setattr__(self, "backend_qualification_id", backend_id)
        object.__setattr__(self, "artifact_store_backend_id", artifact_backend)
        object.__setattr__(self, "release_registry_backend_id", registry_backend)
        object.__setattr__(self, "backend_qualification_snapshot_artifact_id", backend_snapshot)
        object.__setattr__(self, "release_certificate_blockers", certificate_blockers)
        object.__setattr__(self, "cutover_blockers", cutover_blockers)
        object.__setattr__(self, "backend_qualification_artifact_ids", backend_artifacts)

    @property
    def authorized(self) -> bool:
        return (
            self.release_certificate_status == "PASS"
            and not self.release_certificate_blockers
            and not self.cutover_blockers
            and self.bundle_id is not None
            and self.world_id is not None
            and self.valid_until is not None
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-publication-authorization",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry": self.entry,
            "gameweek": self.gameweek,
            "bundle_id": None if self.bundle_id is None else str(self.bundle_id),
            "world_id": None if self.world_id is None else str(self.world_id),
            "runtime_digest": self.runtime_digest,
            "created_at": self.created_at,
            "valid_until": self.valid_until,
            "artifact_manifest_id": self.artifact_manifest_id,
            "assurance_case_id": self.assurance_case_id,
            "assurance_case_artifact_id": self.assurance_case_artifact_id,
            "proof_obligations_artifact_id": self.proof_obligations_artifact_id,
            "release_certificate_status": self.release_certificate_status,
            "release_certificate_blockers": list(self.release_certificate_blockers),
            "cutover_blockers": list(self.cutover_blockers),
            "backend_qualification_id": self.backend_qualification_id,
            "artifact_store_backend_id": self.artifact_store_backend_id,
            "release_registry_backend_id": self.release_registry_backend_id,
            "backend_qualification_snapshot_artifact_id": self.backend_qualification_snapshot_artifact_id,
            "backend_qualification_artifact_ids": list(self.backend_qualification_artifact_ids),
            "authorized": self.authorized,
        }

    @property
    def authorization_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ProductionCutoverReport:
    """Content-addressed evidence for one explicit production cutover attempt."""

    season: str
    entry: int
    gameweek: int
    bundle_id: BundleId | None
    world_id: GlobalWorldId | None
    attempt_release_id: ReleaseId
    publication_authorization_artifact_id: str
    release_record_artifact_id: str
    assurance_case_id: str
    assurance_case_artifact_id: str
    proof_obligations_artifact_id: str
    release_certificate_status: str
    release_certificate_blockers: tuple[str, ...]
    cutover_blockers: tuple[str, ...]
    backend_qualification_id: str
    backend_qualification_snapshot_artifact_id: str
    backend_qualification_artifact_ids: tuple[str, ...]
    production_pointer_before: str | None
    production_pointer_after: str | None
    artifact_manifest_id: str
    source_artifact_ids: tuple[str, ...]
    status: ProductionCutoverStatus
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProductionCutoverReport schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("production cutover report requires season")
        if isinstance(self.entry, bool) or not isinstance(self.entry, int) or self.entry <= 0:
            raise ValueError("production cutover entry must be positive integer")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ValueError("production cutover gameweek must be positive integer")
        if not isinstance(self.status, ProductionCutoverStatus):
            raise ValueError("production cutover status must be typed")
        authorization_artifact = str(self.publication_authorization_artifact_id).strip()
        case_id = str(self.assurance_case_id).strip()
        case_artifact = str(self.assurance_case_artifact_id).strip()
        proof_artifact = str(self.proof_obligations_artifact_id).strip()
        backend_id = str(self.backend_qualification_id).strip()
        backend_snapshot = str(self.backend_qualification_snapshot_artifact_id).strip()
        record_artifact = str(self.release_record_artifact_id).strip()
        manifest_id = str(self.artifact_manifest_id).strip()
        if not all(
            (
                authorization_artifact,
                case_id,
                case_artifact,
                proof_artifact,
                backend_id,
                backend_snapshot,
                record_artifact,
                manifest_id,
                str(self.attempt_release_id).strip(),
            )
        ):
            raise ValueError(
                "production cutover report requires complete authorization/proof/backend/release identities"
            )
        if self.release_certificate_status not in {"PASS", "FAIL"}:
            raise ValueError("production ReleaseCertificate status must be PASS or FAIL")

        certificate_blockers = tuple(
            str(item).strip()
            for item in self.release_certificate_blockers
            if str(item).strip()
        )
        cutover_blockers = tuple(
            str(item).strip() for item in self.cutover_blockers if str(item).strip()
        )
        backend_artifacts = tuple(
            sorted(
                set(
                    str(item).strip()
                    for item in self.backend_qualification_artifact_ids
                    if str(item).strip()
                )
            )
        )
        sources = tuple(
            sorted(
                set(
                    str(item).strip()
                    for item in self.source_artifact_ids
                    if str(item).strip()
                )
            )
        )
        if len(backend_artifacts) != 2:
            raise ValueError("production cutover requires both backend qualification artifacts")
        required_sources = {
            manifest_id,
            authorization_artifact,
            case_artifact,
            proof_artifact,
            backend_snapshot,
            record_artifact,
            *backend_artifacts,
        }
        if not required_sources.issubset(set(sources)):
            raise ValueError(
                "production cutover lineage must include authorization, manifest, AssuranceCase, proof policy, backend and ReleaseRecord evidence"
            )

        if self.status is ProductionCutoverStatus.PUBLISHED:
            if self.release_certificate_status != "PASS" or certificate_blockers:
                raise ValueError(
                    "PUBLISHED production cutover requires blocker-free PASS ReleaseCertificate"
                )
            if cutover_blockers:
                raise ValueError("PUBLISHED production cutover cannot retain cutover blockers")
            if self.bundle_id is None or self.world_id is None:
                raise ValueError("PUBLISHED production cutover requires bundle/world identities")
            if self.production_pointer_after != str(self.attempt_release_id):
                raise ValueError("published production pointer must resolve to the exact release")
        else:
            if not certificate_blockers and not cutover_blockers:
                raise ValueError("WITHHELD production cutover requires an explicit blocker")
            if self.production_pointer_before != self.production_pointer_after:
                raise ValueError("WITHHELD production cutover must not change current pointer")

        object.__setattr__(self, "season", season)
        object.__setattr__(self, "publication_authorization_artifact_id", authorization_artifact)
        object.__setattr__(self, "assurance_case_id", case_id)
        object.__setattr__(self, "assurance_case_artifact_id", case_artifact)
        object.__setattr__(self, "proof_obligations_artifact_id", proof_artifact)
        object.__setattr__(self, "backend_qualification_id", backend_id)
        object.__setattr__(self, "backend_qualification_snapshot_artifact_id", backend_snapshot)
        object.__setattr__(self, "release_record_artifact_id", record_artifact)
        object.__setattr__(self, "artifact_manifest_id", manifest_id)
        object.__setattr__(self, "release_certificate_blockers", certificate_blockers)
        object.__setattr__(self, "cutover_blockers", cutover_blockers)
        object.__setattr__(self, "backend_qualification_artifact_ids", backend_artifacts)
        object.__setattr__(self, "source_artifact_ids", sources)

    @property
    def publication_eligible(self) -> bool:
        return self.status is ProductionCutoverStatus.PUBLISHED

    @property
    def ready_to_act(self) -> bool:
        return self.publication_eligible

    @property
    def safe_to_act(self) -> bool:
        return self.publication_eligible

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-cutover-report",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry": self.entry,
            "gameweek": self.gameweek,
            "bundle_id": None if self.bundle_id is None else str(self.bundle_id),
            "world_id": None if self.world_id is None else str(self.world_id),
            "attempt_release_id": str(self.attempt_release_id),
            "publication_authorization_artifact_id": self.publication_authorization_artifact_id,
            "release_record_artifact_id": self.release_record_artifact_id,
            "assurance_case_id": self.assurance_case_id,
            "assurance_case_artifact_id": self.assurance_case_artifact_id,
            "proof_obligations_artifact_id": self.proof_obligations_artifact_id,
            "release_certificate_status": self.release_certificate_status,
            "release_certificate_blockers": list(self.release_certificate_blockers),
            "cutover_blockers": list(self.cutover_blockers),
            "backend_qualification_id": self.backend_qualification_id,
            "backend_qualification_snapshot_artifact_id": self.backend_qualification_snapshot_artifact_id,
            "backend_qualification_artifact_ids": list(self.backend_qualification_artifact_ids),
            "production_pointer_before": self.production_pointer_before,
            "production_pointer_after": self.production_pointer_after,
            "artifact_manifest_id": self.artifact_manifest_id,
            "source_artifact_ids": list(self.source_artifact_ids),
            "status": self.status.value,
            "publication_eligible": self.publication_eligible,
            "ready_to_act": self.ready_to_act,
            "safe_to_act": self.safe_to_act,
        }

    @property
    def report_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
