"""Fail-closed resolution of the one current V2 production answer authority."""

from __future__ import annotations

from typing import Protocol

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.release_registry import ReleaseKey, ReleaseRecord, ReleaseStatus
from apex_fpl.core.ids import BundleId, GlobalWorldId, ReleaseId
from apex_fpl.core.production_authority import (
    ProductionAnswerAuthority,
    ProductionAuthorityStatus,
)


class ProductionCurrentReader(Protocol):
    def current_release_id(self, key: ReleaseKey) -> str | None: ...

    def read_release(self, release_id: str) -> ReleaseRecord: ...


def _unavailable(key: ReleaseKey, blocker: str) -> ProductionAnswerAuthority:
    return ProductionAnswerAuthority(
        season=key.season,
        entry=key.entry,
        gameweek=key.gameweek,
        status=ProductionAuthorityStatus.UNAVAILABLE,
        release_id=None,
        bundle_id=None,
        world_id=None,
        runtime_digest=None,
        artifact_manifest_id=None,
        blockers=(blocker,),
    )


def resolve_production_answer_authority(
    *,
    season: str,
    entry: int,
    gameweek: int,
    artifact_store: ArtifactStore,
    production_registry: ProductionCurrentReader,
) -> ProductionAnswerAuthority:
    """Resolve only the exact current PUBLISHED V2 release; everything else withholds."""

    key = ReleaseKey(season, entry, gameweek)
    release_id = production_registry.current_release_id(key)
    if release_id is None:
        return _unavailable(key, "no current V2 production release")
    try:
        record = production_registry.read_release(release_id)
    except (FileNotFoundError, ValueError) as exc:
        return _unavailable(key, f"current V2 release cannot be replayed: {exc}")
    if record.release_id != release_id:
        return _unavailable(key, "current pointer and immutable ReleaseRecord identity disagree")
    if (
        record.season != key.season
        or record.entry != key.entry
        or record.gameweek != key.gameweek
    ):
        return _unavailable(key, "current ReleaseRecord scope does not match requested authority")
    if record.status is not ReleaseStatus.PUBLISHED:
        return _unavailable(key, f"current release status is not V2 PUBLISHED: {record.status.value}")
    if record.ready_to_act is not True or record.safe_to_act is not True:
        return _unavailable(key, "current PUBLISHED ReleaseRecord is not actionable")
    if record.bundle_id is None or record.world_id is None:
        return _unavailable(key, "current PUBLISHED ReleaseRecord lacks bundle/world identity")
    if not str(record.runtime_digest).strip():
        return _unavailable(key, "current PUBLISHED ReleaseRecord lacks runtime identity")
    manifest_id = str(record.artifact_manifest_id).strip()
    if not manifest_id or not artifact_store.verify(manifest_id):
        return _unavailable(key, "current PUBLISHED release manifest is missing or corrupt")

    return ProductionAnswerAuthority(
        season=key.season,
        entry=key.entry,
        gameweek=key.gameweek,
        status=ProductionAuthorityStatus.CURRENT,
        release_id=ReleaseId(release_id),
        bundle_id=BundleId(record.bundle_id),
        world_id=GlobalWorldId(record.world_id),
        runtime_digest=record.runtime_digest,
        artifact_manifest_id=manifest_id,
        blockers=(),
    )
