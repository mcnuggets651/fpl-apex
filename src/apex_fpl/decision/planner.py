"""Executable exact-semantics receding-horizon planner for Apex V2.

The planner searches the full action semantics declared by the production DecisionPolicy.
It never turns a runtime cap into a global-optimality claim.  A deterministic no-transfer
trajectory supplies a legal incumbent first; branch-and-bound then explores the shared
exact action surface.  If the node budget is exhausted, the result carries a proof-valid
upper bound and explicit gap with ``SOLVER_LIMIT`` status.

This in-process implementation is correctness-first, not the independent reference
solver.  Production publication still requires a separately qualified solver worker and
parity evidence for the same receding-horizon objective.
"""

from __future__ import annotations

from datetime import datetime
from fractions import Fraction

from apex_fpl.core.decision import (
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionChip,
    DecisionInput,
    DecisionObjectiveModel,
    DecisionUseMode,
    RationalValue,
)
from apex_fpl.core.decision_policy import (
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
)
from apex_fpl.core.decision_policy_support import (
    CandidatePolicy,
    CandidatePolicyMode,
    ChipOptionValuePolicy,
    ContinuationValuePolicy,
    PricePolicy,
    PricePolicyMode,
)
from apex_fpl.core.forecast import Forecast
from apex_fpl.core.manager_state import ManagerState
from apex_fpl.core.planning import (
    PlanningSolverCertificate,
    PlanningSolverStatus,
    PlanningState,
    PlanningStep,
    PlanningTrajectory,
    RecedingHorizonDecisionResult,
)
from apex_fpl.core.rules import RuleSet

from .action_surface import (
    action_tie_key,
    enumerate_gameweek_actions,
    rational_from_fraction,
)
from .mechanics import build_gameweek_values
from .planning_objective import policy_value_to_rational, terminal_chip_reserve
from .planning_state import apply_planning_action, planning_state_from_manager_state


_ALL_CHIPS = (
    DecisionChip.NONE,
    DecisionChip.TRIPLE_CAPTAIN,
    DecisionChip.BENCH_BOOST,
    DecisionChip.WILDCARD,
    DecisionChip.FREE_HIT,
)


def _fraction(value: RationalValue) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _add(left: RationalValue, right: RationalValue) -> RationalValue:
    return RationalValue(
        left.numerator * right.denominator + right.numerator * left.denominator,
        left.denominator * right.denominator,
    )


def _subtract(left: RationalValue, right: RationalValue) -> RationalValue:
    return RationalValue(
        left.numerator * right.denominator - right.numerator * left.denominator,
        left.denominator * right.denominator,
    )


def _multiply(left: RationalValue, right: RationalValue) -> RationalValue:
    return RationalValue(
        left.numerator * right.numerator,
        left.denominator * right.denominator,
    )


def _compare(left: RationalValue, right: RationalValue) -> int:
    delta = left.numerator * right.denominator - right.numerator * left.denominator
    return (delta > 0) - (delta < 0)


def _max_rational(left: RationalValue | None, right: RationalValue) -> RationalValue:
    if left is None or _compare(right, left) > 0:
        return right
    return left


def _aware_before_or_equal(left: str, right: str) -> bool:
    left_dt = datetime.fromisoformat(left.replace("Z", "+00:00"))
    right_dt = datetime.fromisoformat(right.replace("Z", "+00:00"))
    return left_dt <= right_dt


