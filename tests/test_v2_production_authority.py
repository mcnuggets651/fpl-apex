from __future__ import annotations

from pathlib import Path

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.production_authority import resolve_production_answer_authority
from apex_fpl.control.production_cutover import execute_production_cutover
from apex_fpl.control.release_registry import (
    FileSystemReleaseRegistry,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)
from apex_fpl.core.ids import BundleId, GlobalWorldId
from apex_fpl.core.production import MANDATORY_PRODUCTION_PROOF_IDS, ProductionBackendQualification
from apex_fpl.core.production_authority import ProductionAuthorityStatus
from apex_fpl.core.proofs import (
    AssuranceCase,
    AssuranceClaim,
    ProofClass,
    ProofObligation,
    ProofStatus,
    ReleasePolicy,
)


SEASON = "2026-2027"
ENTRY = 63984
GAMEWEEK = 2
SCOPE = f"{SEASON}:{ENTRY}:{GAMEWEEK}:production"


def _artifact(store: FileSystemArtifactStore, text: str) -> str:
    return store.put_bytes(text.encode("utf-8")).artifact_id


def _qualified_cutover(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    evidence = _artifact(store, "proof-evidence")
    manifest = _artifact(store, "manifest")
    store_q = _artifact(store, "store-qualified")
    registry_q = _artifact(store, "registry-qualified")
    obligations = tuple(
        ProofObligation(
            proof_id=proof_id,
            claim=f"qualified {proof_id}",
            proof_class=ProofClass.FORMAL_INVARIANT,
            scope="production-test",
            required_evidence=("artifact",),
            required_tests=("test",),
            failure_consequence="withhold",
            release_policy=ReleasePolicy.REQUIRED,
            owner="tests",
        )
        for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS)
    )
    case = AssuranceCase(
        release_scope=SCOPE,
        claims=tuple(
            AssuranceClaim(
                proof_id=proof_id,
                status=ProofStatus.PROVEN,
                evidence_ids=("evidence",),
                test_ids=("test",),
                artifact_ids=(evidence,),
            )
            for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS)
        ),
    )
    backend = ProductionBackendQualification(
        artifact_store_qualification_artifact_id=store_q,
        release_registry_qualification_artifact_id=registry_q,
        durable_shared_artifact_store=True,
        durable_shared_release_registry=True,
        atomic_compare_and_swap=True,
        immutable_release_history=True,
        qualification_scope=SCOPE,
    )
    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=BundleId("bundle-v2"),
        world_id=GlobalWorldId("world-v2"),
        runtime_digest="sha256:runtime-v2",
        created_at="2026-08-25T06:00:00Z",
        valid_until="2026-08-29T10:00:00Z",
        artifact_manifest_id=manifest,
        assurance_case=case,
        obligations=obligations,
        backend_qualification=backend,
        artifact_store=store,
        production_registry=registry,
    )
    return store, registry, outcome


def test_no_current_pointer_is_non_actionable_and_exposes_no_bundle(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    authority = resolve_production_answer_authority(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        artifact_store=store,
        production_registry=registry,
    )
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.ready_to_act is False
    assert authority.safe_to_act is False
    assert authority.production_result_bundle_id is None


def test_exact_current_proof_authorized_release_is_only_actionable_authority(tmp_path: Path) -> None:
    store, registry, outcome = _qualified_cutover(tmp_path)
    authority = resolve_production_answer_authority(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        artifact_store=store,
        production_registry=registry,
    )
    assert authority.status is ProductionAuthorityStatus.CURRENT
    assert authority.ready_to_act is True
    assert authority.safe_to_act is True
    assert authority.release_id is not None
    assert str(authority.release_id) == outcome.release_record.release_id
    assert authority.production_result_bundle_id == BundleId("bundle-v2")


def _make_current_record(
    *,
    store: FileSystemArtifactStore,
    registry: FileSystemReleaseRegistry,
    status: ReleaseStatus,
    ready: bool,
    safe: bool,
    authorization_artifact_id: str | None = None,
) -> ReleaseRecord:
    manifest = _artifact(store, f"manifest-{status.value}")
    record = registry.append(
        ReleaseRecord(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id="forged-bundle",
            world_id="forged-world",
            runtime_digest="sha256:forged-runtime",
            created_at="2026-08-25T06:00:00Z",
            valid_until=None,
            status=status,
            ready_to_act=ready,
            safe_to_act=safe,
            artifact_manifest_id=manifest,
            publication_authorization_artifact_id=authorization_artifact_id,
        )
    )
    assert record.release_id is not None
    registry.compare_and_swap_current(
        ReleaseKey(SEASON, ENTRY, GAMEWEEK),
        expected_release_id=None,
        new_release_id=record.release_id,
    )
    return record


def test_forged_published_ready_record_without_authorization_is_rejected(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    _make_current_record(
        store=store,
        registry=registry,
        status=ReleaseStatus.PUBLISHED,
        ready=True,
        safe=True,
    )
    authority = resolve_production_answer_authority(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        artifact_store=store,
        production_registry=registry,
    )
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert "lacks proof-derived authorization" in authority.blockers[0]
    assert authority.production_result_bundle_id is None


def test_v1_and_certified_records_cannot_become_v2_answer_authority(tmp_path: Path) -> None:
    for index, status in enumerate((ReleaseStatus.V1_ACTIONABLE, ReleaseStatus.CERTIFIED), start=1):
        root = tmp_path / str(index)
        store = FileSystemArtifactStore(root / "artifacts")
        registry = FileSystemReleaseRegistry(root / "production")
        _make_current_record(
            store=store,
            registry=registry,
            status=status,
            ready=status is ReleaseStatus.V1_ACTIONABLE,
            safe=status is ReleaseStatus.V1_ACTIONABLE,
        )
        authority = resolve_production_answer_authority(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            artifact_store=store,
            production_registry=registry,
        )
        assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
        assert authority.production_result_bundle_id is None
        assert "not V2 PUBLISHED" in authority.blockers[0]


def test_corrupt_publication_authorization_withholds_current_answer(tmp_path: Path) -> None:
    store, registry, outcome = _qualified_cutover(tmp_path)
    artifact_id = outcome.release_record.publication_authorization_artifact_id
    assert artifact_id is not None
    digest = artifact_id.split(":", 1)[1]
    path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    path.write_bytes(b"corrupt")
    authority = resolve_production_answer_authority(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        artifact_store=store,
        production_registry=registry,
    )
    assert authority.status is ProductionAuthorityStatus.UNAVAILABLE
    assert authority.production_result_bundle_id is None
    assert "publication authorization is invalid" in authority.blockers[0]
