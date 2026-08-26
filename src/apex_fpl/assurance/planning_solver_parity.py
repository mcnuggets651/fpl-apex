"""Fail-closed planning parity validation for isolated receding-horizon worker evidence."""

from __future__ import annotations

from apex_fpl.assurance.reference_solver_planning_exchange import (
    verify_planning_reference_solver_certificate_io,
)
from apex_fpl.assurance.worker_authorization import create_reference_solver_authorization
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.reference_solver_registry import ReferenceSolverRegistry
from apex_fpl.core.assurance import (
    AssuranceParityStatus,
    IndependentAssuranceReport,
    ReferenceMechanicsCertificate,
)
from apex_fpl.core.ids import ReferenceSolverCertificateId
from apex_fpl.core.planning import RecedingHorizonDecisionResult
from apex_fpl.core.reference_solver_planning_assurance import PlanningReferenceSolverCertificate
from apex_fpl.core.reference_solver_planning_io import PlanningReferenceSolverStatus


def _compare(left, right) -> int:
    delta = left.numerator * right.denominator - right.numerator * left.denominator
    return (delta > 0) - (delta < 0)


def validate_planning_reference_solver_parity(
    result: RecedingHorizonDecisionResult,
    certificate: PlanningReferenceSolverCertificate,
    *,
    store: ArtifactStore,
    expected_tie_break_policy_id: str | None = None,
) -> tuple[AssuranceParityStatus, tuple[str, ...]]:
    """Validate replay-derived planning worker evidence against one exact planning result."""

    blockers: list[str] = []
    if certificate.decision_input_id != result.decision_input.decision_input_id:
        blockers.append("planning reference solver DecisionInputId mismatch")
    if certificate.candidate_universe_id != result.decision_input.candidate_universe_id:
        blockers.append("planning reference solver CandidateUniverseId mismatch")
    if certificate.decision_policy_id != result.decision_input.decision_policy_id:
        blockers.append("planning reference solver DecisionPolicyId mismatch")
    try:
        request, run = verify_planning_reference_solver_certificate_io(certificate, store=store)
    except (FileNotFoundError, ValueError) as exc:
        blockers.append(f"planning reference solver retained I/O failed replay: {exc}")
    else:
        if run.request_id != request.request_id:
            blockers.append("planning reference solver output/request identity mismatch")
        if request.decision_input.get("manager_state_id") != str(
            result.decision_input.manager_state_id
        ):
            blockers.append("planning retained request ManagerStateId mismatch")
        if request.decision_input.get("forecast_id") != str(result.decision_input.forecast_id):
            blockers.append("planning retained request ForecastId mismatch")
    if blockers:
        return AssuranceParityStatus.FAIL, tuple(blockers)

    if certificate.solver_status is PlanningReferenceSolverStatus.INFEASIBLE:
        return (
            AssuranceParityStatus.FAIL,
            ("planning reference solver claims infeasible while Apex returned a trajectory",),
        )
    if certificate.solver_status in {
        PlanningReferenceSolverStatus.ERROR,
        PlanningReferenceSolverStatus.SOLVER_LIMIT,
    }:
        return (
            AssuranceParityStatus.INCONCLUSIVE,
            (f"planning reference solver ended {certificate.solver_status.value}",),
        )
    if certificate.solver_status is not PlanningReferenceSolverStatus.OPTIMAL:
        return AssuranceParityStatus.INCONCLUSIVE, ("planning reference status is not certifying",)
    if not certificate.search_complete:
        return AssuranceParityStatus.INCONCLUSIVE, ("planning reference search is incomplete",)
    if certificate.best_objective is None:
        return AssuranceParityStatus.FAIL, ("OPTIMAL planning reference solver lacks objective",)

    objective_cmp = _compare(certificate.best_objective, result.selection_objective)
    if objective_cmp != 0:
        relation = "higher" if objective_cmp > 0 else "lower"
        return (
            AssuranceParityStatus.FAIL,
            (
                "planning reference optimum is "
                f"{relation} than Apex horizon objective: "
                f"reference={certificate.best_objective.numerator}/"
                f"{certificate.best_objective.denominator} "
                f"apex={result.selection_objective.numerator}/"
                f"{result.selection_objective.denominator}",
            ),
        )
    if certificate.selected_trajectory_id != result.selected_trajectory.trajectory_id:
        return (
            AssuranceParityStatus.FAIL,
            ("planning reference selected trajectory identity differs",),
        )
    if certificate.selected_action_id != result.selected_action.action_id:
        return (
            AssuranceParityStatus.FAIL,
            ("planning reference selected current root action differs",),
        )
    if (
        expected_tie_break_policy_id is not None
        and certificate.tie_break_policy_id != expected_tie_break_policy_id
    ):
        return (
            AssuranceParityStatus.FAIL,
            ("planning reference tie-break policy identity differs",),
        )
    return AssuranceParityStatus.PASS, ()


