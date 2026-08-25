"""Release binding for the mandatory receding-horizon reference-solver parity proof."""

from __future__ import annotations

from apex_fpl.assurance.planning_solver_parity import validate_planning_reference_solver_parity
from apex_fpl.assurance.reference_solver_planning_exchange import (
    load_planning_reference_solver_certificate,
)
from apex_fpl.assurance.worker_authorization import load_reference_solver_authorization
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.production_planning_bundle import VerifiedProductionPlanningBundle
from apex_fpl.core.assurance import AssuranceParityStatus
from apex_fpl.core.proofs import AssuranceClaim


REFERENCE_SOLVER_PARITY_PROOF_ID = "PO-REFERENCE-SOLVER-PARITY-001"


def claim_has_matching_planning_reference_solver_parity(
    claim: AssuranceClaim,
    *,
    verified_bundle: VerifiedProductionPlanningBundle,
    store: ArtifactStore,
) -> bool:
    """Require exact planning parity plus replayed qualified-champion authorization.

    Generic algorithmic artifacts are insufficient. The certificate must derive from
    retained planning worker I/O, match the exact production planning result, and be
    authorized by a replay-valid champion registry whose qualification covers the same
    season, decision cutoff, and horizon.
    """

    if claim.proof_id != REFERENCE_SOLVER_PARITY_PROOF_ID:
        return False
    result = verified_bundle.decision
    policy = verified_bundle.decision_policy
    evidence_ids = set(claim.evidence_ids)
    expected_result_id = str(result.planning_result_id)
    if expected_result_id not in evidence_ids:
        return False

    for artifact_id in claim.artifact_ids:
        try:
            stored_certificate = load_planning_reference_solver_certificate(
                artifact_id,
                store=store,
            )
        except (FileNotFoundError, ValueError):
            continue
        certificate = stored_certificate.certificate
        if str(certificate.certificate_id) not in evidence_ids:
            continue
        status, blockers = validate_planning_reference_solver_parity(
            result,
            certificate,
            store=store,
            expected_tie_break_policy_id=policy.tie_break_policy,
        )
        if status is not AssuranceParityStatus.PASS or blockers:
            continue

        for authorization_artifact_id in claim.artifact_ids:
            if authorization_artifact_id == artifact_id:
                continue
            try:
                stored_authorization = load_reference_solver_authorization(
                    authorization_artifact_id,
                    certificate=certificate,
                    store=store,
                )
            except (FileNotFoundError, ValueError):
                continue
            authorization = stored_authorization.authorization
            if authorization.authorization_id not in evidence_ids:
                continue
            if authorization.season != verified_bundle.bundle.season:
                continue
            if authorization.decision_cutoff != verified_bundle.forecast.feature_cutoff:
                continue
            if authorization.horizon_gameweeks != policy.horizon_gameweeks:
                continue
            if authorization.solver_certificate_id != certificate.certificate_id:
                continue
            return True
    return False
