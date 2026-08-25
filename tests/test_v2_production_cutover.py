from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.production_cutover import (
    execute_production_cutover,
    load_production_cutover_report,
)
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    FileSystemReleaseRegistry,
    ReleaseKey,
    ReleaseStatus,
)
from apex_fpl.core.ids import BundleId, GlobalWorldId
from apex_fpl.core.production import (
    MANDATORY_PRODUCTION_PROOF_IDS,
    ProductionBackendQualification,
    ProductionCutoverStatus,
)
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


def _artifact(store: FileSystemArtifactStore, value: str) -> str:
    return store.put_bytes(value.encode("utf-8")).artifact_id


def _obligations() -> tuple[ProofObligation, ...]:
    return tuple(
        ProofObligation(
            proof_id=proof_id,
            claim=f"synthetic production proof for {proof_id}",
            proof_class=ProofClass.FORMAL_INVARIANT,
            scope="production-test",
            required_evidence=("synthetic-evidence",),
            required_tests=("synthetic-test",),
            failure_consequence="withhold production",
            release_policy=ReleasePolicy.REQUIRED,
            owner="tests",
        )
        for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS)
    )


def _case(
    claim_artifact: str,
    *,
    missing: str | None = None,
    inconclusive: str | None = None,
    scope: str = SCOPE,
) -> AssuranceCase:
    claims = []
    for proof_id in sorted(MANDATORY_PRODUCTION_PROOF_IDS):
        if proof_id == missing:
            continue
        claims.append(
            AssuranceClaim(
                proof_id=proof_id,
                status=(
                    ProofStatus.INCONCLUSIVE
                    if proof_id == inconclusive
                    else ProofStatus.PROVEN
                ),
                evidence_ids=("synthetic-evidence",),
                test_ids=("synthetic-test",),
                artifact_ids=(claim_artifact,),
            )
        )
    return AssuranceCase(release_scope=scope, claims=tuple(claims))


def _backend(
    store: FileSystemArtifactStore,
    *,
    qualified: bool = True,
    scope: str = SCOPE,
) -> ProductionBackendQualification:
    return ProductionBackendQualification(
        artifact_store_qualification_artifact_id=_artifact(store, "artifact-store-qualified"),
        release_registry_qualification_artifact_id=_artifact(store, "registry-qualified"),
        durable_shared_artifact_store=qualified,
        durable_shared_release_registry=qualified,
        atomic_compare_and_swap=qualified,
        immutable_release_history=qualified,
        qualification_scope=scope,
    )


def _execute(
    tmp_path: Path,
    *,
    case: AssuranceCase | None = None,
    obligations: tuple[ProofObligation, ...] | None = None,
    backend: ProductionBackendQualification | None = None,
    registry: FileSystemReleaseRegistry | None = None,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim_artifact = _artifact(store, "claim")
    registry = registry or FileSystemReleaseRegistry(tmp_path / "production")
    return store, registry, execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=BundleId("bundle-v2"),
        world_id=GlobalWorldId("world-v2"),
        runtime_digest="sha256:v2-runtime",
        created_at="2026-08-25T06:00:00Z",
        valid_until="2026-08-29T10:00:00Z",
        artifact_manifest_id=manifest,
        assurance_case=case or _case(claim_artifact),
        obligations=obligations or _obligations(),
        backend_qualification=backend or _backend(store),
        artifact_store=store,
        production_registry=registry,
    )


def test_production_cutover_publishes_only_after_complete_pass_and_exact_cas(tmp_path: Path) -> None:
    store, registry, outcome = _execute(tmp_path)
    key = ReleaseKey(SEASON, ENTRY, GAMEWEEK)

    assert outcome.report.status is ProductionCutoverStatus.PUBLISHED
    assert outcome.report.release_certificate_status == "PASS"
    assert outcome.report.release_certificate_blockers == ()
    assert outcome.report.cutover_blockers == ()
    assert outcome.report.ready_to_act is True
    assert outcome.report.safe_to_act is True
    assert outcome.release_record.status is ReleaseStatus.PUBLISHED
    assert outcome.release_record.ready_to_act is True
    assert outcome.release_record.safe_to_act is True
    assert registry.current_release_id(key) == outcome.release_record.release_id
    assert registry.read_release(outcome.release_record.release_id or "") == outcome.release_record
    replayed = load_production_cutover_report(
        outcome.report_artifact_id,
        artifact_store=store,
    )
    assert replayed.report_id == outcome.report.report_id


