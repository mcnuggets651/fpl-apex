from __future__ import annotations

from dataclasses import replace

import pytest

from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import (
    DecisionAction,
    DecisionChip,
    DecisionInput,
    DecisionMechanics,
    DecisionObjectiveModel,
    DecisionUseMode,
    RationalValue,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    CandidateUniverseId,
    DecisionPolicyId,
    ForecastId,
    GlobalWorldId,
    ManagerStateId,
    PlanningStateId,
    RuleSetId,
)
from apex_fpl.core.manager_state import OwnedPlayer
from apex_fpl.core.planning import (
    PlanningChipUse,
    PlanningSolverCertificate,
    PlanningSolverStatus,
    PlanningState,
    PlanningStep,
    PlanningTrajectory,
    RecedingHorizonDecisionResult,
)


def _owned() -> tuple[OwnedPlayer, ...]:
    positions = (
        "GK",
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
        "FWD",
    )
    return tuple(
        OwnedPlayer(
            player_id=OfficialPlayerId(index),
            team_id=index,
            position=position,
            purchase_basis_tenths=50,
            current_price_tenths=50,
            selling_price_tenths=50,
        )
        for index, position in enumerate(positions, start=1)
    )


def _state(*, gameweek: int = 2, parent: bool = False) -> PlanningState:
    return PlanningState(
        origin_manager_state_id=ManagerStateId("manager-current"),
        price_world_id=GlobalWorldId("world"),
        season="2026-2027",
        entry_id=63984,
        gameweek=gameweek,
        ruleset_id=RuleSetId("rules"),
        bank_tenths=10,
        free_transfers=1,
        squad=_owned(),
        chips_used=(PlanningChipUse(1, "TRIPLE_CAPTAIN", 1),),
        parent_state_id=(PlanningStateId("parent") if parent else None),
        parent_action_id=("action-parent" if parent else None),
    )


def _mechanics(points: int) -> DecisionMechanics:
    value = RationalValue(points, 1)
    return DecisionMechanics(
        xi_points=RationalValue(points - 2, 1),
        autosub_points=RationalValue.zero(),
        captain_bonus=RationalValue(2, 1),
        squad_points_if_bench_boost=RationalValue.zero(),
        points_before_hits=value,
        hit_points=0,
        objective_points=value,
    )


def _action(points: int, *, captain: int = 13) -> DecisionAction:
    xi = tuple(OfficialPlayerId(index) for index in (1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14))
    vice = 14 if captain == 13 else 13
    return DecisionAction(
        chip=DecisionChip.NONE,
        transfers=(),
        squad_ids=tuple(OfficialPlayerId(index) for index in range(1, 16)),
        xi_ids=xi,
        captain_id=OfficialPlayerId(captain),
        vice_captain_id=OfficialPlayerId(vice),
        bench_gk_id=OfficialPlayerId(2),
        outfield_bench_order=(OfficialPlayerId(6), OfficialPlayerId(7), OfficialPlayerId(15)),
        bank_after_tenths=10,
        mechanics=_mechanics(points),
    )


def _input() -> DecisionInput:
    return DecisionInput(
        manager_state_id=ManagerStateId("manager-current"),
        forecast_id=ForecastId("forecast"),
        ruleset_id=RuleSetId("rules"),
        candidate_universe_id=CandidateUniverseId("universe"),
        decision_policy_id=DecisionPolicyId("receding-policy"),
        gameweek=2,
        use_mode=DecisionUseMode.PRODUCTION,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=15,
        chips_considered=tuple(DecisionChip),
    )


def _trajectory(*, first_points: int, future_points: int, captain: int) -> PlanningTrajectory:
    state0 = PlanningStateId("state-0")
    state1 = PlanningStateId(f"state-1-{captain}")
    state2 = PlanningStateId(f"state-2-{captain}")
    first = _action(first_points, captain=captain)
    second = _action(future_points, captain=captain)
    step1 = PlanningStep(
        gameweek=2,
        state_before_id=state0,
        action=first,
        state_after_id=state1,
        gameweek_points=first.mechanics.objective_points,
        continuation_weight=RationalValue(1, 1),
        weighted_points=first.mechanics.objective_points,
    )
    weighted_future = RationalValue(future_points, 2)
    step2 = PlanningStep(
        gameweek=3,
        state_before_id=state1,
        action=second,
        state_after_id=state2,
        gameweek_points=second.mechanics.objective_points,
        continuation_weight=RationalValue(1, 2),
        weighted_points=weighted_future,
    )
    objective = RationalValue(first_points * 2 + future_points, 2)
    return PlanningTrajectory(
        steps=(step1, step2),
        terminal_chip_reserve=RationalValue.zero(),
        selection_objective=objective,
    )


