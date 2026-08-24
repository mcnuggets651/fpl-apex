"""Exact fixed-action robustness scoring over one sealed common scenario stream."""

from __future__ import annotations

from fractions import Fraction

from apex_fpl.core.decision import (
    CandidateUniverse,
    DecisionAction,
    DecisionChip,
    DecisionResult,
    RationalValue,
)
from apex_fpl.core.forecast import Forecast, PROBABILITY_DENOMINATOR
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.rules import RuleSet
from apex_fpl.core.scenarios import (
    ActionRobustnessMetrics,
    JointScenario,
    RobustnessReport,
    ScenarioConvergenceCheckpoint,
    ScenarioConvergencePolicy,
    ScenarioConvergenceStatus,
    ScenarioSet,
)


_POSITION_ORDER = ("DEF", "MID", "FWD")


def _fraction(value: RationalValue) -> Fraction:
    return Fraction(value.numerator, value.denominator)


def _rational(value: Fraction) -> RationalValue:
    return RationalValue(value.numerator, value.denominator)


def _abs_diff(left: RationalValue, right: RationalValue) -> Fraction:
    return abs(_fraction(left) - _fraction(right))


def _lineup_limits(ruleset: RuleSet) -> tuple[dict[str, int], dict[str, int]]:
    minimum = {
        position: int(value)
        for position, value in ruleset.mapping("FPL-XI-POSITION-MIN-001").items()
    }
    maximum = {
        position: int(value)
        for position, value in ruleset.mapping("FPL-XI-POSITION-MAX-001").items()
    }
    return minimum, maximum


def _legal_outfield_counts(
    counts: dict[str, int],
    *,
    minimum: dict[str, int],
    maximum: dict[str, int],
) -> bool:
    return all(
        minimum[position] <= counts.get(position, 0) <= maximum[position]
        for position in _POSITION_ORDER
    )


def score_action_scenario(
    action: DecisionAction,
    scenario: JointScenario,
    *,
    gameweek: int,
    universe: CandidateUniverse,
    ruleset: RuleSet,
) -> int:
    """Score the submitted action in one realised scenario without hindsight edits."""

    outcomes = {
        row.player_id: row
        for row in scenario.outcomes
        if row.gameweek == gameweek
    }
    required = set(action.squad_ids)
    missing = sorted(required - set(outcomes))
    if missing:
        raise ValueError(f"scenario does not cover submitted squad: {missing[:10]}")
    positions = {
        player_id: universe.player(player_id).position for player_id in action.squad_ids
    }
    minimum, maximum = _lineup_limits(ruleset)

    captain_multiplier = (
        ruleset.integer("FPL-TRIPLE-CAPTAIN-MULTIPLIER-001")
        if action.chip is DecisionChip.TRIPLE_CAPTAIN
        else ruleset.integer("FPL-CAPTAIN-MULTIPLIER-001")
    )
    captain = outcomes[action.captain_id]
    vice = outcomes[action.vice_captain_id]
    if captain.appeared:
        captain_bonus = (captain_multiplier - 1) * captain.points
    elif vice.appeared:
        captain_bonus = (captain_multiplier - 1) * vice.points
    else:
        captain_bonus = 0

    if action.chip is DecisionChip.BENCH_BOOST:
        realised = sum(outcomes[player_id].points for player_id in action.squad_ids)
        return realised + captain_bonus - action.mechanics.hit_points

    realised = sum(outcomes[player_id].points for player_id in action.xi_ids)
    starting_gk = next(
        player_id for player_id in action.xi_ids if positions[player_id] == "GK"
    )
    if not outcomes[starting_gk].appeared and outcomes[action.bench_gk_id].appeared:
        realised += outcomes[action.bench_gk_id].points

    starters = tuple(
        player_id for player_id in action.xi_ids if positions[player_id] != "GK"
    )
    planned_counts = {
        position: sum(positions[player_id] == position for player_id in starters)
        for position in _POSITION_ORDER
    }
    missing_counts = {
        position: sum(
            positions[player_id] == position and not outcomes[player_id].appeared
            for player_id in starters
        )
        for position in _POSITION_ORDER
    }
    live_counts = dict(planned_counts)
    for bench_player in action.outfield_bench_order:
        if not outcomes[bench_player].appeared or not any(missing_counts.values()):
            continue
        bench_position = positions[bench_player]
        for missing_position in _POSITION_ORDER:
            if missing_counts[missing_position] <= 0:
                continue
            trial = dict(live_counts)
            trial[missing_position] -= 1
            trial[bench_position] += 1
            if not _legal_outfield_counts(
                trial,
                minimum=minimum,
                maximum=maximum,
            ):
                continue
            live_counts = trial
            missing_counts[missing_position] -= 1
            realised += outcomes[bench_player].points
            break

    return realised + captain_bonus - action.mechanics.hit_points


