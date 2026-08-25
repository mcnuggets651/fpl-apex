from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    FileSystemReleaseRegistry,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)
from apex_fpl.control.shadow_production import (
    execute_shadow_production,
    load_shadow_production_report,
)
from apex_fpl.core.ids import BundleId, GlobalWorldId
from apex_fpl.core.proofs import (
    AssuranceCase,
    AssuranceClaim,
    ProofClass,
    ProofObligation,
    ProofStatus,
    ReleasePolicy,
)
from apex_fpl.core.shadow import ShadowProductionStatus


def _artifact(store: FileSystemArtifactStore, value: str) -> str:
    return store.put_bytes(value.encode("utf-8")).artifact_id


def _obligation() -> ProofObligation:
    return ProofObligation(
        proof_id="PO-SHADOW-SYNTHETIC-001",
        claim="synthetic shadow prerequisite",
        proof_class=ProofClass.FORMAL_INVARIANT,
        scope="shadow",
        required_evidence=("synthetic",),
        required_tests=("test_shadow",),
        failure_consequence="withhold shadow release",
        release_policy=ReleasePolicy.REQUIRED,
        owner="tests",
    )


def _case(claim_artifact: str | None, *, proven: bool = True) -> AssuranceCase:
    claims = ()
    if claim_artifact is not None:
        claims = (
            AssuranceClaim(
                proof_id="PO-SHADOW-SYNTHETIC-001",
                status=ProofStatus.PROVEN if proven else ProofStatus.INCONCLUSIVE,
                evidence_ids=("synthetic-evidence",),
                test_ids=("test_shadow",),
                artifact_ids=(claim_artifact,),
            ),
        )
    return AssuranceCase(release_scope="2026-2027:63984:1:shadow", claims=claims)


def _production_record(manifest: str) -> ReleaseRecord:
    return ReleaseRecord(
        season="2026-2027",
        entry=63984,
        gameweek=1,
        bundle_id="production-bundle",
        world_id="production-world",
        runtime_digest="sha256:production-runtime",
        created_at=datetime(2026, 8, 25, tzinfo=timezone.utc).isoformat(),
        valid_until=None,
        status=ReleaseStatus.PUBLISHED,
        ready_to_act=True,
        safe_to_act=True,
        artifact_manifest_id=manifest,
    )


def _seed_production(registry: FileSystemReleaseRegistry, manifest: str) -> str:
    record = registry.append(_production_record(manifest))
    assert record.release_id is not None
    key = ReleaseKey("2026-2027", 63984, 1)
    registry.compare_and_swap_current(
        key,
        expected_release_id=None,
        new_release_id=record.release_id,
    )
    return record.release_id


