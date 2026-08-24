from __future__ import annotations

from pathlib import Path

from apex_fpl.assurance.case_bridge import claims_from_independent_assurance
from apex_fpl.control.proof_registry import ProofRegistry
from apex_fpl.core.assurance import AssuranceParityStatus, IndependentAssuranceReport
from apex_fpl.core.ids import (
    DecisionId,
    ReferenceMechanicsCertificateId,
    ReferenceSolverCertificateId,
)
from apex_fpl.core.proofs import AssuranceCase, ProofStatus


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "sha256:" + "a" * 64


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


def _claims(report: IndependentAssuranceReport):
    return claims_from_independent_assurance(
        report,
        report_artifact_id="sha256:" + "b" * 64,
        mechanics_certificate_artifact_id="sha256:" + "c" * 64,
        solver_certificate_artifact_id=(
            None if report.solver_certificate_id is None else "sha256:" + "d" * 64
        ),
    )


def test_assurance_case_bridge_never_upgrades_inconclusive_solver_evidence() -> None:
    mechanics, solver = _claims(_report(AssuranceParityStatus.INCONCLUSIVE))
    assert mechanics.status is ProofStatus.PROVEN
    assert solver.status is ProofStatus.INCONCLUSIVE


def test_assurance_case_bridge_maps_exact_pass_and_fail_statuses() -> None:
    mechanics, solver = _claims(_report(AssuranceParityStatus.PASS))
    assert mechanics.status is ProofStatus.PROVEN
    assert solver.status is ProofStatus.PROVEN

    failed_mechanics, failed_solver = _claims(
        _report(AssuranceParityStatus.FAIL, mechanics_passed=False)
    )
    assert failed_mechanics.status is ProofStatus.FAILED
    assert failed_solver.status is ProofStatus.FAILED


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