def _weighted_mean(scores: list[tuple[int, int]]) -> Fraction:
    total_weight = sum(weight for _, weight in scores)
    if total_weight <= 0:
        raise ValueError("weighted metric requires positive mass")
    return Fraction(sum(score * weight for score, weight in scores), total_weight)


def _lower_quantile(scores: list[tuple[int, int]], probability_bps: int) -> int:
    ordered = sorted(scores)
    total_weight = sum(weight for _, weight in ordered)
    target = Fraction(total_weight * probability_bps, 10_000)
    cumulative = 0
    for score, weight in ordered:
        cumulative += weight
        if Fraction(cumulative, 1) >= target:
            return score
    return ordered[-1][0]


def _lower_cvar(scores: list[tuple[int, int]], alpha_bps: int) -> Fraction:
    ordered = sorted(scores)
    total_weight = sum(weight for _, weight in ordered)
    target_mass = Fraction(total_weight * alpha_bps, 10_000)
    remaining = target_mass
    weighted_sum = Fraction(0, 1)
    for score, weight in ordered:
        if remaining <= 0:
            break
        used = min(Fraction(weight, 1), remaining)
        weighted_sum += score * used
        remaining -= used
    if target_mass <= 0 or remaining > 0:
        raise ValueError("CVaR tail mass could not be satisfied")
    return weighted_sum / target_mass


def _metrics_for_action(
    action: DecisionAction,
    scenarios: tuple[JointScenario, ...],
    *,
    gameweek: int,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    policy: ScenarioConvergencePolicy,
) -> ActionRobustnessMetrics:
    scores = [
        (
            score_action_scenario(
                action,
                scenario,
                gameweek=gameweek,
                universe=universe,
                ruleset=ruleset,
            ),
            scenario.weight,
        )
        for scenario in scenarios
    ]
    return ActionRobustnessMetrics(
        action_id=action.action_id,
        sample_count=len(scenarios),
        mean_points=_rational(_weighted_mean(scores)),
        lower_cvar_points=_rational(_lower_cvar(scores, policy.cvar_alpha_bps)),
        lower_quantile_points=_lower_quantile(scores, policy.lower_quantile_bps),
    )


def _ranking(
    metrics: tuple[ActionRobustnessMetrics, ...],
    *,
    field: str,
) -> tuple[str, ...]:
    if field == "tail":
        return tuple(
            row.action_id
            for row in sorted(
                metrics,
                key=lambda row: (-row.lower_quantile_points, row.action_id),
            )
        )
    return tuple(
        row.action_id
        for row in sorted(
            metrics,
            key=lambda row: (-_fraction(getattr(row, field)), row.action_id),
        )
    )


