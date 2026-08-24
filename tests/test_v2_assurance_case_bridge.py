from __future__ import annotations

from pathlib import Path

from apex_fpl.assurance.case_bridge import claims_from_independent_assurance
from apex_fpl.assurance.replay_verification import VerifiedIndependentAssuranceEvidence
from apex_fpl.assurance.store import StoredIndependentAssuranceReport
from apex_fpl.assurance.worker_authorization import StoredReferenceSolverAuthorization
from apex_fpl.control.proof_registry import ProofRegistry
from apex_fpl.core.assurance import AssuranceParityStatus, IndependentAssuranceReport
from apex_fpl.core.ids import (
    DecisionId,
    ReferenceMechanicsCertificateId,
    ReferenceSolverCertificateId,
    ReferenceSolverWorkerId,
)
from apex_fpl.core.proofs import AssuranceCase, ProofStatus
from apex_fpl.core.reference_solver_authorization import ReferenceSolverAuthorization


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "sha256:" + "a" * 64
REPORT_ARTIFACT = "sha256:" + "b" * 64
MECHANICS_ARTIFACT = "sha256:" + "c" * 64
SOLVER_ARTIFACT = "sha256:" + "d" * 64
AUTH_ARTIFACT = "sha256:" + "e" * 64
QUALIFICATION_ARTIFACT = "sha256:" + "f" * 64
REGISTRY_ARTIFACT = "sha256:" + "1" * 64


def _report(status: AssuranceParityStatus, *, mechanics_passed: bool = True):
    solver_id = (
        None
        if status is AssuranceParityStatus.INCONCLUSIVE
        else ReferenceSolverCertificateId("solver-cert")
    )
    blockers = () if status is AssuranceParityStatus.PASS and mechanics_passed else ("blocked",)
    return IndependentAssuranceReport(
        decision_id=DecisionId("bridge-decision"),
        mechanics_certificate_id=ReferenceMechanicsCertificateId("mechanics-cert"),
        mechanics_passed=mechanics_passed,
        solver_certificate_id=solver_id,
        solver_parity_status=status,
        blockers=blockers,
        source_artifact_ids=(SOURCE,),
    )


def _verified(report: IndependentAssuranceReport) -> VerifiedIndependentAssuranceEvidence:
    stored = StoredIndependentAssuranceReport(
        report=report,
        artifact_id=REPORT_ARTIFACT,
        mechanics_certificate_artifact_id=MECHANICS_ARTIFACT,
        solver_certificate_artifact_id=(
            None if report.solver_certificate_id is None else SOLVER_ARTIFACT
        ),
    )
    authorization = None
    if report.solver_parity_status is AssuranceParityStatus.PASS:
        authorization = StoredReferenceSolverAuthorization(
            authorization=ReferenceSolverAuthorization(
                solver_certificate_id=report.solver_certificate_id,
                worker_id=ReferenceSolverWorkerId("bridge-worker"),
                worker_code_artifact_id=SOURCE,
                qualification_artifact_id=QUALIFICATION_ARTIFACT,
                registry_artifact_id=REGISTRY_ARTIFACT,
                season="2026-2027",
                decision_cutoff="2026-08-24T06:00:00Z",
                horizon_gameweeks=1,
            ),
            artifact_id=AUTH_ARTIFACT,
        )
    return VerifiedIndependentAssuranceEvidence(
        stored_report=stored,
        solver_authorization=authorization,
    )


def _claims(report: IndependentAssuranceReport):
    return claims_from_independent_assurance(_verified(report))


def test_assurance_case_bridge_never_upgrades_inconclusive_solver_evidence() -> None:
    mechanics, solver = _claims(_report(AssuranceParityStatus.INCONCLUSIVE))
    assert mechanics.status is ProofStatus.PROVEN
    assert solver.status is ProofStatus.INCONCLUSIVE


def test_assurance_case_bridge_maps_exact_pass_and_fail_statuses() -> None:
    mechanics, solver = _claims(_report(AssuranceParityStatus.PASS))
    assert mechanics.status is ProofStatus.PROVEN
    assert solver.status is ProofStatus.PROVEN
    assert AUTH_ARTIFACT in solver.artifact_ids

    failed_mechanics, failed_solver = _claims(
        _report(AssuranceParityStatus.FAIL, mechanics_passed=False)
    )
    assert failed_mechanics.status is ProofStatus.FAILED
    assert failed_solver.status is ProofStatus.FAILED


def test_solver_pass_cannot_bridge_without_verified_authorization() -> None:
    report = _report(AssuranceParityStatus.PASS)
    stored = StoredIndependentAssuranceReport(
        report=report,
        artifact_id=REPORT_ARTIFACT,
        mechanics_certificate_artifact_id=MECHANICS_ARTIFACT,
        solver_certificate_artifact_id=SOLVER_ARTIFACT,
    )
    verified = VerifiedIndependentAssuranceEvidence(
        stored_report=stored,
        solver_authorization=None,
    )
    try:
        claims_from_independent_assurance(verified)
    except ValueError as exc:
        assert "authorization" in str(exc)
    else:
        raise AssertionError("solver PASS bridged without verified authorization")


def test_missing_solver_parity_claim_blocks_real_release_certificate() -> None:
    registry = ProofRegistry.load(ROOT / "config" / "proof_obligations.yaml")
    relevant = tuple(
        obligation
        for obligation in registry.obligations
        if obligation.proof_id
        in {"PO-MECHANICS-RECONCILIATION-001", "PO-REFERENCE-SOLVER-PARITY-001"}
    )
    claims = _claims(_report(AssuranceParityStatus.INCONCLUSIVE))
    certificate = AssuranceCase(
        release_scope="slice10-test",
        claims=claims,
    ).derive_release_certificate(relevant)
    assert certificate.eligible is False
    assert any("PO-REFERENCE-SOLVER-PARITY-001" in blocker for blocker in certificate.blockers)