def test_planning_state_is_content_addressed_and_not_manager_truth() -> None:
    first = _state()
    second = _state()
    assert first.planning_state_id == second.planning_state_id
    assert str(first.planning_state_id).startswith("sha256:")
    assert first.semantic_payload()["schema_name"] == "apex-planning-state"
    assert "scope" not in first.semantic_payload()
    assert "provenance_artifact_ids" not in first.semantic_payload()


def test_planning_state_parent_lineage_is_atomic() -> None:
    with pytest.raises(ValueError, match="parent state/action lineage must be paired"):
        replace(_state(), parent_state_id=PlanningStateId("parent"))
    with pytest.raises(ValueError, match="parent state/action lineage must be paired"):
        replace(_state(), parent_action_id="action")


def test_planning_state_rejects_duplicate_chip_entitlement_use() -> None:
    with pytest.raises(ValueError, match="same chip twice"):
        replace(
            _state(),
            chips_used=(
                PlanningChipUse(2, "WILDCARD", 1),
                PlanningChipUse(3, "WILDCARD", 1),
            ),
        )


def test_planning_step_reconciles_exact_action_points_and_weight() -> None:
    action = _action(10)
    with pytest.raises(ValueError, match="must equal exact DecisionAction mechanics"):
        PlanningStep(
            gameweek=2,
            state_before_id=PlanningStateId("before"),
            action=action,
            state_after_id=PlanningStateId("after"),
            gameweek_points=RationalValue(9, 1),
            continuation_weight=RationalValue(1, 1),
            weighted_points=RationalValue(9, 1),
        )
    with pytest.raises(ValueError, match="weighted points do not reconcile"):
        PlanningStep(
            gameweek=2,
            state_before_id=PlanningStateId("before"),
            action=action,
            state_after_id=PlanningStateId("after"),
            gameweek_points=RationalValue(10, 1),
            continuation_weight=RationalValue(1, 2),
            weighted_points=RationalValue(10, 1),
        )


def test_receding_result_can_choose_lower_current_gw_for_higher_policy_value() -> None:
    # Selected: 9 now + 20/2 future = 19 policy points.
    selected = _trajectory(first_points=9, future_points=20, captain=13)
    # Alternative: 10 now + 16/2 future = 18 policy points.
    immediate_better = _trajectory(first_points=10, future_points=16, captain=14)
    zero = RationalValue.zero()
    solver = PlanningSolverCertificate(
        status=PlanningSolverStatus.OPTIMAL,
        incumbent_objective=selected.selection_objective,
        best_bound=selected.selection_objective,
        gap=zero,
        search_complete=True,
        expanded_nodes=2,
        pruned_nodes=0,
        message="exact synthetic search",
    )
    result = RecedingHorizonDecisionResult(
        decision_input=_input(),
        initial_planning_state_id=selected.first_state_id,
        selected_trajectory=selected,
        alternatives=(immediate_better,),
        solver=solver,
        enumerated_root_actions=2,
    )
    assert result.selected_action.mechanics.objective_points == RationalValue(9, 1)
    assert immediate_better.first_action.mechanics.objective_points == RationalValue(10, 1)
    assert result.selection_objective == RationalValue(19, 1)
    assert result.decision_id.value.startswith("sha256:")


def test_receding_result_rejects_alternative_with_higher_policy_objective() -> None:
    selected = _trajectory(first_points=9, future_points=16, captain=13)
    better = _trajectory(first_points=10, future_points=20, captain=14)
    solver = PlanningSolverCertificate(
        status=PlanningSolverStatus.FEASIBLE,
        incumbent_objective=selected.selection_objective,
        best_bound=better.selection_objective,
        gap=RationalValue(3, 1),
        search_complete=False,
        expanded_nodes=2,
        pruned_nodes=0,
        message="synthetic incomplete search",
    )
    with pytest.raises(ValueError, match="cannot outrank selected policy objective"):
        RecedingHorizonDecisionResult(
            decision_input=_input(),
            initial_planning_state_id=selected.first_state_id,
            selected_trajectory=selected,
            alternatives=(better,),
            solver=solver,
            enumerated_root_actions=2,
        )


def test_optimal_planning_certificate_requires_complete_zero_gap() -> None:
    objective = RationalValue(10, 1)
    with pytest.raises(ValueError, match="requires complete zero-gap proof"):
        PlanningSolverCertificate(
            status=PlanningSolverStatus.OPTIMAL,
            incumbent_objective=objective,
            best_bound=RationalValue(11, 1),
            gap=RationalValue(1, 1),
            search_complete=False,
            expanded_nodes=1,
            pruned_nodes=0,
            message="not actually optimal",
        )


def test_planning_result_identity_changes_with_future_trajectory() -> None:
    first = _trajectory(first_points=9, future_points=20, captain=13)
    second = _trajectory(first_points=9, future_points=22, captain=13)
    assert first.trajectory_id != second.trajectory_id
    assert canonical_sha256(first.semantic_payload()) != canonical_sha256(second.semantic_payload())
