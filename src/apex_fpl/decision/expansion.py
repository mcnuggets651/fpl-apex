"""Candidate-universe expansion certification for Apex V2 decisions."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import (
    CandidateExpansionCertificate,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionResult,
    ExactnessClaim,
    ExactnessStatus,
    ExpansionResult,
    RationalValue,
    SolverStatus,
)


def _fraction(value: RationalValue) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _rational(value: Fraction) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


def _same_decision_policy(baseline: DecisionResult, expanded: DecisionResult) -> None:
    left = baseline.decision_input
    right = expanded.decision_input
    comparable = (
        "manager_state_id",
        "forecast_id",
        "ruleset_id",
        "gameweek",
        "use_mode",
        "objective_model",
        "max_normal_transfers",
        "chips_considered",
        "numeric_policy_id",
    )
    mismatches = [
        name for name in comparable if getattr(left, name) != getattr(right, name)
    ]
    if mismatches:
        raise ValueError(
            "candidate expansion changed decision policy/state: "
            + ",".join(mismatches)
        )


def certify_candidate_expansion(
    *,
    baseline: DecisionResult,
    expanded: DecisionResult,
    baseline_universe: CandidateUniverse,
    expanded_universe: CandidateUniverse,
    materiality_threshold: RationalValue,
    store: ArtifactStore,
) -> tuple[CandidateExpansionCertificate, str, DecisionResult]:
    """Compare a scoped result with a strict expansion and promote only if certified.

    A scoped universe can become ``OPTIMAL_WITHIN_CERTIFIED_UNIVERSE`` only when the
    expanded solve covers the complete Official pool, is itself GLOBAL_OPTIMAL under
    the same action/policy surface, and does not improve the objective beyond the
    explicit materiality threshold. Any material improvement leaves the baseline
    unpromoted and records a SEARCH DEFECT signal.
    """

    if baseline_universe.scope is not CandidateUniverseScope.SCOPED:
        raise ValueError("candidate expansion baseline must be SCOPED")
    if baseline.decision_input.candidate_universe_id != baseline_universe.candidate_universe_id:
        raise ValueError("baseline decision/universe identity mismatch")
    if expanded.decision_input.candidate_universe_id != expanded_universe.candidate_universe_id:
        raise ValueError("expanded decision/universe identity mismatch")
    if baseline_universe.global_world_id != expanded_universe.global_world_id:
        raise ValueError("candidate expansion must use the same GlobalWorld")
    baseline_ids = {row.player_id for row in baseline_universe.players}
    expanded_ids = {row.player_id for row in expanded_universe.players}
    if not baseline_ids < expanded_ids:
        raise ValueError("expanded candidate universe must be a strict superset")
    _same_decision_policy(baseline, expanded)
    if baseline.solver.status is not SolverStatus.OPTIMAL:
        raise ValueError("baseline expansion audit requires an OPTIMAL scoped solve")
    if not baseline.exactness.search_complete or not baseline.exactness.action_surface_complete:
        raise ValueError("baseline expansion audit requires complete scoped search/action surface")
    if expanded.exactness.status is not ExactnessStatus.GLOBAL_OPTIMAL:
        raise ValueError("certifying expansion must itself be GLOBAL_OPTIMAL")
    if expanded_universe.scope is not CandidateUniverseScope.FULL_OFFICIAL:
        raise ValueError("certifying expansion must cover FULL_OFFICIAL universe")
    if materiality_threshold.numerator < 0:
        raise ValueError("candidate expansion materiality threshold cannot be negative")

    baseline_objective = baseline.selected_action.mechanics.objective_points
    expanded_objective = expanded.selected_action.mechanics.objective_points
    improvement = _fraction(expanded_objective) - _fraction(baseline_objective)
    threshold = _fraction(materiality_threshold)
    result = (
        ExpansionResult.MATERIAL_IMPROVEMENT_FOUND
        if improvement > threshold
        else ExpansionResult.NO_MATERIAL_IMPROVEMENT
    )

    audit_payload = {
        "schema_name": "apex-candidate-expansion-audit-input",
        "schema_version": 1,
        "baseline_decision_id": str(baseline.decision_id),
        "expanded_decision_id": str(expanded.decision_id),
        "baseline_universe_id": str(baseline_universe.candidate_universe_id),
        "expanded_universe_id": str(expanded_universe.candidate_universe_id),
        "materiality_threshold": materiality_threshold.semantic_payload(),
        "objective_improvement": _rational(improvement).semantic_payload(),
    }
    audit_ref = store.put_bytes(
        canonical_json_bytes(audit_payload),
        media_type="application/json",
        schema_name="apex-candidate-expansion-audit-input",
        schema_version="1",
    )
    certificate = CandidateExpansionCertificate(
        baseline_universe_id=baseline_universe.candidate_universe_id,
        expanded_universe_id=expanded_universe.candidate_universe_id,
        expanded_universe_scope=expanded_universe.scope,
        baseline_objective=baseline_objective,
        expanded_objective=expanded_objective,
        materiality_threshold=materiality_threshold,
        result=result,
        expanded_exactness_status=expanded.exactness.status,
        source_artifact_id=audit_ref.artifact_id,
    )
    certificate_ref = store.put_bytes(
        canonical_json_bytes(certificate.semantic_payload()),
        media_type="application/json",
        schema_name="apex-candidate-expansion-certificate",
        schema_version="1",
    )

    if not certificate.certifies_baseline_universe:
        return certificate, certificate_ref.artifact_id, baseline

    promoted_exactness = ExactnessClaim(
        status=ExactnessStatus.OPTIMAL_WITHIN_CERTIFIED_UNIVERSE,
        candidate_universe_id=baseline_universe.candidate_universe_id,
        universe_scope=baseline_universe.scope,
        solver_status=baseline.solver.status,
        action_surface_complete=baseline.exactness.action_surface_complete,
        search_complete=baseline.exactness.search_complete,
        best_bound=baseline.exactness.best_bound,
        gap=baseline.exactness.gap,
        filter_identity=baseline_universe.filter_identity,
        expansion_result=certificate.result,
        expansion_certificate_id=certificate_ref.artifact_id,
        numeric_error_bound=baseline.exactness.numeric_error_bound,
        reasons=(),
    )
    promoted = replace(baseline, exactness=promoted_exactness)
    return certificate, certificate_ref.artifact_id, promoted