def _checkpoint(
    actions: tuple[DecisionAction, ...],
    scenario_set: ScenarioSet,
    sample_count: int,
    *,
    gameweek: int,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    policy: ScenarioConvergencePolicy,
) -> ScenarioConvergenceCheckpoint:
    scenarios = scenario_set.scenarios[:sample_count]
    metrics = tuple(
        _metrics_for_action(
            action,
            scenarios,
            gameweek=gameweek,
            universe=universe,
            ruleset=ruleset,
            policy=policy,
        )
        for action in actions
    )
    return ScenarioConvergenceCheckpoint(
        sample_count=sample_count,
        metrics=metrics,
        mean_ranking=_ranking(metrics, field="mean_points"),
        cvar_ranking=_ranking(metrics, field="lower_cvar_points"),
        tail_ranking=_ranking(metrics, field="tail"),
    )


def _forecast_gameweek_xp(
    forecast: Forecast,
    *,
    gameweek: int,
    player_id: OfficialPlayerId,
) -> Fraction:
    rows = [
        row
        for row in forecast.rows
        if row.target.gameweek == gameweek and row.target.player_id == player_id
    ]
    if not rows:
        raise ValueError(
            "Forecast misses scenario reconciliation target "
            f"gw={gameweek} player={int(player_id)}"
        )
    return sum(
        (
            Fraction(row.expected_points_numerator, PROBABILITY_DENOMINATOR)
            for row in rows
        ),
        Fraction(0, 1),
    )


def _xp_reconciliation_failures(
    scenario_set: ScenarioSet,
    forecast: Forecast,
    *,
    sample_count: int,
    policy: ScenarioConvergencePolicy,
) -> tuple[str, ...]:
    scenarios = scenario_set.scenarios[:sample_count]
    absolute_tolerance = _fraction(policy.xp_absolute_tolerance)
    sigma_multiplier = _fraction(policy.sampling_sigma_multiplier)
    failures: list[str] = []
    for gameweek in scenario_set.gameweeks:
        for player_id in scenario_set.player_ids:
            values = []
            weights = []
            for scenario in scenarios:
                outcome = next(
                    row
                    for row in scenario.outcomes
                    if row.gameweek == gameweek and row.player_id == player_id
                )
                values.append(outcome.points)
                weights.append(scenario.weight)
            total_weight = sum(weights)
            mean = Fraction(
                sum(value * weight for value, weight in zip(values, weights, strict=True)),
                total_weight,
            )
            canonical = _forecast_gameweek_xp(
                forecast,
                gameweek=gameweek,
                player_id=player_id,
            )
            difference = abs(mean - canonical)
            excess = max(difference - absolute_tolerance, Fraction(0, 1))
            if excess == 0:
                continue
            variance = sum(
                Fraction(weight, total_weight) * (Fraction(value, 1) - mean) ** 2
                for value, weight in zip(values, weights, strict=True)
            )
            weight_square_sum = sum(weight * weight for weight in weights)
            effective_n = Fraction(total_weight * total_weight, weight_square_sum)
            mean_variance = variance / effective_n
            if excess**2 > sigma_multiplier**2 * mean_variance:
                failures.append(
                    f"xp mismatch gw={gameweek} player={int(player_id)} "
                    f"scenario={mean} canonical={canonical}"
                )
    return tuple(failures)


def _checkpoint_converged(
    previous: ScenarioConvergenceCheckpoint,
    current: ScenarioConvergenceCheckpoint,
    *,
    policy: ScenarioConvergencePolicy,
) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    if previous.mean_ranking != current.mean_ranking:
        blockers.append("mean ranking changed across nested scenario prefixes")
    if previous.cvar_ranking != current.cvar_ranking:
        blockers.append("CVaR ranking changed across nested scenario prefixes")
    if previous.tail_ranking != current.tail_ranking:
        blockers.append("tail ranking changed across nested scenario prefixes")
    before = {row.action_id: row for row in previous.metrics}
    after = {row.action_id: row for row in current.metrics}
    if set(before) != set(after):
        blockers.append("action set changed across convergence checkpoints")
        return False, tuple(blockers)
    for action_id in sorted(before):
        left, right = before[action_id], after[action_id]
        if _abs_diff(left.mean_points, right.mean_points) > _fraction(policy.mean_tolerance):
            blockers.append(f"mean did not converge for action {action_id}")
        if _abs_diff(left.lower_cvar_points, right.lower_cvar_points) > _fraction(
            policy.cvar_tolerance
        ):
            blockers.append(f"CVaR did not converge for action {action_id}")
        if Fraction(
            abs(left.lower_quantile_points - right.lower_quantile_points),
            1,
        ) > _fraction(policy.tail_tolerance):
            blockers.append(f"tail quantile did not converge for action {action_id}")
    return not blockers, tuple(blockers)


