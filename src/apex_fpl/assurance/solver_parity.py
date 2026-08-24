"""Fail-closed validation of sealed external reference-solver evidence."""

from __future__ import annotations

from apex_fpl.assurance.worker_authorization import create_reference_solver_authorization
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.reference_solver_registry import ReferenceSolverRegistry
from apex_fpl.core.assurance import (
    AssuranceParityStatus,
    IndependentAssuranceReport,
    ReferenceMechanicsCertificate,
    ReferenceSolverCertificate,
    ReferenceSolverStatus,
)
from apex_fpl.core.decision import DecisionResult, RationalValue


def _compare(left: RationalValue, right: RationalValue) -> int:
    delta = left.numerator * right.denominator - right.numerator * left.denominator
    return (delta > 0) - (delta < 0)


def validate_reference_solver_parity(
    result: DecisionResult,
    certificate: ReferenceSolverCertificate,
    *,
    store: ArtifactStore,
    expected_tie_break_policy_id: str | None = None,
) -> tuple[AssuranceParityStatus, tuple[str, ...]]:
    """Validate an untrusted worker certificate against one exact DecisionResult."""

    blockers: list[str] = []
    if certificate.decision_input_id != result.decision_input.decision_input_id:
        blockers.append("reference solver DecisionInputId mismatch")
    if certificate.candidate_universe_id != result.decision_input.candidate_universe_id:
        blockers.append("reference solver CandidateUniverseId mismatch")
    if certificate.decision_policy_id != result.decision_input.decision_policy_id:
        blockers.append("reference solver DecisionPolicyId mismatch")
    for artifact_id in (
        certificate.solver_input_artifact_id,
        certificate.solver_output_artifact_id,
        certificate.worker_artifact_id,
    ):
        try:
            store.read_bytes(artifact_id)
        except FileNotFoundError:
            blockers.append(f"reference solver artifact missing: {artifact_id}")
    if blockers:
        return AssuranceParityStatus.FAIL, tuple(blockers)

    if certificate.solver_status is ReferenceSolverStatus.INFEASIBLE:
        return (
            AssuranceParityStatus.FAIL,
            ("reference solver claims infeasible while Apex returned a feasible action",),
        )
    if certificate.solver_status in {
        ReferenceSolverStatus.ERROR,
        ReferenceSolverStatus.SOLVER_LIMIT,
        ReferenceSolverStatus.FEASIBLE,
    }:
        return (
            AssuranceParityStatus.INCONCLUSIVE,
            (f"reference solver ended {certificate.solver_status.value}",),
        )
    if certificate.solver_status is not ReferenceSolverStatus.OPTIMAL:
        return AssuranceParityStatus.INCONCLUSIVE, ("reference solver status is not certifying",)

    if certificate.best_objective is None:
        return AssuranceParityStatus.FAIL, ("OPTIMAL reference solver lacks objective",)
    apex_objective = result.selected_action.mechanics.objective_points
    objective_cmp = _compare(certificate.best_objective, apex_objective)
    if objective_cmp != 0:
        relation = "higher" if objective_cmp > 0 else "lower"
        return (
            AssuranceParityStatus.FAIL,
            (
                "reference optimum is "
                f"{relation} than Apex selected objective: "
                f"reference={certificate.best_objective.numerator}/{certificate.best_objective.denominator} "
                f"apex={apex_objective.numerator}/{apex_objective.denominator}",
            ),
        )

    if (
        expected_tie_break_policy_id is not None
        and certificate.tie_break_policy_id == expected_tie_break_policy_id
        and certificate.selected_action_id is not None
        and certificate.selected_action_id != result.selected_action.action_id
    ):
        return (
            AssuranceParityStatus.FAIL,
            ("reference solver claims same tie policy but selected action identity differs",),
        )
    return AssuranceParityStatus.PASS, ()


def build_independent_assurance_report(
    result: DecisionResult,
    mechanics: ReferenceMechanicsCertificate,
    *,
    store: ArtifactStore,
    solver: ReferenceSolverCertificate | None = None,
    worker_registry: ReferenceSolverRegistry | None = None,
    worker_registry_artifact_id: str | None = None,
    season: str | None = None,
    decision_cutoff: str | None = None,
    horizon_gameweeks: int | None = None,
    expected_tie_break_policy_id: str | None = None,
) -> IndependentAssuranceReport:
    """Build publication-grade assurance without converting missing qualification to PASS.

    Raw parity may be inspected with :func:`validate_reference_solver_parity`. A final
    assurance report can reach PASS only after the certificate is matched to retained
    registry authority proving the artifact-verified, season/horizon-valid qualified
    champion. If no registry artifact is supplied, the exact in-memory registry authority
    is first sealed as a canonical semantic snapshot. The resulting authorization artifact
    is part of report source lineage and is replayable.
    """

    blockers: list[str] = []
    if mechanics.decision_id != result.decision_id:
        blockers.append("reference mechanics DecisionId mismatch")
    if mechanics.decision_input_id != result.decision_input.decision_input_id:
        blockers.append("reference mechanics DecisionInputId mismatch")
    if mechanics.action_id != result.selected_action.action_id:
        blockers.append("reference mechanics action identity mismatch")
    for artifact_id in mechanics.source_artifact_ids:
        try:
            store.read_bytes(artifact_id)
        except FileNotFoundError:
            blockers.append(f"reference mechanics source artifact missing: {artifact_id}")
    mechanics_passed = mechanics.passed and not blockers

    if solver is None:
        parity_status = AssuranceParityStatus.INCONCLUSIVE
        blockers.append("independent solver certificate is absent")
        solver_id = None
        solver_artifacts: tuple[str, ...] = ()
    else:
        parity_status, solver_blockers = validate_reference_solver_parity(
            result,
            solver,
            store=store,
            expected_tie_break_policy_id=expected_tie_break_policy_id,
        )
        blockers.extend(solver_blockers)
        solver_id = solver.certificate_id
        solver_artifact_list = [
            solver.solver_input_artifact_id,
            solver.solver_output_artifact_id,
            solver.worker_artifact_id,
        ]
        if parity_status is AssuranceParityStatus.PASS:
            missing_context = []
            if worker_registry is None:
                missing_context.append("qualified reference solver registry")
            if season is None:
                missing_context.append("decision season")
            if decision_cutoff is None:
                missing_context.append("decision cutoff")
            if horizon_gameweeks is None:
                missing_context.append("decision horizon")
            if missing_context:
                parity_status = AssuranceParityStatus.INCONCLUSIVE
                blockers.append(
                    "reference solver parity lacks production worker qualification context: "
                    + ", ".join(missing_context)
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
                        f"reference solver worker is not production-qualified: {exc}"
                    )
                else:
                    solver_artifact_list.extend(
                        (
                            authorization.artifact_id,
                            authorization.authorization.registry_artifact_id,
                            authorization.authorization.worker_code_artifact_id,
                            authorization.authorization.qualification_artifact_id,
                        )
                    )
        solver_artifacts = tuple(sorted(set(solver_artifact_list)))

    source_artifacts = tuple(sorted(set(mechanics.source_artifact_ids) | set(solver_artifacts)))
    return IndependentAssuranceReport(
        decision_id=result.decision_id,
        mechanics_certificate_id=mechanics.certificate_id,
        mechanics_passed=mechanics_passed,
        solver_certificate_id=solver_id,
        solver_parity_status=parity_status,
        blockers=tuple(dict.fromkeys(blockers)),
        source_artifact_ids=source_artifacts,
    )