def test_passing_shadow_rehearsal_is_certified_but_never_actionable(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    production = FileSystemReleaseRegistry(tmp_path / "production")
    shadow = FileSystemReleaseRegistry(tmp_path / "shadow")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    production_id = _seed_production(production, manifest)

    outcome = execute_shadow_production(
        season="2026-2027",
        entry=63984,
        gameweek=1,
        bundle_id=BundleId("bundle-v2"),
        world_id=GlobalWorldId("world-v2"),
        runtime_digest="sha256:v2-runtime",
        created_at="2026-08-25T05:00:00Z",
        valid_until=None,
        artifact_manifest_id=manifest,
        assurance_case=_case(claim),
        obligations=(_obligation(),),
        artifact_store=store,
        shadow_registry=shadow,
        production_reader=production,
    )

    key = ReleaseKey("2026-2027", 63984, 1)
    assert outcome.report.status is ShadowProductionStatus.PASS
    assert outcome.report.release_certificate_status == "PASS"
    assert outcome.release_record.status is ReleaseStatus.CERTIFIED
    assert outcome.release_record.ready_to_act is False
    assert outcome.release_record.safe_to_act is False
    assert production.current_release_id(key) == production_id
    assert shadow.current_release_id(key) == outcome.release_record.release_id
    assert outcome.report.production_pointer_before == production_id
    assert outcome.report.production_pointer_after == production_id
    assert load_shadow_production_report(
        outcome.report_artifact_id,
        artifact_store=store,
    ).report_id == outcome.report.report_id


def test_missing_required_proof_produces_withheld_non_actionable_shadow_release(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    production = FileSystemReleaseRegistry(tmp_path / "production")
    shadow = FileSystemReleaseRegistry(tmp_path / "shadow")
    manifest = _artifact(store, "manifest")

    outcome = execute_shadow_production(
        season="2026-2027",
        entry=63984,
        gameweek=1,
        bundle_id=None,
        world_id=None,
        runtime_digest="sha256:v2-runtime",
        created_at="2026-08-25T05:00:00Z",
        valid_until=None,
        artifact_manifest_id=manifest,
        assurance_case=_case(None),
        obligations=(_obligation(),),
        artifact_store=store,
        shadow_registry=shadow,
        production_reader=production,
    )

    assert outcome.report.status is ShadowProductionStatus.WITHHELD
    assert outcome.report.release_certificate_status == "FAIL"
    assert any("missing required proof" in item for item in outcome.report.release_certificate_blockers)
    assert outcome.release_record.status is ReleaseStatus.WITHHELD
    assert outcome.release_record.ready_to_act is False
    assert outcome.release_record.safe_to_act is False


def test_missing_or_corrupt_assurance_artifact_fails_before_shadow_release(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    production = FileSystemReleaseRegistry(tmp_path / "production")
    shadow = FileSystemReleaseRegistry(tmp_path / "shadow")
    manifest = _artifact(store, "manifest")
    missing = "sha256:" + "a" * 64

    with pytest.raises(ValueError, match="assurance claim artifact"):
        execute_shadow_production(
            season="2026-2027",
            entry=63984,
            gameweek=1,
            bundle_id=None,
            world_id=None,
            runtime_digest="sha256:v2-runtime",
            created_at="2026-08-25T05:00:00Z",
            valid_until=None,
            artifact_manifest_id=manifest,
            assurance_case=_case(missing),
            obligations=(_obligation(),),
            artifact_store=store,
            shadow_registry=shadow,
            production_reader=production,
        )
    assert shadow.current_release_id(ReleaseKey("2026-2027", 63984, 1)) is None


class _StaleShadowRegistry(FileSystemReleaseRegistry):
    def compare_and_swap_current(self, key, *, expected_release_id, new_release_id):
        raise CompareAndSwapConflict("synthetic stale shadow writer")


def test_shadow_pointer_update_uses_cas_and_stale_writer_fails_closed(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    with pytest.raises(CompareAndSwapConflict, match="stale shadow"):
        execute_shadow_production(
            season="2026-2027",
            entry=63984,
            gameweek=1,
            bundle_id=None,
            world_id=None,
            runtime_digest="sha256:v2-runtime",
            created_at="2026-08-25T05:00:00Z",
            valid_until=None,
            artifact_manifest_id=manifest,
            assurance_case=_case(claim),
            obligations=(_obligation(),),
            artifact_store=store,
            shadow_registry=_StaleShadowRegistry(tmp_path / "shadow"),
            production_reader=FileSystemReleaseRegistry(tmp_path / "production"),
        )


class _DriftingProductionReader:
    def __init__(self) -> None:
        self.calls = 0

    def current_release_id(self, key: ReleaseKey) -> str | None:
        self.calls += 1
        return "prod-a" if self.calls == 1 else "prod-b"


def test_shadow_report_refuses_to_claim_success_if_production_pointer_changes_concurrently(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    with pytest.raises(ValueError, match="must not change production"):
        execute_shadow_production(
            season="2026-2027",
            entry=63984,
            gameweek=1,
            bundle_id=None,
            world_id=None,
            runtime_digest="sha256:v2-runtime",
            created_at="2026-08-25T05:00:00Z",
            valid_until=None,
            artifact_manifest_id=manifest,
            assurance_case=_case(claim),
            obligations=(_obligation(),),
            artifact_store=store,
            shadow_registry=FileSystemReleaseRegistry(tmp_path / "shadow"),
            production_reader=_DriftingProductionReader(),
        )


def test_shadow_replay_rejects_lost_source_evidence(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    outcome = execute_shadow_production(
        season="2026-2027",
        entry=63984,
        gameweek=1,
        bundle_id=None,
        world_id=None,
        runtime_digest="sha256:v2-runtime",
        created_at="2026-08-25T05:00:00Z",
        valid_until=None,
        artifact_manifest_id=manifest,
        assurance_case=_case(claim),
        obligations=(_obligation(),),
        artifact_store=store,
        shadow_registry=FileSystemReleaseRegistry(tmp_path / "shadow"),
        production_reader=FileSystemReleaseRegistry(tmp_path / "production"),
    )
    digest = claim.split(":", 1)[1]
    object_path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    object_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="shadow replay source artifact"):
        load_shadow_production_report(outcome.report_artifact_id, artifact_store=store)