def evaluate_decision_robustness(
    result: DecisionResult,
    scenario_set: ScenarioSet,
    forecast: Forecast,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    policy: ScenarioConvergencePolicy,
) -> RobustnessReport:
    """Evaluate EV anchor and alternatives on common nested scenario prefixes."""

    if scenario_set.forecast_id != result.decision_input.forecast_id:
        raise ValueError("ScenarioSet forecast does not match DecisionResult")
    if forecast.forecast_id != result.decision_input.forecast_id:
        raise ValueError("Forecast does not match DecisionResult")
    if universe.candidate_universe_id != result.decision_input.candidate_universe_id:
        raise ValueError("candidate universe does not match DecisionResult")
    if ruleset.ruleset_id != result.decision_input.ruleset_id:
        raise ValueError("RuleSet does not match DecisionResult")
    if scenario_set.season != forecast.season or policy.season != forecast.season:
        raise ValueError("scenario/forecast/policy season mismatch")
    if ruleset.season != forecast.season:
        raise ValueError("scenario robustness RuleSet season mismatch")
    policy.require_available_for(
        season=forecast.season,
        cutoff=forecast.feature_cutoff,
        production=False,
    )
    if result.decision_input.gameweek not in scenario_set.gameweeks:
        raise ValueError("ScenarioSet does not cover decision gameweek")
    if scenario_set.rng_algorithm.strip() == "":
        raise ValueError("ScenarioSet RNG identity is missing")

    actions_by_id = {
        action.action_id: action
        for action in (result.selected_action, *result.alternatives)
    }
    actions = tuple(actions_by_id[action_id] for action_id in sorted(actions_by_id))
    required_players = {pid for action in actions for pid in action.squad_ids}
    if not required_players.issubset(set(scenario_set.player_ids)):
        missing = sorted(required_players - set(scenario_set.player_ids))
        raise ValueError(f"ScenarioSet misses decision players: {missing[:10]}")

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
    ev_anchor = result.selected_action.action_id
    robust_preferred = None
    robust_regret = None
    final_metrics = (
        {row.action_id: row for row in checkpoints[-1].metrics}
        if checkpoints
        else {}
    )
    if status is ScenarioConvergenceStatus.CONVERGED and final_metrics:
        objective_by_id = {
            action.action_id: _fraction(action.mechanics.objective_points)
            for action in actions
        }
        anchor_objective = objective_by_id[ev_anchor]
        regret_limit = _fraction(policy.max_ev_regret_tolerance)
        eligible_metrics: list[ActionRobustnessMetrics] = []
        regret_by_id: dict[str, Fraction] = {}
        for action_id, metrics in final_metrics.items():
            regret = anchor_objective - objective_by_id[action_id]
            if regret < 0:
                raise ValueError("robust alternative cannot beat certified EV anchor objective")
            regret_by_id[action_id] = regret
            if regret <= regret_limit:
                eligible_metrics.append(metrics)
        if not eligible_metrics:
            raise ValueError("EV anchor must remain inside its own robustness regret band")
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
        ev_anchor_action_id=ev_anchor,
        robust_preferred_action_id=robust_preferred,
        robust_preferred_ev_regret=robust_regret,
        status=status,
        xp_reconciled=xp_reconciled,
        checkpoints=checkpoints,
        blockers=tuple(dict.fromkeys(blockers)),
    )
