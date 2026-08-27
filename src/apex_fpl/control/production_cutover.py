"""Authoritative fail-closed V2 production cutover.

The detailed proof/certificate transaction remains isolated in the private legacy engine;
this public module is the only supported publication entry point and adds the immutable
ArtifactManifest -> current ProductionAuthorityRoot gate around that transaction.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from apex_fpl.control import _production_cutover_legacy as _legacy
from apex_fpl.control.backend_ports import ProductionAuthorityRootRegistry
from apex_fpl.control.postgres_atomic_publication import (
    compare_and_swap_release_under_authority_root,
    is_postgres_release_registry,
)
from apex_fpl.control.production_authority_verification import (
    VerifiedProductionAuthorityClosure,
    require_authority_root_unchanged,
    verify_production_authority_closure,
)
from apex_fpl.core.artifact_manifest import ArtifactManifestRole

# Preserve the established replay/report API while keeping the raw publication engine private.
for _name in dir(_legacy):
    if _name.startswith("__") or _name == "execute_production_cutover":
        continue
    globals()[_name] = getattr(_legacy, _name)


def _instant(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} is not valid ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _require_manifest_input_binding(
    closure: VerifiedProductionAuthorityClosure,
    *,
    role: ArtifactManifestRole,
    artifact_id: str,
) -> None:
    entry = closure.manifest.require_role(role)
    if entry.artifact_id != str(artifact_id):
        raise ValueError(
            f"artifact manifest {role.value} does not bind the exact cutover input snapshot"
        )


class _RootGuardedReleaseRegistry:
    """Delegate persistence while binding release CAS to the exact authority-root pointer.

    Reference/non-PostgreSQL adapters receive the portable before-CAS root check. The real
    PostgreSQL release adapter uses a stronger primitive: root-pointer verification and release
    CAS occur in one database transaction while the season root row is locked ``FOR UPDATE``.
    """

    def __init__(
        self,
        delegate,
        *,
        closure: VerifiedProductionAuthorityClosure,
        season: str,
        authority_root_registry: ProductionAuthorityRootRegistry,
    ) -> None:
        self._delegate = delegate
        self._closure = closure
        self._season = season
        self._authority_root_registry = authority_root_registry
        self.backend_id = delegate.backend_id

    def __getattr__(self, name: str):
        return getattr(self._delegate, name)

    def compare_and_swap_current(self, key, *, expected_release_id, new_release_id) -> None:
        require_authority_root_unchanged(
            self._closure,
            season=self._season,
            authority_root_registry=self._authority_root_registry,
        )
        if is_postgres_release_registry(self._delegate):
            compare_and_swap_release_under_authority_root(
                self._delegate,
                self._authority_root_registry,
                key,
                expected_release_id=expected_release_id,
                new_release_id=new_release_id,
                expected_root_id=self._closure.current_root_id,
            )
            return
        self._delegate.compare_and_swap_current(
            key,
            expected_release_id=expected_release_id,
            new_release_id=new_release_id,
        )


def execute_production_cutover(
    *,
    season: str,
    entry: int,
    gameweek: int,
    bundle_id: _legacy.BundleId | None,
    world_id: _legacy.GlobalWorldId | None,
    runtime_digest: str,
    created_at: str,
    valid_until: str | None,
    artifact_manifest_id: str,
    assurance_case: _legacy.AssuranceCase,
    obligations: Iterable[_legacy.ProofObligation],
    backend_qualification: _legacy.ProductionBackendQualification,
    artifact_store: _legacy.ArtifactStore,
    production_registry: _legacy.ProductionReleaseRegistry,
    champion_generation_artifact_id: str | None = None,
    authority_root_registry: ProductionAuthorityRootRegistry | None = None,
) -> _legacy.ProductionCutoverOutcome:
    """Publish only after replaying the exact current authority root and full manifest closure."""

    if authority_root_registry is None:
        raise ValueError("production AuthorityRootRegistry is required for cutover")
    if bundle_id is None or world_id is None:
        raise ValueError("rooted production cutover requires bundle and world identity")
    if valid_until is None:
        raise ValueError("rooted production cutover requires a validity horizon")
    if champion_generation_artifact_id is None:
        raise ValueError("rooted production cutover requires champion authority")

    obligations_tuple = tuple(sorted(tuple(obligations), key=lambda item: item.proof_id))
    case_artifact_id, proof_artifact_id = _legacy._seal_release_policy(
        assurance_case,
        obligations_tuple,
        store=artifact_store,
    )
    backend_snapshot_id = _legacy._seal_backend_qualification(
        backend_qualification,
        store=artifact_store,
    )

    closure = verify_production_authority_closure(
        artifact_manifest_id=artifact_manifest_id,
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=str(bundle_id),
        world_id=str(world_id),
        runtime_digest=runtime_digest,
        as_of=created_at,
        store=artifact_store,
        authority_root_registry=authority_root_registry,
    )
    _require_manifest_input_binding(
        closure,
        role=ArtifactManifestRole.ASSURANCE_CASE,
        artifact_id=case_artifact_id,
    )
    _require_manifest_input_binding(
        closure,
        role=ArtifactManifestRole.PROOF_OBLIGATIONS,
        artifact_id=proof_artifact_id,
    )
    _require_manifest_input_binding(
        closure,
        role=ArtifactManifestRole.BACKEND_QUALIFICATION,
        artifact_id=backend_snapshot_id,
    )
    if (
        closure.authority.root.champion_generation_artifact_id
        != str(champion_generation_artifact_id)
    ):
        raise ValueError("cutover champion authority does not match production authority root")

    release_start = _instant(created_at, label="production created_at")
    release_end = _instant(valid_until, label="production valid_until")
    root_start = _instant(closure.authority.root.valid_from, label="authority root valid_from")
    root_end = _instant(closure.authority.root.valid_until, label="authority root valid_until")
    if root_start > release_start or root_end < release_end:
        raise ValueError("production authority root does not cover the full release validity horizon")

    guarded_registry = _RootGuardedReleaseRegistry(
        production_registry,
        closure=closure,
        season=season,
        authority_root_registry=authority_root_registry,
    )
    outcome = _legacy.execute_production_cutover(
        season=season,
        entry=entry,
        gameweek=gameweek,
        bundle_id=bundle_id,
        world_id=world_id,
        runtime_digest=runtime_digest,
        created_at=created_at,
        valid_until=valid_until,
        artifact_manifest_id=artifact_manifest_id,
        assurance_case=assurance_case,
        obligations=obligations_tuple,
        backend_qualification=backend_qualification,
        artifact_store=artifact_store,
        production_registry=guarded_registry,
        champion_generation_artifact_id=champion_generation_artifact_id,
    )
    require_authority_root_unchanged(
        closure,
        season=season,
        authority_root_registry=authority_root_registry,
    )
    return outcome