def _validate_supports(
    *,
    state: ManagerState,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    policy: DecisionPolicy,
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
    price_policy: PricePolicy,
    candidate_policy: CandidatePolicy,
    use_mode: DecisionUseMode,
) -> None:
    state.require_decision_safe(ruleset=ruleset)
    policy.require_available_for(season=state.season, decision_cutoff=forecast.feature_cutoff)
    if policy.evaluation_mode is not DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION:
        raise ValueError("receding planner requires receding-horizon DecisionPolicy")
    if policy.objective_policy is not DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME:
        raise ValueError("receding planner requires max expected FPL points over time")
    if use_mode is DecisionUseMode.PRODUCTION and not policy.production_qualified:
        raise ValueError("production receding planner requires qualified DecisionPolicy")
    if not (
        state.season
        == forecast.season
        == ruleset.season
        == policy.season
        == continuation.season
        == chip_option.season
        == price_policy.season
        == candidate_policy.season
    ):
        raise ValueError("receding planner season mismatch")
    if state.ruleset_id != ruleset.ruleset_id or forecast.ruleset_id != ruleset.ruleset_id:
        raise ValueError("receding planner RuleSet identity mismatch")
    if universe.global_world_id != forecast.global_world_id:
        raise ValueError("receding planner candidate/forecast world mismatch")
    if universe.scope is not CandidateUniverseScope.FULL_OFFICIAL:
        raise ValueError("receding production semantics require FULL_OFFICIAL candidate universe")
    if price_policy.mode is not PricePolicyMode.OFFICIAL_CURRENT_ONLY:
        raise ValueError("receding planner supports only Official-current price semantics")
    if candidate_policy.mode is not CandidatePolicyMode.FULL_OFFICIAL:
        raise ValueError("receding planner supports only full-Official candidate semantics")
    if continuation.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("continuation horizon does not match DecisionPolicy")
    if chip_option.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("chip-option horizon does not match DecisionPolicy")
    bound_ids = (
        (policy.continuation_value_artifact_id, continuation.policy_id, "continuation"),
        (policy.chip_option_value_artifact_id, chip_option.policy_id, "chip-option"),
        (policy.price_policy_artifact_id, price_policy.policy_id, "price"),
        (policy.candidate_policy_artifact_id, candidate_policy.policy_id, "candidate"),
    )
    for declared, actual, label in bound_ids:
        if declared != actual:
            raise ValueError(f"DecisionPolicy {label} support identity mismatch")
    for support_time, label in (
        (continuation.first_available_at, "continuation"),
        (chip_option.first_available_at, "chip-option"),
        (price_policy.first_available_at, "price"),
        (candidate_policy.first_available_at, "candidate"),
    ):
        if not _aware_before_or_equal(support_time, forecast.feature_cutoff):
            raise ValueError(f"{label} support was not available at decision cutoff")


def _weight(continuation: ContinuationValuePolicy, depth: int) -> RationalValue:
    value = continuation.gameweek_weights[depth]
    return RationalValue(value.numerator, value.denominator)


def _make_step(
    *,
    state: PlanningState,
    action,
    next_state: PlanningState,
    weight: RationalValue,
) -> PlanningStep:
    points = action.mechanics.objective_points
    return PlanningStep(
        gameweek=state.gameweek,
        state_before_id=state.planning_state_id,
        action=action,
        state_after_id=next_state.planning_state_id,
        gameweek_points=points,
        continuation_weight=weight,
        weighted_points=_multiply(points, weight),
    )


def _trajectory_tie_key(trajectory: PlanningTrajectory) -> tuple:
    return tuple(action_tie_key(step.action) for step in trajectory.steps)


def _trajectory_better(left: PlanningTrajectory, right: PlanningTrajectory) -> bool:
    comparison = _compare(left.selection_objective, right.selection_objective)
    if comparison != 0:
        return comparison > 0
    return _trajectory_tie_key(left) > _trajectory_tie_key(right)


def _economic_state_key(state: PlanningState) -> tuple:
    return (
        state.gameweek,
        state.bank_tenths,
        state.free_transfers,
        tuple(
            (
                int(row.player_id),
                row.team_id,
                row.position,
                row.purchase_basis_tenths,
                row.current_price_tenths,
                row.selling_price_tenths,
            )
            for row in state.squad
        ),
        tuple((row.gameweek, row.chip, row.set_number) for row in state.chips_used),
    )


def _gameweek_global_upper_bound(
    *,
    forecast: Forecast,
    universe: CandidateUniverse,
    gameweek: int,
) -> RationalValue:
    """Admissible state-independent bound for any legal FPL action in one Gameweek.

    Ignoring budget, club and position constraints can only increase the bound. At most
    15 squad players can score before captaincy; Triple Captain can add at most two more
    copies of the best player's unconditional xP. Negative xP is clipped to zero only for
    the purpose of an upper bound.
    """

    values = build_gameweek_values(
        forecast,
        gameweek=gameweek,
        player_ids=(row.player_id for row in universe.players),
    )
    positive = sorted(
        (max(Fraction(0, 1), row.expected_points) for row in values.values()),
        reverse=True,
    )
    squad_bound = sum(positive[:15], Fraction(0, 1))
    captain_bound = (positive[0] if positive else Fraction(0, 1)) * 2
    return rational_from_fraction(squad_bound + captain_bound)


