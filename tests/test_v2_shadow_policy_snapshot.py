from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.release_registry import FileSystemReleaseRegistry
from apex_fpl.control.shadow_production import execute_shadow_production, load_shadow_production_report
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.proofs import AssuranceCase, AssuranceClaim, ProofClass, ProofObligation, ProofStatus, ReleasePolicy


def _artifact(store: FileSystemArtifactStore, value: str) -> str:
    return store.put_bytes(value.encode("utf-8")).artifact_id


def _obligation(proof_id: str = "PO-SNAPSHOT-001") -> ProofObligation:
    return ProofObligation(
        proof_id=proof_id,
        claim="snapshot proof",
        proof_class=ProofClass.FORMAL_INVARIANT,
        scope="shadow",
        required_evidence=("snapshot",),
        required_tests=("test_snapshot",),
        failure_consequence="withhold",
        release_policy=ReleasePolicy.REQUIRED,
        owner="tests",
    )


def _case(claim_artifact: str, *, reason: str | None = None) -> AssuranceCase:
    return AssuranceCase(
        release_scope="2026-2027:63984:1:shadow",
        claims=(
            AssuranceClaim(
                proof_id="PO-SNAPSHOT-001",
                status=ProofStatus.PROVEN,
                evidence_ids=("snapshot-evidence",),
                test_ids=("test_snapshot",),
                artifact_ids=(claim_artifact,),
                reason=reason,
            ),
        ),
    )


def _run(tmp_path: Path, *, reason: str | None = None):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    outcome = execute_shadow_production(
        season="2026-2027",
        entry=63984,
        gameweek=1,
        bundle_id=None,
        world_id=None,
        runtime_digest="sha256:runtime",
        created_at="2026-08-25T05:00:00Z",
        valid_until=None,
        artifact_manifest_id=manifest,
        assurance_case=_case(claim, reason=reason),
        obligations=(_obligation(),),
        artifact_store=store,
        shadow_registry=FileSystemReleaseRegistry(tmp_path / "shadow"),
        production_reader=FileSystemReleaseRegistry(tmp_path / "production"),
    )
    return store, outcome


def test_assurance_case_semantic_payload_preserves_historical_case_id_shape(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    case = _case(_artifact(store, "claim"), reason="retained reason")
    historical_payload = {
        "release_scope": case.release_scope,
        "claims": [claim.semantic_payload() for claim in case.claims],
    }
    assert case.semantic_payload() == historical_payload
    assert case.case_id == canonical_sha256(historical_payload)


def test_shadow_replay_rederives_release_certificate_from_exact_retained_policy(tmp_path: Path) -> None:
    store, outcome = _run(tmp_path, reason="qualification retained")
    replayed = load_shadow_production_report(outcome.report_artifact_id, artifact_store=store)
    assert replayed.assurance_case_artifact_id == outcome.report.assurance_case_artifact_id
    assert replayed.proof_obligations_artifact_id == outcome.report.proof_obligations_artifact_id
    assert replayed.assurance_case_id == outcome.report.assurance_case_id
    assert replayed.release_certificate_status == "PASS"
    assert replayed.release_certificate_blockers == ()


def test_duplicate_shadow_proof_ids_are_rejected_before_release(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    claim = _artifact(store, "claim")
    obligation = _obligation()
    with pytest.raises(ValueError, match="duplicate proof_id"):
        execute_shadow_production(
            season="2026-2027",
            entry=63984,
            gameweek=1,
            bundle_id=None,
            world_id=None,
            runtime_digest="sha256:runtime",
            created_at="2026-08-25T05:00:00Z",
            valid_until=None,
            artifact_manifest_id=manifest,
            assurance_case=_case(claim),
            obligations=(obligation, obligation),
            artifact_store=store,
            shadow_registry=FileSystemReleaseRegistry(tmp_path / "shadow"),
            production_reader=FileSystemReleaseRegistry(tmp_path / "production"),
        )


def test_shadow_release_and_replay_use_same_canonical_proof_order(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    manifest = _artifact(store, "manifest")
    outcome = execute_shadow_production(
        season="2026-2027",
        entry=63984,
        gameweek=1,
        bundle_id=None,
        world_id=None,
        runtime_digest="sha256:runtime",
        created_at="2026-08-25T05:00:00Z",
        valid_until=None,
        artifact_manifest_id=manifest,
        assurance_case=AssuranceCase(
            release_scope="2026-2027:63984:1:shadow",
            claims=(),
        ),
        obligations=(_obligation("PO-Z-001"), _obligation("PO-A-001")),
        artifact_store=store,
        shadow_registry=FileSystemReleaseRegistry(tmp_path / "shadow"),
        production_reader=FileSystemReleaseRegistry(tmp_path / "production"),
    )
    assert outcome.report.release_certificate_status == "FAIL"
    assert outcome.report.release_certificate_blockers == (
        "missing required proof: PO-A-001",
        "missing required proof: PO-Z-001",
    )
    replayed = load_shadow_production_report(outcome.report_artifact_id, artifact_store=store)
    assert replayed.release_certificate_blockers == outcome.report.release_certificate_blockers


def test_shadow_replay_fails_if_retained_proof_policy_snapshot_is_lost(tmp_path: Path) -> None:
    store, outcome = _run(tmp_path)
    digest = outcome.report.proof_obligations_artifact_id.split(":", 1)[1]
    object_path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    object_path.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="shadow replay source artifact"):
        load_shadow_production_report(outcome.report_artifact_id, artifact_store=store)
