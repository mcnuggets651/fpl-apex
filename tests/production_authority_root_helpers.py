from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from apex_fpl.control import _production_cutover_legacy as _legacy_cutover
from apex_fpl.control.artifact_manifest import store_artifact_manifest
from apex_fpl.control.authority_root_backend_qualification import (
    StoredAuthorityRootRegistryQualification,
    qualify_authority_root_registry,
)
from apex_fpl.control.authority_root_registry import FileSystemAuthorityRootRegistry
from apex_fpl.control.production_authority_root import store_production_authority_root
from apex_fpl.control.provenance import BuildManifest
from apex_fpl.core.artifact_manifest import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactManifestRole,
)
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot

from learning_promotion_helpers import _policy_bundle, _truth


@dataclass(frozen=True, slots=True)
class RootedProductionAuthorityMaterial:
    authority_root_registry: "SyntheticProductionAuthorityRootRegistry"
    registry_qualification: StoredAuthorityRootRegistryQualification
    root: ProductionAuthorityRoot
    root_artifact_id: str
    artifact_manifest_id: str
    runtime_digest: str


class SyntheticProductionAuthorityRootRegistry:
    """Durable mechanism-only root registry with the production backend identity shape.

    This wrapper exists only in tests. It deliberately exercises the same reopen/history/CAS
    protocol as the PostgreSQL adapter while retaining filesystem state under ``tmp_path``.
    The resulting qualification is synthetic mechanism evidence and is never production
    activation evidence.
    """

    backend_id = "apex.production.postgres-authority-root-registry.v1:synthetic-test"

    def __init__(self, root: Path):
        self.root = Path(root)
        self.delegate = FileSystemAuthorityRootRegistry(self.root)

    def reopen(self) -> "SyntheticProductionAuthorityRootRegistry":
        return SyntheticProductionAuthorityRootRegistry(self.root)

    def append(self, root: ProductionAuthorityRoot) -> None:
        self.delegate.append(root)

    def read_root(self, root_id: str) -> ProductionAuthorityRoot:
        return self.delegate.read_root(root_id)

    def current_root_id(self, season: str) -> str | None:
        return self.delegate.current_root_id(season)

    def compare_and_swap_current(
        self,
        season: str,
        *,
        expected_root_id: str | None,
        new_root_id: str,
    ) -> None:
        self.delegate.compare_and_swap_current(
            season,
            expected_root_id=expected_root_id,
            new_root_id=new_root_id,
        )


def _store_build_manifest(*, store, runtime_digest: str, built_at: str) -> tuple[BuildManifest, str]:
    dependency_lock = store.put_bytes(b"synthetic-rooted-dependency-lock").artifact_id
    sbom = store.put_bytes(b"synthetic-rooted-sbom").artifact_id
    provenance = store.put_bytes(b"synthetic-rooted-provenance").artifact_id
    base_image = store.put_bytes(b"synthetic-rooted-base-image").artifact_id
    manifest = BuildManifest(
        source_sha="0" * 40,
        dependency_lock_digest=dependency_lock,
        runtime_digest=runtime_digest,
        base_image_digest=base_image,
        builder_identity="synthetic-rooted-authority-fixture",
        built_at=built_at,
        sbom_artifact_id=sbom,
        provenance_artifact_id=provenance,
    )
    envelope = {
        "schema_name": "apex-build-manifest",
        "schema_version": 1,
        "build_manifest_id": manifest.build_manifest_id,
        "payload": manifest.semantic_payload(),
    }
    artifact_id = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-build-manifest",
        schema_version="1",
    ).artifact_id
    return manifest, artifact_id


