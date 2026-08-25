"""Dependency-free authority contract for user-facing V2 production answers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256
from .ids import BundleId, GlobalWorldId, ReleaseId


class ProductionAuthorityStatus(StrEnum):
    CURRENT = "CURRENT"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ProductionAnswerAuthority:
    """The only V2 release identity from which a user-facing answer may be sourced."""

    season: str
    entry: int
    gameweek: int
    status: ProductionAuthorityStatus
    release_id: ReleaseId | None
    bundle_id: BundleId | None
    world_id: GlobalWorldId | None
    runtime_digest: str | None
    artifact_manifest_id: str | None
    blockers: tuple[str, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProductionAnswerAuthority schema_version")
        if not str(self.season).strip():
            raise ValueError("production answer authority requires season")
        if isinstance(self.entry, bool) or not isinstance(self.entry, int) or self.entry <= 0:
            raise ValueError("production answer authority entry must be positive integer")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ValueError("production answer authority gameweek must be positive integer")
        if not isinstance(self.status, ProductionAuthorityStatus):
            raise ValueError("production answer authority status must be typed")
        blockers = tuple(str(item).strip() for item in self.blockers if str(item).strip())
        if self.status is ProductionAuthorityStatus.CURRENT:
            if blockers:
                raise ValueError("CURRENT production answer authority cannot contain blockers")
            if self.release_id is None or self.bundle_id is None or self.world_id is None:
                raise ValueError("CURRENT production answer authority requires release/bundle/world")
            if not str(self.runtime_digest or "").strip() or not str(
                self.artifact_manifest_id or ""
            ).strip():
                raise ValueError("CURRENT production answer authority requires runtime/manifest")
        else:
            if not blockers:
                raise ValueError("UNAVAILABLE production answer authority requires blocker reason")
            if any(
                value is not None
                for value in (
                    self.release_id,
                    self.bundle_id,
                    self.world_id,
                    self.runtime_digest,
                    self.artifact_manifest_id,
                )
            ):
                raise ValueError("UNAVAILABLE production authority cannot expose release payload")
        object.__setattr__(self, "season", str(self.season).strip())
        object.__setattr__(self, "blockers", blockers)

    @property
    def publication_eligible(self) -> bool:
        return self.status is ProductionAuthorityStatus.CURRENT

    @property
    def ready_to_act(self) -> bool:
        return self.publication_eligible

    @property
    def safe_to_act(self) -> bool:
        return self.publication_eligible

    @property
    def production_result_bundle_id(self) -> BundleId | None:
        """Only the current certified bundle may be decoded into a recommendation."""

        return self.bundle_id if self.publication_eligible else None

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-answer-authority",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry": self.entry,
            "gameweek": self.gameweek,
            "status": self.status.value,
            "release_id": None if self.release_id is None else str(self.release_id),
            "bundle_id": None if self.bundle_id is None else str(self.bundle_id),
            "world_id": None if self.world_id is None else str(self.world_id),
            "runtime_digest": self.runtime_digest,
            "artifact_manifest_id": self.artifact_manifest_id,
            "blockers": list(self.blockers),
            "publication_eligible": self.publication_eligible,
            "ready_to_act": self.ready_to_act,
            "safe_to_act": self.safe_to_act,
        }

    @property
    def authority_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
