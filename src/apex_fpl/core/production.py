"""Dependency-free production-cutover contracts for Apex V2 Slice 13."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256
from .ids import BundleId, GlobalWorldId, ReleaseId


class ProductionCutoverStatus(StrEnum):
    """Outcome of one explicit production publication attempt."""

    PUBLISHED = "PUBLISHED"
    WITHHELD = "WITHHELD"


@dataclass(frozen=True, slots=True)
class ProductionBackendQualification:
    """Operational qualification for the production control plane.

    There is deliberately no default or filesystem shortcut. Production requires retained
    evidence that immutable artifact storage and the current-pointer registry are durable,
    shared and provide the atomicity/history semantics required by the frozen architecture.
    """

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
        for label, value in (
            ("artifact store qualification", self.artifact_store_qualification_artifact_id),
            ("release registry qualification", self.release_registry_qualification_artifact_id),
            ("qualification scope", self.qualification_scope),
        ):
            if not str(value).strip():
                raise ValueError(f"production {label} is required")

    @property
    def qualified(self) -> bool:
        return all(
            (
                self.durable_shared_artifact_store,
                self.durable_shared_release_registry,
                self.atomic_compare_and_swap,
                self.immutable_release_history,
            )
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-backend-qualification",
            "schema_version": self.schema_version,
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
class ProductionCutoverReport:
    """Content-addressed evidence for one explicit production cutover attempt.

    A PASS ReleaseCertificate is the certification transition. It is necessary but not
    sufficient for publication: the production control plane must also be qualified and
    atomic compare-and-swap must make the exact derived PUBLISHED ReleaseRecord current.
    WITHHELD attempts retain their immutable ReleaseRecord evidence but cannot move the
    production pointer or become actionable.
    """

    season: str
    entry: int
    gameweek: int
    bundle_id: BundleId | None
    world_id: GlobalWorldId | None
    attempt_release_id: ReleaseId
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
        case_id = str(self.assurance_case_id).strip()
        case_artifact = str(self.assurance_case_artifact_id).strip()
        proof_artifact = str(self.proof_obligations_artifact_id).strip()
        backend_id = str(self.backend_qualification_id).strip()
        backend_snapshot = str(self.backend_qualification_snapshot_artifact_id).strip()
        record_artifact = str(self.release_record_artifact_id).strip()
        manifest_id = str(self.artifact_manifest_id).strip()
        if not all(
            (
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
            raise ValueError("production cutover report requires complete proof/backend/release identities")
        if self.release_certificate_status not in {"PASS", "FAIL"}:
            raise ValueError("production ReleaseCertificate status must be PASS or FAIL")

        certificate_blockers = tuple(
            str(item).strip()
            for item in self.release_certificate_blockers
            if str(item).strip()
        )
        cutover_blockers = tuple(
            str(item).strip()
            for item in self.cutover_blockers
            if str(item).strip()
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
            case_artifact,
            proof_artifact,
            backend_snapshot,
            record_artifact,
            *backend_artifacts,
        }
        if not required_sources.issubset(set(sources)):
            raise ValueError(
                "production cutover lineage must include manifest, AssuranceCase, proof policy, backend and ReleaseRecord evidence"
            )

        if self.status is ProductionCutoverStatus.PUBLISHED:
            if self.release_certificate_status != "PASS" or certificate_blockers:
                raise ValueError("PUBLISHED production cutover requires blocker-free PASS ReleaseCertificate")
            if cutover_blockers:
                raise ValueError("PUBLISHED production cutover cannot retain cutover blockers")
            if self.bundle_id is None or self.world_id is None:
                raise ValueError("PUBLISHED production cutover requires bundle/world identities")
            if self.production_pointer_after != str(self.attempt_release_id):
                raise ValueError("published production pointer must resolve to the exact release")
        elif self.production_pointer_before != self.production_pointer_after:
            raise ValueError("WITHHELD production cutover must not change current pointer")

        object.__setattr__(self, "season", season)
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
        """Derived authority only; there is no independent readiness input."""

        return self.publication_eligible

    @property
    def safe_to_act(self) -> bool:
        """System publication safety derives from successful certified cutover only."""

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
