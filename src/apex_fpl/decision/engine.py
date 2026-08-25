"""Exhaustive reference DecisionEngine for one current FPL gameweek.

This engine is intentionally correctness-first. It completely enumerates the declared
candidate universe and declared action surface, then exhaustively optimises submission
mechanics for each legal resulting squad. Its exactness certificate makes any narrower
universe/action surface visible instead of pretending it is a global optimum.

This entry point is deliberately tactical/shadow-only. A persistent production action
must use the qualified receding-horizon policy path; this function refuses to relabel
one-Gameweek chip/transfer EV as max-EV-over-time.
"""

from __future__ import annotations

from apex_fpl.core.decision import (
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionChip,
    DecisionInput,
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
from apex_fpl.core.decision_policy import DecisionEvaluationMode, DecisionPolicy
from apex_fpl.core.forecast import Forecast
from apex_fpl.core.manager_state import ManagerState
from apex_fpl.core.rules import RuleSet

from .action_surface import (
    action_objective,
    action_surface_complete,
    action_tie_key,
    available_chips,
    enumerate_gameweek_actions,
    rational_from_fraction,
    validate_owned_against_universe,
)


def optimise_current_gameweek(
    *,
    state: ManagerState,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    policy: DecisionPolicy,
    use_mode: DecisionUseMode,
    max_normal_transfers: int,
    chips_considered: tuple[DecisionChip, ...] = (DecisionChip.NONE,),
    alternatives_limit: int = 5,
) -> DecisionResult:
    """Return the maximum tactical marginal-EV action over the declared shadow surface."""

    state.require_decision_safe(ruleset=ruleset)
    policy.require_available_for(
        season=state.season,
        decision_cutoff=forecast.feature_cutoff,
    )
    if policy.evaluation_mode is not DecisionEvaluationMode.TACTICAL_CURRENT_GAMEWEEK:
        raise ValueError(
            "current-gameweek reference engine cannot execute a receding-horizon policy"
        )
    if use_mode is DecisionUseMode.PRODUCTION:
        raise ValueError(
            "tactical current-Gameweek reference engine is shadow-only; production requires "
            "the qualified receding-horizon DecisionPolicy path"
        )
    if state.gameweek <= 0:
        raise ValueError("DecisionEngine requires a positive current gameweek")
    if forecast.season != state.season or ruleset.season != state.season:
        raise ValueError("decision season mismatch")
    if (
        forecast.ruleset_id != ruleset.ruleset_id
        or state.ruleset_id != ruleset.ruleset_id
    ):
        raise ValueError("decision RuleSet identity mismatch")
    if universe.global_world_id != forecast.global_world_id:
        raise ValueError("candidate universe GlobalWorldId does not match Forecast")
    validate_owned_against_universe(state, universe)

    available = available_chips(state, ruleset=ruleset)
    considered = tuple(sorted(set(chips_considered), key=lambda chip: chip.value))
    decision_input = DecisionInput(
        manager_state_id=state.manager_state_id,
        forecast_id=forecast.forecast_id,
        ruleset_id=ruleset.ruleset_id,
        candidate_universe_id=universe.candidate_universe_id,
        decision_policy_id=policy.decision_policy_id,
        gameweek=state.gameweek,
        use_mode=use_mode,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=max_normal_transfers,
        chips_considered=considered,
    )

    legal_actions = list(
        enumerate_gameweek_actions(
            state=state,
            forecast=forecast,
            universe=universe,
            ruleset=ruleset,
            max_normal_transfers=decision_input.max_normal_transfers,
            chips_considered=decision_input.chips_considered,
        )
    )
    if not legal_actions:
        raise ValueError("DecisionEngine found no legal actions in declared search surface")

    legal_actions.sort(
        key=lambda action: (action_objective(action), action_tie_key(action)),
        reverse=True,
    )
    selected = legal_actions[0]
    alternatives = tuple(legal_actions[1 : 1 + max(0, alternatives_limit)])
    incumbent = rational_from_fraction(action_objective(selected))
    zero = RationalValue.zero()
    solver = SolverCertificate(
        status=SolverStatus.OPTIMAL,
        incumbent_objective=incumbent,
        best_bound=incumbent,
        gap=zero,
        numeric_error_bound=zero,
        message="exhaustive tactical reference enumeration completed",
    )

    surface_complete = action_surface_complete(
        max_normal_transfers=decision_input.max_normal_transfers,
        chips_considered=decision_input.chips_considered,
        available=available,
    )
    reasons: list[str] = [
        "tactical current-Gameweek policy is shadow/reference only"
    ]
    if universe.scope is not CandidateUniverseScope.FULL_OFFICIAL:
        reasons.append(
            "candidate universe is scoped and has no successful expansion certificate"
        )
    if not surface_complete:
        missing_chips = sorted(
            chip.value for chip in available - set(decision_input.chips_considered)
        )
        if decision_input.max_normal_transfers < 15:
            reasons.append(
                "normal transfer surface capped at "
                f"{decision_input.max_normal_transfers}/15"
            )
        if missing_chips:
            reasons.append(
                "available chips omitted from action surface: " + ",".join(missing_chips)
            )

    status = (
        ExactnessStatus.GLOBAL_OPTIMAL
        if universe.scope is CandidateUniverseScope.FULL_OFFICIAL and surface_complete
        else ExactnessStatus.FEASIBLE_INCUMBENT
    )
    exactness_reasons = () if status is ExactnessStatus.GLOBAL_OPTIMAL else tuple(reasons)
    exactness = ExactnessClaim(
        status=status,
        candidate_universe_id=universe.candidate_universe_id,
        universe_scope=universe.scope,
        solver_status=solver.status,
        action_surface_complete=surface_complete,
        search_complete=True,
        best_bound=solver.best_bound,
        gap=solver.gap,
        filter_identity=universe.filter_identity,
        expansion_result=ExpansionResult.NOT_RUN,
        expansion_certificate_id=None,
        numeric_error_bound=solver.numeric_error_bound,
        reasons=exactness_reasons,
    )
    return DecisionResult(
        decision_input=decision_input,
        selected_action=selected,
        alternatives=alternatives,
        solver=solver,
        exactness=exactness,
        enumerated_actions=len(legal_actions),
    )