def _max_terminal_reserve(policy: ChipOptionValuePolicy) -> RationalValue:
    per_set = RationalValue.zero()
    for _, value in policy.option_values:
        per_set = _add(per_set, policy_value_to_rational(value))
    return _add(per_set, per_set)


def _remaining_upper_bound(
    *,
    depth: int,
    prefix: RationalValue,
    gameweek_bounds: tuple[RationalValue, ...],
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
) -> RationalValue:
    value = prefix
    for index in range(depth, len(gameweek_bounds)):
        value = _add(value, _multiply(gameweek_bounds[index], _weight(continuation, index)))
    return _add(value, _max_terminal_reserve(chip_option))


def _seed_incumbent(
    *,
    root: PlanningState,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
) -> PlanningTrajectory:
    """Build a deterministic legal no-transfer/no-chip path before exact search."""

    state = root
    steps: list[PlanningStep] = []
    for depth in range(continuation.horizon_gameweeks):
        actions = tuple(
            enumerate_gameweek_actions(
                state=state,
                forecast=forecast,
                universe=universe,
                ruleset=ruleset,
                max_normal_transfers=0,
                chips_considered=(DecisionChip.NONE,),
            )
        )
        if len(actions) != 1:
            raise ValueError("no-transfer planning seed must produce exactly one legal action")
        action = actions[0]
        next_state = apply_planning_action(state, action, universe, ruleset=ruleset)
        steps.append(
            _make_step(
                state=state,
                action=action,
                next_state=next_state,
                weight=_weight(continuation, depth),
            )
        )
        state = next_state
    reserve = terminal_chip_reserve(state, chip_option, ruleset=ruleset)
    total = reserve
    for step in steps:
        total = _add(total, step.weighted_points)
    return PlanningTrajectory(
        steps=tuple(steps),
        terminal_chip_reserve=reserve,
        selection_objective=total,
    )


