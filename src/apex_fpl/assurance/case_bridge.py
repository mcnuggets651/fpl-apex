"""Bridge replay-verified Slice 10 evidence into the constitutional AssuranceCase."""

from __future__ import annotations

from apex_fpl.assurance.replay_verification import VerifiedIndependentAssuranceEvidence
from apex_fpl.core.assurance import AssuranceParityStatus
from apex_fpl.core.proofs import AssuranceClaim, ProofStatus


MECHANICS_PROOF_ID = "PO-MECHANICS-RECONCILIATION-001"
SOLVER_PARITY_PROOF_ID = "PO-REFERENCE-SOLVER-PARITY-001"


def claims_from_independent_assurance(
    verified: VerifiedIndependentAssuranceEvidence,
) -> tuple[AssuranceClaim, AssuranceClaim]:
    """Translate only replay-verified assurance outcomes without status promotion."""

    stored = verified.stored_report
    report = stored.report
    mechanics_status = ProofStatus.PROVEN if report.mechanics_passed else ProofStatus.FAILED
    if report.solver_parity_status is AssuranceParityStatus.PASS:
        if verified.solver_authorization is None:
            raise ValueError("solver PASS cannot enter AssuranceCase without verified authorization")
        solver_status = ProofStatus.PROVEN
    elif report.solver_parity_status is AssuranceParityStatus.FAIL:
        solver_status = ProofStatus.FAILED
    else:
        solver_status = ProofStatus.INCONCLUSIVE

    mechanics = AssuranceClaim(
        proof_id=MECHANICS_PROOF_ID,
        status=mechanics_status,
        evidence_ids=(str(report.mechanics_certificate_id),),
        artifact_ids=(
            stored.mechanics_certificate_artifact_id,
            stored.artifact_id,
        ),
        reason=None if report.mechanics_passed else "; ".join(report.blockers),
    )
    solver_artifacts = (
        (stored.artifact_id,)
        if stored.solver_certificate_artifact_id is None
        else (stored.solver_certificate_artifact_id, stored.artifact_id)
    )
    if verified.solver_authorization is not None:
        solver_artifacts = solver_artifacts + (verified.solver_authorization.artifact_id,)
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