def test_incomplete_constitutional_proof_surface_is_rejected_before_pointer_write(
    tmp_path: Path,
) -> None:
    obligations = _obligations()[1:]
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    with pytest.raises(ValueError, match="proof surface is incomplete"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=BundleId("bundle-v2"),
            world_id=GlobalWorldId("world-v2"),
            runtime_digest="sha256:v2-runtime",
            created_at="2026-08-25T06:00:00Z",
            valid_until=None,
            artifact_manifest_id=manifest,
            assurance_case=_case(claim),
            obligations=obligations,
            backend_qualification=_backend(store),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_missing_required_proof_withholds_and_never_moves_production_pointer(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    missing = sorted(MANDATORY_PRODUCTION_PROOF_IDS)[0]
    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=BundleId("bundle-v2"),
        world_id=GlobalWorldId("world-v2"),
        runtime_digest="sha256:v2-runtime",
        created_at="2026-08-25T06:00:00Z",
        valid_until=None,
        artifact_manifest_id=manifest,
        assurance_case=_case(claim, missing=missing),
        obligations=_obligations(),
        backend_qualification=_backend(store),
        artifact_store=store,
        production_registry=registry,
    )

    assert outcome.report.status is ProductionCutoverStatus.WITHHELD
    assert outcome.report.release_certificate_status == "FAIL"
    assert any(missing in blocker for blocker in outcome.report.release_certificate_blockers)
    assert outcome.report.ready_to_act is False
    assert outcome.report.safe_to_act is False
    assert outcome.release_record.status is ReleaseStatus.WITHHELD
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_unqualified_backend_withholds_even_when_release_certificate_passes(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    registry = FileSystemReleaseRegistry(tmp_path / "production")
    outcome = execute_production_cutover(
        season=SEASON,
        entry=ENTRY,
        gameweek=GAMEWEEK,
        bundle_id=BundleId("bundle-v2"),
        world_id=GlobalWorldId("world-v2"),
        runtime_digest="sha256:v2-runtime",
        created_at="2026-08-25T06:00:00Z",
        valid_until=None,
        artifact_manifest_id=manifest,
        assurance_case=_case(claim),
        obligations=_obligations(),
        backend_qualification=_backend(store, qualified=False),
        artifact_store=store,
        production_registry=registry,
    )

    assert outcome.report.release_certificate_status == "PASS"
    assert outcome.report.status is ProductionCutoverStatus.WITHHELD
    assert outcome.report.cutover_blockers == (
        "production ArtifactStore/ReleaseRegistry control plane is not qualified",
    )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


class _StaleRegistry(FileSystemReleaseRegistry):
    def compare_and_swap_current(self, key, *, expected_release_id, new_release_id):
        raise CompareAndSwapConflict("synthetic stale production writer")


def test_stale_writer_fails_closed_and_cannot_become_current(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    registry = _StaleRegistry(tmp_path / "production")
    with pytest.raises(CompareAndSwapConflict, match="stale production"):
        execute_production_cutover(
            season=SEASON,
            entry=ENTRY,
            gameweek=GAMEWEEK,
            bundle_id=BundleId("bundle-v2"),
            world_id=GlobalWorldId("world-v2"),
            runtime_digest="sha256:v2-runtime",
            created_at="2026-08-25T06:00:00Z",
            valid_until=None,
            artifact_manifest_id=manifest,
            assurance_case=_case(claim),
            obligations=_obligations(),
            backend_qualification=_backend(store),
            artifact_store=store,
            production_registry=registry,
        )
    assert registry.current_release_id(ReleaseKey(SEASON, ENTRY, GAMEWEEK)) is None


def test_production_replay_rejects_lost_or_corrupt_source_evidence(tmp_path: Path) -> None:
    store, _, outcome = _execute(tmp_path)
    source_id = outcome.report.backend_qualification_artifact_ids[0]
    digest = source_id.split(":", 1)[1]
    object_path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    object_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="production replay source"):
        load_production_cutover_report(
            outcome.report_artifact_id,
            artifact_store=store,
        )


def test_release_registry_read_rejects_tampered_release_bytes(tmp_path: Path) -> None:
    _, registry, outcome = _execute(tmp_path)
    release_id = outcome.release_record.release_id
    assert release_id is not None
    path = tmp_path / "production" / "releases" / f"{release_id}.json"
    path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="declared identity mismatch"):
        registry.read_release(release_id)
