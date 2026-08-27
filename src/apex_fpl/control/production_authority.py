"""Fail-closed resolution of the one current V2 production answer authority."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.champion_authority import verify_bundle_champion_authority
from apex_fpl.control.production_backend_qualification import (
    load_production_backend_qualification,
)
from apex_fpl.control.production_cutover import load_production_publication_authorization
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from apex_fpl.control.release_registry import ReleaseKey, ReleaseRecord, ReleaseStatus
from apex_fpl.core.ids import BundleId, GlobalWorldId, ReleaseId
from apex_fpl.core.production_authority import (
    ProductionAnswerAuthority,
    ProductionAuthorityStatus,
)


class ProductionCurrentReader(Protocol):
    backend_id: str

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


def _parse_timestamp(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not valid ISO-8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _backend_id(value: object, *, label: str) -> str:
    backend_id = getattr(value, "backend_id", None)
    if not isinstance(backend_id, str) or not backend_id.strip():
        raise ValueError(f"{label} has no stable backend identity")
    return backend_id.strip()


def resolve_production_answer_authority(
    *,
    season: str,
    entry: int,
    gameweek: int,
    as_of: str,
    artifact_store: ArtifactStore,
    production_registry: ProductionCurrentReader,
) -> ProductionAnswerAuthority:
    """Resolve only the exact current, unexpired, proof-authorized PUBLISHED V2 release.

    ``as_of`` is explicit so answer authority never depends on a hidden wall clock and can be
    replayed exactly. The current pointer is re-read immediately before authority is returned
    so a concurrent CAS cannot make a stale release user-facing during verification.
    """

    key = ReleaseKey(season, entry, gameweek)
    evaluation_time = _parse_timestamp(as_of, label="production authority as_of")

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

    try:
        created_at = _parse_timestamp(record.created_at, label="current release created_at")
    except ValueError as exc:
        return _unavailable(key, str(exc))
    if record.valid_until is None:
        return _unavailable(key, "current PUBLISHED release has no validity horizon")
    try:
        valid_until = _parse_timestamp(record.valid_until, label="current release valid_until")
    except ValueError as exc:
        return _unavailable(key, str(exc))
    if valid_until <= created_at:
        return _unavailable(key, "current release validity horizon is not after creation")
    if evaluation_time < created_at:
        return _unavailable(key, "current PUBLISHED release is not yet valid")
    if evaluation_time >= valid_until:
        return _unavailable(key, "current PUBLISHED release has expired")

    manifest_id = str(record.artifact_manifest_id).strip()
    if not manifest_id or not artifact_store.verify(manifest_id):
        return _unavailable(key, "current PUBLISHED release manifest is missing or corrupt")

    authorization_artifact_id = str(
        record.publication_authorization_artifact_id or ""
    ).strip()
    if not authorization_artifact_id:
        return _unavailable(key, "current PUBLISHED release lacks proof-derived authorization")
    try:
        authorization = load_production_publication_authorization(
            authorization_artifact_id,
            artifact_store=artifact_store,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _unavailable(key, f"current V2 publication authorization is invalid: {exc}")
    if not authorization.authorized:
        return _unavailable(key, "current publication authorization is WITHHELD")
    if (
        authorization.season != record.season
        or authorization.entry != record.entry
        or authorization.gameweek != record.gameweek
    ):
        return _unavailable(key, "publication authorization scope does not match ReleaseRecord")
    if authorization.bundle_id is None or str(authorization.bundle_id) != record.bundle_id:
        return _unavailable(key, "publication authorization bundle does not match ReleaseRecord")
    if authorization.world_id is None or str(authorization.world_id) != record.world_id:
        return _unavailable(key, "publication authorization world does not match ReleaseRecord")
    if authorization.runtime_digest != record.runtime_digest:
        return _unavailable(key, "publication authorization runtime does not match ReleaseRecord")
    if authorization.created_at != record.created_at:
        return _unavailable(key, "publication authorization creation time does not match ReleaseRecord")
    if authorization.valid_until != record.valid_until:
        return _unavailable(key, "publication authorization validity does not match ReleaseRecord")
    if authorization.artifact_manifest_id != record.artifact_manifest_id:
        return _unavailable(key, "publication authorization manifest does not match ReleaseRecord")

    try:
        verified_bundle = load_production_planning_bundle(
            BundleId(record.bundle_id),
            store=artifact_store,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _unavailable(key, f"current V2 production planning bundle is invalid: {exc}")
    bundle = verified_bundle.bundle
    if (
        bundle.season != record.season
        or bundle.entry != record.entry
        or bundle.gameweek != record.gameweek
    ):
        return _unavailable(key, "production planning bundle scope does not match ReleaseRecord")
    if str(bundle.world_id) != record.world_id:
        return _unavailable(key, "production planning bundle world does not match ReleaseRecord")
    if authorization.champion_generation_artifact_id is None:
        return _unavailable(key, "publication authorization lacks production champion authority")
    try:
        verify_bundle_champion_authority(
            authorization.champion_generation_artifact_id,
            verified_bundle=verified_bundle,
            as_of=authorization.created_at,
            store=artifact_store,
        )
    except (FileNotFoundError, ValueError) as exc:
        return _unavailable(key, f"current production champion authority is invalid: {exc}")

    try:
        qualification = load_production_backend_qualification(
            authorization.backend_qualification_snapshot_artifact_id,
            artifact_store=artifact_store,
        )
        artifact_backend_id = _backend_id(
            artifact_store,
            label="production authority ArtifactStore",
        )
        registry_backend_id = _backend_id(
            production_registry,
            label="production authority ReleaseRegistry",
        )
    except (FileNotFoundError, ValueError) as exc:
        return _unavailable(key, f"current production backend qualification is invalid: {exc}")
    if qualification.qualification_id != authorization.backend_qualification_id:
        return _unavailable(key, "publication authorization backend identity does not reconcile")
    if not qualification.qualified:
        return _unavailable(key, "current production backend qualification is not production-qualified")
    if qualification.artifact_store_backend_id != artifact_backend_id:
        return _unavailable(key, "current ArtifactStore backend differs from publication authorization")
    if qualification.release_registry_backend_id != registry_backend_id:
        return _unavailable(key, "current ReleaseRegistry backend differs from publication authorization")
    if qualification.qualification_scope != f"{season}:{entry}:{gameweek}:production":
        return _unavailable(key, "current production backend qualification scope does not match authority")

    if production_registry.current_release_id(key) != release_id:
        return _unavailable(key, "current V2 production pointer changed during authority verification")

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
