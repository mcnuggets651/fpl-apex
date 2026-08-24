from __future__ import annotations

from dataclasses import replace

import pytest

from apex_fpl.core.decision import (
    CandidateExpansionCertificate,
    CandidateUniverseScope,
    DecisionAction,
    DecisionChip,
    DecisionInput,
    DecisionMechanics,
    DecisionObjectiveModel,
    DecisionResult,
    DecisionUseMode,
    ExactnessClaim,
    ExactnessStatus,
    ExpansionResult,
    RationalValue,
    SolverCertificate,
    SolverStatus,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    CandidateUniverseId,
    DecisionPolicyId,
    ForecastId,
    ManagerStateId,
    RuleSetId,
)


def _mechanics(*, objective: int = 11) -> DecisionMechanics:
    return DecisionMechanics(
        xi_points=RationalValue(10, 1),
        autosub_points=RationalValue(2, 1),
        captain_bonus=RationalValue(3, 1),
        squad_points_if_bench_boost=RationalValue(20, 1),
        points_before_hits=RationalValue(15, 1),
        hit_points=4,
        objective_points=RationalValue(objective, 1),
    )


def _action(*, mechanics: DecisionMechanics | None = None, bank: int = 0) -> DecisionAction:
    ids = tuple(OfficialPlayerId(player_id) for player_id in range(1, 16))
    return DecisionAction(
        chip=DecisionChip.NONE,
        transfers=(),
        squad_ids=ids,
        xi_ids=ids[:11],
        captain_id=ids[0],
        vice_captain_id=ids[1],
        bench_gk_id=ids[11],
        outfield_bench_order=ids[12:],
        bank_after_tenths=bank,
        mechanics=mechanics or _mechanics(),
    )


def _decision_input() -> DecisionInput:
    return DecisionInput(
        manager_state_id=ManagerStateId("state"),
        forecast_id=ForecastId("forecast"),
        ruleset_id=RuleSetId("rules"),
        candidate_universe_id=CandidateUniverseId("universe"),
        decision_policy_id=DecisionPolicyId("policy"),
        gameweek=2,
        use_mode=DecisionUseMode.SHADOW,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=1,
        chips_considered=(DecisionChip.NONE,),
    )


def _solver(objective: int = 11) -> SolverCertificate:
    value = RationalValue(objective, 1)
    return SolverCertificate(
        status=SolverStatus.OPTIMAL,
        incumbent_objective=value,
        best_bound=value,
        gap=RationalValue.zero(),
        numeric_error_bound=RationalValue.zero(),
        message="integrity fixture",
    )


def _exactness(solver: SolverCertificate) -> ExactnessClaim:
    return ExactnessClaim(
        status=ExactnessStatus.FEASIBLE_INCUMBENT,
        candidate_universe_id=CandidateUniverseId("universe"),
        universe_scope=CandidateUniverseScope.SCOPED,
        solver_status=solver.status,
        action_surface_complete=False,
        search_complete=True,
        best_bound=solver.best_bound,
        gap=solver.gap,
        filter_identity="sha256:" + "a" * 64,
        expansion_result=ExpansionResult.NOT_RUN,
        expansion_certificate_id=None,
        numeric_error_bound=solver.numeric_error_bound,
        reasons=("integrity fixture is scoped",),
    )


def _expansion_certificate(
    *,
    baseline: int,
    expanded: int,
    threshold: int,
    result: ExpansionResult,
) -> CandidateExpansionCertificate:
    return CandidateExpansionCertificate(
        baseline_universe_id=CandidateUniverseId("baseline"),
        expanded_universe_id=CandidateUniverseId("expanded"),
        expanded_universe_scope=CandidateUniverseScope.FULL_OFFICIAL,
        baseline_objective=RationalValue(baseline, 1),
        expanded_objective=RationalValue(expanded, 1),
        materiality_threshold=RationalValue(threshold, 1),
        result=result,
        expanded_exactness_status=ExactnessStatus.GLOBAL_OPTIMAL,
        source_artifact_id="sha256:" + "b" * 64,
    )


