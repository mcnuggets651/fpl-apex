"""Shared fail-closed verification for the published production authority closure.

Release publication and answer-time resolution must prove the same authority chain:
ReleaseRecord -> ArtifactManifest -> current ProductionAuthorityRoot.  This module keeps
that replay contract in one place so cutover and serving cannot silently diverge.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_fpl.control.artifact_manifest import (
    load_artifact_manifest,
    verify_artifact_manifest_scope,
)
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.authority_root_backend_qualification import (
    StoredAuthorityRootRegistryQualification,
    load_authority_root_registry_qualification,
)
from apex_fpl.control.backend_ports import ProductionAuthorityRootRegistry
from apex_fpl.control.production_authority_root import (
    VerifiedProductionAuthorityRoot,
    verify_production_authority_root,
)
from apex_fpl.core.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactManifestRole,
)


@dataclass(frozen=True, slots=True)
class VerifiedProductionAuthorityClosure:
    """Identity snapshot captured before a production publication/answer operation."""

    manifest: ArtifactManifest
    authority: VerifiedProductionAuthorityRoot
    registry_qualification: StoredAuthorityRootRegistryQualification
    current_root_id: str


def _backend_id(registry: ProductionAuthorityRootRegistry) -> str:
    value = getattr(registry, "backend_id", None)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("production AuthorityRootRegistry has no stable backend identity")
    return value.strip()


def _require_artifact_role(
    manifest: ArtifactManifest,
    role: ArtifactManifestRole,
    expected_artifact_id: str,
    *,
    expected_semantic_id: str | None = None,
) -> ArtifactManifestEntry:
    entry = manifest.require_role(role)
    if entry.artifact_id != str(expected_artifact_id):
        raise ValueError(
            f"artifact manifest {role.value} does not match production authority root"
        )
    if (
        expected_semantic_id is not None
        and entry.semantic_id is not None
        and entry.semantic_id != str(expected_semantic_id)
    ):
        raise ValueError(
            f"artifact manifest {role.value} semantic identity does not match "
            "production authority root"
        )
    return entry


def verify_production_authority_closure(
    *,
    artifact_manifest_id: str,
    season: str,
    entry: int,
    gameweek: int,
    bundle_id: str,
    world_id: str,
    runtime_digest: str,
    as_of: str,
    store: ArtifactStore,
    authority_root_registry: ProductionAuthorityRootRegistry,
) -> VerifiedProductionAuthorityClosure:
    """Replay the complete manifest/root authority chain at the caller's exact ``as_of``."""

    manifest = load_artifact_manifest(
        str(artifact_manifest_id),
        store=store,
        verify_members=True,
    )
    verify_artifact_manifest_scope(
        manifest,
        season=str(season),
        entry=entry,
        gameweek=gameweek,
        bundle_id=str(bundle_id),
        world_id=str(world_id),
        runtime_digest=str(runtime_digest),
        authority_root_artifact_id=manifest.authority_root_artifact_id,
    )

    qualification_entry = manifest.require_role(
        ArtifactManifestRole.AUTHORITY_ROOT_REGISTRY_QUALIFICATION
    )
    qualification = load_authority_root_registry_qualification(
        qualification_entry.artifact_id,
        store=store,
        expected_backend_id=_backend_id(authority_root_registry),
        expected_scope=f"{season}:production",
    )
    if not qualification.qualification.qualified:
        raise ValueError("production AuthorityRootRegistry is not independently qualified")
    if (
        qualification_entry.semantic_id is not None
        and qualification_entry.semantic_id != qualification.qualification.qualification_id
    ):
        raise ValueError(
            "artifact manifest authority-root registry qualification semantic identity mismatch"
        )

    root_entry = manifest.require_role(ArtifactManifestRole.AUTHORITY_ROOT)
    current_root_id = authority_root_registry.current_root_id(str(season))
    if current_root_id is None:
        raise ValueError("production authority-root current pointer is missing")
    if current_root_id != root_entry.artifact_id:
        raise ValueError("production authority-root current pointer does not match release manifest")

    registry_root = authority_root_registry.read_root(current_root_id)
    verified = verify_production_authority_root(
        current_root_id,
        as_of=str(as_of),
        store=store,
        expected_runtime_digest=str(runtime_digest),
    )
    root = verified.root
    if registry_root != root:
        raise ValueError("production authority root differs between registry and ArtifactStore")
    if root.season != str(season):
        raise ValueError("production authority root season does not match release")
    if root_entry.semantic_id is not None and root_entry.semantic_id != root.root_id:
        raise ValueError("artifact manifest AUTHORITY_ROOT semantic identity mismatch")

    _require_artifact_role(
        manifest,
        ArtifactManifestRole.CHAMPION_GENERATION,
        root.champion_generation_artifact_id,
    )
    _require_artifact_role(
        manifest,
        ArtifactManifestRole.RULESET,
        root.ruleset_artifact_id,
        expected_semantic_id=root.ruleset_id,
    )
    _require_artifact_role(
        manifest,
        ArtifactManifestRole.LEARNING_POLICY_REGISTRY,
        root.learning_policy_registry_artifact_id,
    )
    _require_artifact_role(
        manifest,
        ArtifactManifestRole.OUTCOME_TRUTH_REGISTRY,
        root.outcome_truth_registry_artifact_id,
        expected_semantic_id=root.outcome_truth_registry_id,
    )
    _require_artifact_role(
        manifest,
        ArtifactManifestRole.BUILD_MANIFEST,
        root.build_manifest_artifact_id,
        expected_semantic_id=root.build_manifest_id,
    )

    return VerifiedProductionAuthorityClosure(
        manifest=manifest,
        authority=verified,
        registry_qualification=qualification,
        current_root_id=current_root_id,
    )


def require_authority_root_unchanged(
    verified: VerifiedProductionAuthorityClosure,
    *,
    season: str,
    authority_root_registry: ProductionAuthorityRootRegistry,
) -> None:
    """Final TOCTOU guard: the exact season authority pointer must remain unchanged."""

    current = authority_root_registry.current_root_id(str(season))
    if current != verified.current_root_id:
        raise ValueError("production authority-root pointer changed during resolution")