def build_planning_independent_assurance_report(
    result: RecedingHorizonDecisionResult,
    mechanics: ReferenceMechanicsCertificate,
    *,
    store: ArtifactStore,
    solver: PlanningReferenceSolverCertificate | None = None,
    worker_registry: ReferenceSolverRegistry | None = None,
    worker_registry_artifact_id: str | None = None,
    season: str | None = None,
    decision_cutoff: str | None = None,
    horizon_gameweeks: int | None = None,
    expected_tie_break_policy_id: str | None = None,
) -> IndependentAssuranceReport:
    """Build publication-grade planning assurance; missing worker authority stays inconclusive."""

    blockers: list[str] = []
    if mechanics.decision_id != result.decision_id:
        blockers.append("reference mechanics DecisionId mismatch")
    if mechanics.decision_input_id != result.decision_input.decision_input_id:
        blockers.append("reference mechanics DecisionInputId mismatch")
    if mechanics.action_id != result.selected_action.action_id:
        blockers.append("reference mechanics root action identity mismatch")
    for artifact_id in mechanics.source_artifact_ids:
        try:
            store.read_bytes(artifact_id)
        except FileNotFoundError:
            blockers.append(f"reference mechanics source artifact missing: {artifact_id}")
    mechanics_passed = mechanics.passed and not blockers

    if solver is None:
        parity_status = AssuranceParityStatus.INCONCLUSIVE
        blockers.append("independent planning solver certificate is absent")
        solver_id = None
        solver_artifacts: tuple[str, ...] = ()
    else:
        parity_status, parity_blockers = validate_planning_reference_solver_parity(
            result,
            solver,
            store=store,
            expected_tie_break_policy_id=expected_tie_break_policy_id,
        )
        blockers.extend(parity_blockers)
        solver_id = ReferenceSolverCertificateId(str(solver.certificate_id))
        artifact_list = [
            solver.solver_input_artifact_id,
            solver.solver_output_artifact_id,
            solver.worker_artifact_id,
        ]
        if parity_status is AssuranceParityStatus.PASS:
            missing = []
            if worker_registry is None:
                missing.append("qualified reference solver registry")
            if season is None:
                missing.append("decision season")
            if decision_cutoff is None:
                missing.append("decision cutoff")
            if horizon_gameweeks is None:
                missing.append("decision horizon")
            if missing:
                parity_status = AssuranceParityStatus.INCONCLUSIVE
                blockers.append(
                    "planning solver parity lacks production worker qualification context: "
                    + ", ".join(missing)
                )
            else:
                try:
                    authorization = create_reference_solver_authorization(
                        solver,
                        worker_registry=worker_registry,
                        registry_artifact_id=worker_registry_artifact_id,
                        store=store,
                        season=season,
                        decision_cutoff=decision_cutoff,
                        horizon_gameweeks=horizon_gameweeks,
                    )
                except (FileNotFoundError, ValueError) as exc:
                    parity_status = AssuranceParityStatus.INCONCLUSIVE
                    blockers.append(
                        f"planning reference worker is not production-qualified: {exc}"
                    )
                else:
                    artifact_list.extend(
                        (
                            authorization.artifact_id,
                            authorization.authorization.registry_artifact_id,
                            authorization.authorization.worker_code_artifact_id,
                            authorization.authorization.qualification_artifact_id,
                        )
                    )
        solver_artifacts = tuple(sorted(set(artifact_list)))

    sources = tuple(sorted(set(mechanics.source_artifact_ids) | set(solver_artifacts)))
    return IndependentAssuranceReport(
        decision_id=result.decision_id,
        mechanics_certificate_id=mechanics.certificate_id,
        mechanics_passed=mechanics_passed,
        solver_certificate_id=solver_id,
        solver_parity_status=parity_status,
        blockers=tuple(dict.fromkeys(blockers)),
        source_artifact_ids=sources,
    )
