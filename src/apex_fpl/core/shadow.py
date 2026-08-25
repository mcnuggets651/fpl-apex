"""Dependency-free shadow-production contracts for Apex V2 Slice 12."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256
from .ids import BundleId, GlobalWorldId, ReleaseId


class ShadowProductionStatus(StrEnum):
    PASS = "PASS"
    WITHHELD = "WITHHELD"


@dataclass(frozen=True, slots=True)
class ShadowProductionReport:
    """Immutable evidence from one non-actionable V2 release-path rehearsal.

    A PASS means the retained AssuranceCase derived an eligible ReleaseCertificate under
    the exact retained ProofObligation set and the shadow release/pointer path completed.
    It never means production publication is allowed.
    """

    season: str
    entry: int
    gameweek: int
    bundle_id: BundleId | None
    world_id: GlobalWorldId | None
    release_id: ReleaseId
    assurance_case_id: str
    assurance_case_artifact_id: str
    proof_obligations_artifact_id: str
    release_certificate_status: str
    release_certificate_blockers: tuple[str, ...]
    production_pointer_before: str | None
    production_pointer_after: str | None
    shadow_pointer_before: str | None
    shadow_pointer_after: str
    artifact_manifest_id: str
    source_artifact_ids: tuple[str, ...]
    status: ShadowProductionStatus
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported ShadowProductionReport schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("shadow production report requires season")
        if isinstance(self.entry, bool) or not isinstance(self.entry, int) or self.entry <= 0:
            raise ValueError("shadow production entry must be positive integer")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ValueError("shadow production gameweek must be positive integer")
        if not isinstance(self.status, ShadowProductionStatus):
            raise ValueError("shadow production status must be typed")
        case_id = str(self.assurance_case_id).strip()
        case_artifact = str(self.assurance_case_artifact_id).strip()
        proof_artifact = str(self.proof_obligations_artifact_id).strip()
        if not case_id or not case_artifact or not proof_artifact:
            raise ValueError("shadow production report requires assurance/proof identities")
        if self.release_certificate_status not in {"PASS", "FAIL"}:
            raise ValueError("shadow release certificate status must be PASS or FAIL")
        blockers = tuple(
            str(item).strip()
            for item in self.release_certificate_blockers
            if str(item).strip()
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
        if not sources:
            raise ValueError("shadow production report requires immutable source artifacts")
        required_sources = {
            self.artifact_manifest_id,
            case_artifact,
            proof_artifact,
        }
        if not required_sources.issubset(set(sources)):
            raise ValueError(
                "shadow production lineage must include manifest, AssuranceCase and proof policy artifacts"
            )
        if self.production_pointer_before != self.production_pointer_after:
            raise ValueError("shadow production must not change production current pointer")
        if self.shadow_pointer_after != str(self.release_id):
            raise ValueError("shadow pointer must resolve to the shadow release")
        if self.status is ShadowProductionStatus.PASS:
            if self.release_certificate_status != "PASS" or blockers:
                raise ValueError(
                    "PASS shadow production requires blocker-free PASS ReleaseCertificate"
                )
        elif self.release_certificate_status == "PASS" and not blockers:
            raise ValueError("eligible blocker-free shadow rehearsal must be PASS")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "assurance_case_id", case_id)
        object.__setattr__(self, "assurance_case_artifact_id", case_artifact)
        object.__setattr__(self, "proof_obligations_artifact_id", proof_artifact)
        object.__setattr__(self, "release_certificate_blockers", blockers)
        object.__setattr__(self, "source_artifact_ids", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-shadow-production-report",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry": self.entry,
            "gameweek": self.gameweek,
            "bundle_id": None if self.bundle_id is None else str(self.bundle_id),
            "world_id": None if self.world_id is None else str(self.world_id),
            "release_id": str(self.release_id),
            "assurance_case_id": self.assurance_case_id,
            "assurance_case_artifact_id": self.assurance_case_artifact_id,
            "proof_obligations_artifact_id": self.proof_obligations_artifact_id,
            "release_certificate_status": self.release_certificate_status,
            "release_certificate_blockers": list(self.release_certificate_blockers),
            "production_pointer_before": self.production_pointer_before,
            "production_pointer_after": self.production_pointer_after,
            "shadow_pointer_before": self.shadow_pointer_before,
            "shadow_pointer_after": self.shadow_pointer_after,
            "artifact_manifest_id": self.artifact_manifest_id,
            "source_artifact_ids": list(self.source_artifact_ids),
            "status": self.status.value,
        }

    @property
    def report_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
