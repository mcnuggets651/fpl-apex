"""Shared fail-closed verification for the published production authority closure.

Release publication and answer-time resolution prove one chain:
ReleaseRecord -> ArtifactManifest -> current ProductionAuthorityRoot. Every mandatory
manifest role is replayed as its expected type so a content-valid artifact cannot be
substituted into the wrong semantic role.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_fpl.assurance.reference_solver_planning_exchange import (
    load_planning_reference_solver_certificate,
)
from apex_fpl.assurance.worker_authorization import load_reference_solver_authorization
from apex_fpl.control import _production_cutover_legacy as _cutover_replay
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
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from apex_fpl.control.production_reference_solver_binding import REFERENCE_SOLVER_PARITY_PROOF_ID
from apex_fpl.core.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactManifestRole,
)
from apex_fpl.core.ids import BundleId


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


def _require_semantic(entry: ArtifactManifestEntry, expected: str, *, label: str) -> None:
    if entry.semantic_id != str(expected):
        raise ValueError(f"artifact manifest {label} semantic identity mismatch")


def _require_artifact_role(
    manifest: ArtifactManifest,
    role: ArtifactManifestRole,
    expected_artifact_id: str,
    *,
    expected_semantic_id: str | None = None,
) -> ArtifactManifestEntry:
    entry = manifest.require_role(role)
    if entry.artifact_id != str(expected_artifact_id):
        raise ValueError(f"artifact manifest {role.value} does not match production authority root")
    if expected_semantic_id is not None:
        _require_semantic(entry, str(expected_semantic_id), label=role.value)
    return entry


def _verify_reference_solver_authorization(
    manifest: ArtifactManifest,
    *,
    assurance_case,
    verified_bundle,
    store: ArtifactStore,
) -> None:
    entry = manifest.require_role(ArtifactManifestRole.REFERENCE_SOLVER_AUTHORIZATION)
    claim = next(
        (item for item in assurance_case.claims if item.proof_id == REFERENCE_SOLVER_PARITY_PROOF_ID),
        None,
    )
    if claim is None or entry.artifact_id not in claim.artifact_ids:
        raise ValueError("manifest reference-solver authorization is not retained by parity claim")
    for candidate_id in claim.artifact_ids:
        if candidate_id == entry.artifact_id:
            continue
        try:
            certificate = load_planning_reference_solver_certificate(candidate_id, store=store).certificate
            stored = load_reference_solver_authorization(
                entry.artifact_id,
                certificate=certificate,
                store=store,
            )
        except (FileNotFoundError, ValueError):
            continue
        authorization = stored.authorization
        if authorization.season != verified_bundle.bundle.season:
            continue
        if authorization.decision_cutoff != verified_bundle.forecast.feature_cutoff:
            continue
        if authorization.horizon_gameweeks != verified_bundle.decision_policy.horizon_gameweeks:
            continue
        if authorization.solver_certificate_id != certificate.certificate_id:
            continue
        _require_semantic(
            entry,
            str(authorization.authorization_id),
            label=ArtifactManifestRole.REFERENCE_SOLVER_AUTHORIZATION.value,
        )
        return
    raise ValueError("manifest reference-solver authorization failed typed replay")


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
    """Replay every mandatory manifest role and the current root at exact ``as_of``."""

    manifest = load_artifact_manifest(str(artifact_manifest_id), store=store, verify_members=True)
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

    planning_entry = manifest.require_role(ArtifactManifestRole.PLANNING_BUNDLE)
    verified_bundle = load_production_planning_bundle(BundleId(planning_entry.artifact_id), store=store)
    bundle = verified_bundle.bundle
    if (
        bundle.season != str(season)
        or bundle.entry != entry
        or bundle.gameweek != gameweek
        or str(bundle.world_id) != str(world_id)
    ):
        raise ValueError("manifest planning bundle typed replay does not match release scope")
    if planning_entry.semantic_id is not None:
        _require_semantic(planning_entry, str(bundle.bundle_id), label=planning_entry.role.value)
    world_entry = manifest.require_role(ArtifactManifestRole.WORLD)
    if world_entry.artifact_id != str(bundle.world_id):
        raise ValueError("manifest WORLD does not match typed planning-bundle world")
    if world_entry.semantic_id is not None:
        _require_semantic(world_entry, str(bundle.world_id), label=world_entry.role.value)

    assurance_entry = manifest.require_role(ArtifactManifestRole.ASSURANCE_CASE)
    assurance_case = _cutover_replay._replay_assurance_case(
        assurance_entry.artifact_id,
        artifact_store=store,
    )
    _require_semantic(assurance_entry, assurance_case.case_id, label=assurance_entry.role.value)

    obligations_entry = manifest.require_role(ArtifactManifestRole.PROOF_OBLIGATIONS)
    _cutover_replay._replay_obligations(obligations_entry.artifact_id, artifact_store=store)
    if obligations_entry.semantic_id is not None:
        _require_semantic(
            obligations_entry,
            obligations_entry.artifact_id,
            label=obligations_entry.role.value,
        )

    backend_entry = manifest.require_role(ArtifactManifestRole.BACKEND_QUALIFICATION)
    backend_qualification = _cutover_replay._replay_backend_qualification(
        backend_entry.artifact_id,
        artifact_store=store,
    )
    _require_semantic(
        backend_entry,
        backend_qualification.qualification_id,
        label=backend_entry.role.value,
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
    _require_semantic(
        qualification_entry,
        qualification.qualification.qualification_id,
        label=qualification_entry.role.value,
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
    _require_semantic(root_entry, root.root_id, label=root_entry.role.value)

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

    _verify_reference_solver_authorization(
        manifest,
        assurance_case=assurance_case,
        verified_bundle=verified_bundle,
        store=store,
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
