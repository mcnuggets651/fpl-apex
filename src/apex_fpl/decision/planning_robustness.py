"""Planning-aware robustness selection over the existing current-GW scenario engine.

Scenario robustness remains a stress test of the one action executable at the current
FPL deadline.  What changes for a receding-horizon decision is the admissible regret
band: root actions are selected by governed multi-Gameweek value, not by current-GW EV.
This module therefore reuses the exact existing scenario scorer/checkpoints while anchoring
regret to ``RecedingHorizonDecisionResult.selection_objective_for_action``.
"""

from __future__ import annotations

from fractions import Fraction

from apex_fpl.core.decision import CandidateUniverse
from apex_fpl.core.forecast import Forecast
from apex_fpl.core.planning import RecedingHorizonDecisionResult
from apex_fpl.core.rules import RuleSet
from apex_fpl.core.scenarios import (
    ActionRobustnessMetrics,
    RobustnessReport,
    ScenarioConvergencePolicy,
    ScenarioConvergenceStatus,
    ScenarioSet,
)

from .robustness import (
    _checkpoint,
    _checkpoint_converged,
    _fraction,
    _rational,
    _xp_reconciliation_failures,
)


def evaluate_planning_robustness(
    result: RecedingHorizonDecisionResult,
    scenario_set: ScenarioSet,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    policy: ScenarioConvergencePolicy,
) -> RobustnessReport:
    """Stress-test current root actions while preserving the multi-GW selection anchor."""

    if scenario_set.forecast_id != result.decision_input.forecast_id:
        raise ValueError("ScenarioSet forecast does not match planning result")
    if forecast.forecast_id != result.decision_input.forecast_id:
        raise ValueError("Forecast does not match planning result")
    if universe.candidate_universe_id != result.decision_input.candidate_universe_id:
        raise ValueError("candidate universe does not match planning result")
    if ruleset.ruleset_id != result.decision_input.ruleset_id:
        raise ValueError("RuleSet does not match planning result")
    if scenario_set.season != forecast.season or policy.season != forecast.season:
        raise ValueError("scenario/forecast/policy season mismatch")
    if ruleset.season != forecast.season:
        raise ValueError("planning robustness RuleSet season mismatch")
    policy.require_available_for(
        season=forecast.season,
        cutoff=forecast.feature_cutoff,
        production=False,
    )
    if result.decision_input.gameweek not in scenario_set.gameweeks:
        raise ValueError("ScenarioSet does not cover planning decision gameweek")
    if scenario_set.rng_algorithm.strip() == "":
        raise ValueError("ScenarioSet RNG identity is missing")

    trajectories = (result.selected_trajectory, *result.alternatives)
    actions_by_id = {row.first_action.action_id: row.first_action for row in trajectories}
    actions = tuple(actions_by_id[action_id] for action_id in sorted(actions_by_id))
    required_players = {pid for action in actions for pid in action.squad_ids}
    if not required_players.issubset(set(scenario_set.player_ids)):
        missing = sorted(required_players - set(scenario_set.player_ids))
        raise ValueError(f"ScenarioSet misses planning root players: {missing[:10]}")

    usable_counts = tuple(
        count
        for count in policy.checkpoint_counts
        if count <= scenario_set.scenario_count and count <= policy.max_scenarios
    )
    checkpoints = tuple(
        _checkpoint(
            actions,
            scenario_set,
            count,
            gameweek=result.decision_input.gameweek,
            universe=universe,
            ruleset=ruleset,
            policy=policy,
        )
        for count in usable_counts
    )
    blockers: list[str] = []
    xp_reconciled = False
    if len(checkpoints) < 2:
        blockers.append("insufficient nested scenario checkpoints for convergence")
    else:
        converged, convergence_blockers = _checkpoint_converged(
            checkpoints[-2],
            checkpoints[-1],
            policy=policy,
        )
        if not converged:
            blockers.extend(convergence_blockers)
        xp_failures = _xp_reconciliation_failures(
            scenario_set,
            forecast,
            sample_count=checkpoints[-1].sample_count,
            policy=policy,
        )
        xp_reconciled = not xp_failures
        blockers.extend(xp_failures[:20])

    status = (
        ScenarioConvergenceStatus.CONVERGED
        if len(checkpoints) >= 2 and xp_reconciled and not blockers
        else ScenarioConvergenceStatus.INCONCLUSIVE
    )
    anchor_action_id = result.selected_action.action_id
    robust_preferred = None
    robust_regret = None
    final_metrics = (
        {row.action_id: row for row in checkpoints[-1].metrics}
        if checkpoints
        else {}
    )
    if status is ScenarioConvergenceStatus.CONVERGED and final_metrics:
        selection_by_id = {
            trajectory.first_action.action_id: _fraction(trajectory.selection_objective)
            for trajectory in trajectories
        }
        anchor_objective = selection_by_id[anchor_action_id]
        regret_limit = _fraction(policy.max_ev_regret_tolerance)
        eligible_metrics: list[ActionRobustnessMetrics] = []
        regret_by_id: dict[str, Fraction] = {}
        for action_id, metrics in final_metrics.items():
            regret = anchor_objective - selection_by_id[action_id]
            if regret < 0:
                raise ValueError(
                    "planning robustness alternative cannot beat certified selection anchor"
                )
            regret_by_id[action_id] = regret
            if regret <= regret_limit:
                eligible_metrics.append(metrics)
        if not eligible_metrics:
            raise ValueError("planning selection anchor must remain inside its own regret band")
        robust_preferred = max(
            eligible_metrics,
            key=lambda row: (
                _fraction(row.lower_cvar_points),
                _fraction(row.mean_points),
                -len(row.action_id),
                row.action_id,
            ),
        ).action_id
        robust_regret = _rational(regret_by_id[robust_preferred])

    return RobustnessReport(
        decision_id=result.decision_id,
        forecast_id=forecast.forecast_id,
        scenario_set_id=scenario_set.scenario_set_id,
        scenario_policy_id=policy.scenario_policy_id,
        ev_anchor_action_id=anchor_action_id,
        robust_preferred_action_id=robust_preferred,
        robust_preferred_ev_regret=robust_regret,
        status=status,
        xp_reconciled=xp_reconciled,
        checkpoints=checkpoints,
        blockers=tuple(dict.fromkeys(blockers)),
    )
