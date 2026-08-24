"""Bridge independent Slice 10 evidence into the constitutional AssuranceCase."""

from __future__ import annotations

from apex_fpl.core.assurance import AssuranceParityStatus, IndependentAssuranceReport
from apex_fpl.core.proofs import AssuranceClaim, ProofStatus


MECHANICS_PROOF_ID = "PO-MECHANICS-RECONCILIATION-001"
SOLVER_PARITY_PROOF_ID = "PO-REFERENCE-SOLVER-PARITY-001"


def claims_from_independent_assurance(
    report: IndependentAssuranceReport,
    *,
    report_artifact_id: str,
    mechanics_certificate_artifact_id: str,
    solver_certificate_artifact_id: str | None,
) -> tuple[AssuranceClaim, AssuranceClaim]:
    """Translate typed assurance outcomes without upgrading inconclusive evidence."""

    mechanics_status = ProofStatus.PROVEN if report.mechanics_passed else ProofStatus.FAILED
    if report.solver_parity_status is AssuranceParityStatus.PASS:
        solver_status = ProofStatus.PROVEN
    elif report.solver_parity_status is AssuranceParityStatus.FAIL:
        solver_status = ProofStatus.FAILED
    else:
        solver_status = ProofStatus.INCONCLUSIVE

    mechanics = AssuranceClaim(
        proof_id=MECHANICS_PROOF_ID,
        status=mechanics_status,
        evidence_ids=(str(report.mechanics_certificate_id),),
        artifact_ids=(mechanics_certificate_artifact_id, report_artifact_id),
        reason=None if report.mechanics_passed else "; ".join(report.blockers),
    )
    solver_artifacts = (
        (report_artifact_id,)
        if solver_certificate_artifact_id is None
        else (solver_certificate_artifact_id, report_artifact_id)
    )
    solver = AssuranceClaim(
        proof_id=SOLVER_PARITY_PROOF_ID,
        status=solver_status,
        evidence_ids=(
            ()
            if report.solver_certificate_id is None
            else (str(report.solver_certificate_id),)
        ),
        artifact_ids=solver_artifacts,
        reason=(
            None
            if report.solver_parity_status is AssuranceParityStatus.PASS
            else "; ".join(report.blockers)
        ),
    )
    return mechanics, solver