def optimise_receding_horizon(
    *,
    state: ManagerState,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    policy: DecisionPolicy,
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
    price_policy: PricePolicy,
    candidate_policy: CandidatePolicy,
    use_mode: DecisionUseMode,
    max_search_nodes: int,
    alternatives_limit: int = 5,
) -> RecedingHorizonDecisionResult:
    """Search the governed multi-Gameweek objective with exact fail-closed certification."""

    if isinstance(max_search_nodes, bool) or not isinstance(max_search_nodes, int) or max_search_nodes <= 0:
        raise ValueError("max_search_nodes must be positive integer")
    _validate_supports(
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=ruleset,
        policy=policy,
        continuation=continuation,
        chip_option=chip_option,
        price_policy=price_policy,
        candidate_policy=candidate_policy,
        use_mode=use_mode,
    )
    root = planning_state_from_manager_state(state, universe, ruleset=ruleset)
    decision_input = DecisionInput(
        manager_state_id=state.manager_state_id,
        forecast_id=forecast.forecast_id,
        ruleset_id=ruleset.ruleset_id,
        candidate_universe_id=universe.candidate_universe_id,
        decision_policy_id=policy.decision_policy_id,
        gameweek=state.gameweek,
        use_mode=use_mode,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=15,
        chips_considered=_ALL_CHIPS,
    )

    gameweek_bounds = tuple(
        _gameweek_global_upper_bound(
            forecast=forecast,
            universe=universe,
            gameweek=state.gameweek + depth,
        )
        for depth in range(policy.horizon_gameweeks)
    )
    seed = _seed_incumbent(
        root=root,
        forecast=forecast,
        universe=universe,
        ruleset=ruleset,
        continuation=continuation,
        chip_option=chip_option,
    )
    incumbent = seed
    best_by_root: dict[str, PlanningTrajectory] = {seed.first_action.action_id: seed}
    root_actions_seen = {seed.first_action.action_id}
    dominance: dict[tuple[int, tuple], RationalValue] = {}
    expanded_nodes = 0
    pruned_nodes = 0
    limit_hit = False
    unresolved_upper: RationalValue | None = None

    def record_trajectory(trajectory: PlanningTrajectory) -> None:
        nonlocal incumbent
        root_id = trajectory.first_action.action_id
        root_actions_seen.add(root_id)
        existing = best_by_root.get(root_id)
        if existing is None or _trajectory_better(trajectory, existing):
            best_by_root[root_id] = trajectory
        if _trajectory_better(trajectory, incumbent):
            incumbent = trajectory

    def search(
        planning_state: PlanningState,
        *,
        depth: int,
        steps: tuple[PlanningStep, ...],
        prefix: RationalValue,
    ) -> None:
        nonlocal expanded_nodes, pruned_nodes, limit_hit, unresolved_upper
        if limit_hit:
            unresolved_upper = _max_rational(
                unresolved_upper,
                _remaining_upper_bound(
                    depth=depth,
                    prefix=prefix,
                    gameweek_bounds=gameweek_bounds,
                    continuation=continuation,
                    chip_option=chip_option,
                ),
            )
            return
        node_upper = _remaining_upper_bound(
            depth=depth,
            prefix=prefix,
            gameweek_bounds=gameweek_bounds,
            continuation=continuation,
            chip_option=chip_option,
        )
        if _compare(node_upper, incumbent.selection_objective) < 0:
            pruned_nodes += 1
            return
        if depth == policy.horizon_gameweeks:
            reserve = terminal_chip_reserve(planning_state, chip_option, ruleset=ruleset)
            total = _add(prefix, reserve)
            record_trajectory(
                PlanningTrajectory(
                    steps=steps,
                    terminal_chip_reserve=reserve,
                    selection_objective=total,
                )
            )
            return

        key = (depth, _economic_state_key(planning_state))
        previous = dominance.get(key)
        if previous is not None and _compare(previous, prefix) > 0:
            pruned_nodes += 1
            return
        if previous is None or _compare(prefix, previous) > 0:
            dominance[key] = prefix

        actions = enumerate_gameweek_actions(
            state=planning_state,
            forecast=forecast,
            universe=universe,
            ruleset=ruleset,
            max_normal_transfers=15,
            chips_considered=_ALL_CHIPS,
        )
        generated_any = False
        for action in actions:
            generated_any = True
            if expanded_nodes >= max_search_nodes:
                limit_hit = True
                unresolved_upper = _max_rational(unresolved_upper, node_upper)
                return
            expanded_nodes += 1
            if depth == 0:
                root_actions_seen.add(action.action_id)
            next_state = apply_planning_action(
                planning_state,
                action,
                universe,
                ruleset=ruleset,
            )
            step = _make_step(
                state=planning_state,
                action=action,
                next_state=next_state,
                weight=_weight(continuation, depth),
            )
            search(
                next_state,
                depth=depth + 1,
                steps=(*steps, step),
                prefix=_add(prefix, step.weighted_points),
            )
            if limit_hit:
                unresolved_upper = _max_rational(unresolved_upper, node_upper)
                return
        if not generated_any:
            raise ValueError(f"receding planner found no legal actions in GW{planning_state.gameweek}")

    search(root, depth=0, steps=(), prefix=RationalValue.zero())

    ordered = sorted(
        best_by_root.values(),
        key=lambda row: (_fraction(row.selection_objective), _trajectory_tie_key(row)),
        reverse=True,
    )
    selected = ordered[0]
    alternatives = tuple(ordered[1 : 1 + max(0, alternatives_limit)])
    if selected.trajectory_id != incumbent.trajectory_id:
        raise ValueError("planning incumbent/root ranking failed to reconcile")

    if not limit_hit:
        status = PlanningSolverStatus.OPTIMAL
        bound = selected.selection_objective
        gap = RationalValue.zero()
        complete = True
        message = "complete exact receding-horizon enumeration with admissible dominance pruning"
    else:
        status = PlanningSolverStatus.SOLVER_LIMIT
        bound = _max_rational(unresolved_upper, selected.selection_objective)
        gap = _subtract(bound, selected.selection_objective)
        complete = False
        message = (
            "receding-horizon node limit reached; incumbent retained with admissible "
            "unexplored-surface upper bound"
        )
    solver = PlanningSolverCertificate(
        status=status,
        incumbent_objective=selected.selection_objective,
        best_bound=bound,
        gap=gap,
        search_complete=complete,
        expanded_nodes=expanded_nodes,
        pruned_nodes=pruned_nodes,
        message=message,
    )
    return RecedingHorizonDecisionResult(
        decision_input=decision_input,
        initial_planning_state_id=root.planning_state_id,
        selected_trajectory=selected,
        alternatives=alternatives,
        solver=solver,
        enumerated_root_actions=len(root_actions_seen),
    )