def test_decision_action_rejects_hit_or_points_arithmetic_laundering() -> None:
    with pytest.raises(ValueError, match="objective does not reconcile"):
        _action(mechanics=_mechanics(objective=12))

    malformed = replace(
        _mechanics(),
        points_before_hits=RationalValue(16, 1),
        objective_points=RationalValue(12, 1),
    )
    with pytest.raises(ValueError, match="points-before-hits do not reconcile"):
        _action(mechanics=malformed)


def test_bench_boost_cannot_simultaneously_claim_autosub_points() -> None:
    ids = tuple(OfficialPlayerId(player_id) for player_id in range(1, 16))
    mechanics = DecisionMechanics(
        xi_points=RationalValue(10, 1),
        autosub_points=RationalValue(1, 1),
        captain_bonus=RationalValue(3, 1),
        squad_points_if_bench_boost=RationalValue(20, 1),
        points_before_hits=RationalValue(23, 1),
        hit_points=0,
        objective_points=RationalValue(23, 1),
    )
    with pytest.raises(ValueError, match="cannot also claim autosub"):
        DecisionAction(
            chip=DecisionChip.BENCH_BOOST,
            transfers=(),
            squad_ids=ids,
            xi_ids=ids[:11],
            captain_id=ids[0],
            vice_captain_id=ids[1],
            bench_gk_id=ids[11],
            outfield_bench_order=ids[12:],
            bank_after_tenths=0,
            mechanics=mechanics,
        )


def test_solver_certificate_rejects_zero_gap_that_does_not_reconcile_bound() -> None:
    with pytest.raises(ValueError, match="gap does not reconcile"):
        SolverCertificate(
            status=SolverStatus.OPTIMAL,
            incumbent_objective=RationalValue(10, 1),
            best_bound=RationalValue(11, 1),
            gap=RationalValue.zero(),
            numeric_error_bound=RationalValue.zero(),
            message="forged zero gap",
        )


def test_decision_result_rejects_solver_incumbent_not_equal_to_selected_objective() -> None:
    solver = _solver(12)
    with pytest.raises(ValueError, match="incumbent does not match"):
        DecisionResult(
            decision_input=_decision_input(),
            selected_action=_action(),
            alternatives=(),
            solver=solver,
            exactness=_exactness(solver),
            enumerated_actions=1,
        )


def test_decision_result_rejects_returned_alternative_better_than_selected() -> None:
    solver = _solver(11)
    better = _action(
        mechanics=DecisionMechanics(
            xi_points=RationalValue(11, 1),
            autosub_points=RationalValue(2, 1),
            captain_bonus=RationalValue(3, 1),
            squad_points_if_bench_boost=RationalValue(20, 1),
            points_before_hits=RationalValue(16, 1),
            hit_points=4,
            objective_points=RationalValue(12, 1),
        ),
        bank=1,
    )
    with pytest.raises(ValueError, match="cannot outrank"):
        DecisionResult(
            decision_input=_decision_input(),
            selected_action=_action(),
            alternatives=(better,),
            solver=solver,
            exactness=_exactness(solver),
            enumerated_actions=2,
        )


def test_expansion_certificate_rejects_expanded_optimum_below_baseline() -> None:
    with pytest.raises(ValueError, match="cannot be below baseline"):
        _expansion_certificate(
            baseline=100,
            expanded=99,
            threshold=2,
            result=ExpansionResult.NO_MATERIAL_IMPROVEMENT,
        )


def test_expansion_certificate_rejects_result_label_that_disagrees_with_objectives() -> None:
    with pytest.raises(ValueError, match="does not reconcile objectives and threshold"):
        _expansion_certificate(
            baseline=100,
            expanded=110,
            threshold=2,
            result=ExpansionResult.NO_MATERIAL_IMPROVEMENT,
        )