def build_rooted_production_authority_material(
    *,
    tmp_path: Path,
    store,
    fixture,
    parity,
    champion,
    assurance_case,
    obligations,
    backend_qualification,
    authorized_at: str,
    root_valid_until: str,
) -> RootedProductionAuthorityMaterial:
    """Build a fully replayable synthetic production authority closure.

    The fixture intentionally uses real typed/replayable component artifacts. No mandatory
    manifest role is satisfied by an opaque placeholder hash. Deterministic cutover snapshots
    are pre-sealed so the public cutover must reproduce the exact same content identities.
    """

    season = fixture.bundle.season
    obligations_tuple = tuple(sorted(tuple(obligations), key=lambda item: item.proof_id))
    assurance_artifact_id, obligations_artifact_id = _legacy_cutover._seal_release_policy(
        assurance_case,
        obligations_tuple,
        store=store,
    )
    backend_artifact_id = _legacy_cutover._seal_backend_qualification(
        backend_qualification,
        store=store,
    )

    runtime_digest = store.put_bytes(b"synthetic-rooted-runtime").artifact_id
    world_payload = {
        "schema_name": "synthetic-production-planning-world",
        "season": fixture.bundle.season,
        "entry": fixture.bundle.entry,
        "gameweek": fixture.bundle.gameweek,
    }
    world_artifact_id = store.put_bytes(canonical_json_bytes(world_payload)).artifact_id
    if world_artifact_id != str(fixture.bundle.world_id):
        raise AssertionError("synthetic world storage identity drifted from planning fixture")

    learning_policy, _, _, learning_registry_artifact_id = _policy_bundle(
        store=store,
        season=season,
    )
    truth_registry, truth_registry_artifact_id = _truth(store)
    build_manifest, build_manifest_artifact_id = _store_build_manifest(
        store=store,
        runtime_digest=runtime_digest,
        built_at=authorized_at,
    )
    change_control_artifact_id = store.put_bytes(
        b"synthetic-rooted-authority-change-control"
    ).artifact_id

    root = ProductionAuthorityRoot(
        season=season,
        generation=1,
        parent_root_artifact_id=None,
        champion_generation_artifact_id=champion.generation.artifact_id,
        ruleset_artifact_id=fixture.bundle.ruleset_artifact_id,
        ruleset_id=str(fixture.bundle.ruleset_id),
        learning_policy_registry_artifact_id=learning_registry_artifact_id,
        learning_policy_id=str(learning_policy.policy_id),
        outcome_truth_registry_artifact_id=truth_registry_artifact_id,
        outcome_truth_registry_id=truth_registry.registry_id,
        build_manifest_artifact_id=build_manifest_artifact_id,
        build_manifest_id=build_manifest.build_manifest_id,
        change_control_artifact_id=change_control_artifact_id,
        authorized_by="synthetic-root-authorizer",
        authorized_at=authorized_at,
        valid_from=authorized_at,
        valid_until=root_valid_until,
        reason="synthetic mechanism-only rooted production authority",
    )
    root_artifact_id = store_production_authority_root(root, store=store)

    root_registry = SyntheticProductionAuthorityRootRegistry(tmp_path / "authority-roots")
    qualification = qualify_authority_root_registry(
        root_registry,
        store=store,
        qualification_scope=f"{season}:production",
        probe_nonce="rooted-production-authority-fixture",
    )
    if not qualification.qualification.qualified:
        raise AssertionError("synthetic production-shaped root registry failed mechanism qualification")
    root_registry.append(root)
    root_registry.compare_and_swap_current(
        season,
        expected_root_id=None,
        new_root_id=root.root_id,
    )

    entries = (
        ArtifactManifestEntry(
            ArtifactManifestRole.PLANNING_BUNDLE,
            str(fixture.bundle.bundle_id),
            str(fixture.bundle.bundle_id),
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.WORLD,
            world_artifact_id,
            world_artifact_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.ASSURANCE_CASE,
            assurance_artifact_id,
            assurance_case.case_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.PROOF_OBLIGATIONS,
            obligations_artifact_id,
            obligations_artifact_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.BACKEND_QUALIFICATION,
            backend_artifact_id,
            backend_qualification.qualification_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.AUTHORITY_ROOT_REGISTRY_QUALIFICATION,
            qualification.artifact_id,
            qualification.qualification.qualification_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.CHAMPION_GENERATION,
            champion.generation.artifact_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.AUTHORITY_ROOT,
            root_artifact_id,
            root.root_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.BUILD_MANIFEST,
            build_manifest_artifact_id,
            build_manifest.build_manifest_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.RULESET,
            fixture.bundle.ruleset_artifact_id,
            str(fixture.bundle.ruleset_id),
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.LEARNING_POLICY_REGISTRY,
            learning_registry_artifact_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.OUTCOME_TRUTH_REGISTRY,
            truth_registry_artifact_id,
            truth_registry.registry_id,
        ),
        ArtifactManifestEntry(
            ArtifactManifestRole.REFERENCE_SOLVER_AUTHORIZATION,
            parity.authorization_artifact_id,
            parity.authorization_id,
        ),
    )
    manifest = ArtifactManifest(
        season=season,
        entry=fixture.bundle.entry,
        gameweek=fixture.bundle.gameweek,
        bundle_id=str(fixture.bundle.bundle_id),
        world_id=world_artifact_id,
        runtime_digest=runtime_digest,
        authority_root_artifact_id=root_artifact_id,
        entries=tuple(sorted(entries, key=lambda item: item.role.value)),
    )
    artifact_manifest_id = store_artifact_manifest(manifest, store=store)
    return RootedProductionAuthorityMaterial(
        authority_root_registry=root_registry,
        registry_qualification=qualification,
        root=root,
        root_artifact_id=root_artifact_id,
        artifact_manifest_id=artifact_manifest_id,
        runtime_digest=runtime_digest,
    )
