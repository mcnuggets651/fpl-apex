from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex.domain.models import (
    OfficialSnapshot,
    ProductionProjectionSurface,
    SystemDecision,
    TeamState,
)
from apex.domain.rules import (
    MAX_PER_TEAM,
    SQUAD_COUNTS,
    XI_MAX,
    XI_MIN,
    season_rules,
)

from .mechanics import best_fixed_squad_mechanics, decision_from_fixed_squad, xp_map


@dataclass(frozen=True)
class TransferWeek:
    horizon: int
    gameweek: int
    squad_ids: tuple[int, ...]
    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    bank_tenths: int
    free_transfers: int
    hits: int
    submitted_ev: float


@dataclass(frozen=True)
class TransferOptimisationResult:
    decision: SystemDecision | None
    weeks: tuple[TransferWeek, ...]
    status: str
    primary_objective: float | None
    solver: dict


def optimise_transfer_horizon(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    team: TeamState,
    *,
    max_horizon: int,
    excluded_h1: frozenset[int] = frozenset(),
    candidate_limit: int = 8,
    candidate_regret_fraction: float = 0.005,
) -> TransferOptimisationResult:
    """Optimise a transfer path then exact-rescore near-optimal paths.

    The MILP remains the canonical max-xP candidate generator. Near-optimal
    distinct squad paths are then rescored with exact FPL automatic substitutions
    and captain/vice fallback. If the bounded shortlist cannot be proven complete,
    Apex retains the primary max-xP path rather than allowing an uncertified
    secondary selector to override it.
    """
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    if not 0.0 <= float(candidate_regret_fraction) <= 0.05:
        raise ValueError("candidate_regret_fraction must be between 0 and 5%")

    if max_horizon < 2:
        decision = decision_from_fixed_squad(
            official,
            surface,
            team.squad_ids,
            horizon=1,
            decision_mode="HOLD_H1_ONLY",
            xi_excluded=excluded_h1,
        )
        return TransferOptimisationResult(
            decision,
            (),
            "WITHHELD_H1_ONLY",
            decision.objective,
            {"reason": "discretionary transfers require H2+ qualified forecast"},
        )
    if (
        not team.state_complete_for_transfers
        or len(team.selling_prices_tenths) != 15
    ):
        decision = decision_from_fixed_squad(
            official,
            surface,
            team.squad_ids,
            horizon=1,
            decision_mode="HOLD_TEAM_STATE_INCOMPLETE",
            xi_excluded=excluded_h1,
        )
        return TransferOptimisationResult(
            decision,
            (),
            "WITHHELD_TEAM_STATE_INCOMPLETE",
            decision.objective,
            {"reason": "exact selling-price state incomplete"},
        )

    horizons = list(range(1, max_horizon + 1))
    xp = {horizon: xp_map(surface, horizon) for horizon in horizons}
    universe = set.intersection(*(set(xp[horizon]) for horizon in horizons))
    players = [
        player
        for player in official.players
        if player.element_id in universe
        and (player.can_transact or player.element_id in team.squad_ids)
    ]
    player_count = len(players)
    horizon_count = len(horizons)
    player_ids = [player.element_id for player in players]
    by_player = {
        player_id: index
        for index, player_id in enumerate(player_ids)
    }
    if not set(team.squad_ids).issubset(by_player):
        return TransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            None,
            {"reason": "current squad missing from forecast universe"},
        )

    block = player_count * horizon_count
    squad_base = 0
    xi_base = block
    captain_base = 2 * block
    transfer_in_base = 3 * block
    transfer_out_base = 4 * block
    bank_base = 5 * block

    rules = season_rules(official.season)
    max_free_transfers = rules.max_rolled_free_transfers
    if not 0 <= int(team.free_transfers) <= max_free_transfers:
        return TransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            None,
            {
                "reason": (
                    "current free-transfer state outside supported range: "
                    f"{team.free_transfers}"
                )
            },
        )

    free_transfer_state_count = max_free_transfers + 1
    max_transfers = 16
    state_base = bank_base + horizon_count
    variable_count = (
        state_base
        + horizon_count * free_transfer_state_count * max_transfers
    )

    def player_var(base, index, period):
        return base + period * player_count + index

    def state_var(period, free_transfers, transfers):
        return (
            state_base
            + (period * free_transfer_state_count + free_transfers)
            * max_transfers
            + transfers
        )

    expected_value = np.zeros(variable_count)
    transfer_count_objective = np.zeros(variable_count)
    for period, horizon in enumerate(horizons):
        for index, player_id in enumerate(player_ids):
            expected_value[
                player_var(xi_base, index, period)
            ] += xp[horizon][player_id]
            expected_value[
                player_var(captain_base, index, period)
            ] += xp[horizon][player_id]
            transfer_count_objective[
                player_var(transfer_in_base, index, period)
            ] = 1
        for free_transfers in range(max_free_transfers + 1):
            for transfers in range(max_transfers):
                expected_value[
                    state_var(period, free_transfers, transfers)
                ] -= rules.transfer_hit_cost * max(
                    0,
                    transfers - free_transfers,
                )

    rows = []
    lower_bounds = []
    upper_bounds = []

    def add(coefficients, lower, upper):
        rows.append(coefficients)
        lower_bounds.append(lower)
        upper_bounds.append(upper)

    for period, horizon in enumerate(horizons):
        add(
            {
                player_var(squad_base, index, period): 1
                for index in range(player_count)
            },
            15,
            15,
        )
        add(
            {
                player_var(xi_base, index, period): 1
                for index in range(player_count)
            },
            11,
            11,
        )
        add(
            {
                player_var(captain_base, index, period): 1
                for index in range(player_count)
            },
            1,
            1,
        )
        for position, required in SQUAD_COUNTS.items():
            indices = [
                index
                for index, player in enumerate(players)
                if player.position == position
            ]
            add(
                {
                    player_var(squad_base, index, period): 1
                    for index in indices
                },
                required,
                required,
            )
            add(
                {
                    player_var(xi_base, index, period): 1
                    for index in indices
                },
                XI_MIN[position],
                XI_MAX[position],
            )
        for team_id in sorted({player.team_id for player in players}):
            add(
                {
                    player_var(squad_base, index, period): 1
                    for index, player in enumerate(players)
                    if player.team_id == team_id
                },
                -np.inf,
                MAX_PER_TEAM,
            )

        for index, player in enumerate(players):
            if period == 0 and player.element_id in excluded_h1:
                add({player_var(xi_base, index, period): 1}, 0, 0)
                add({player_var(captain_base, index, period): 1}, 0, 0)
            add(
                {
                    player_var(xi_base, index, period): 1,
                    player_var(squad_base, index, period): -1,
                },
                -np.inf,
                0,
            )
            add(
                {
                    player_var(captain_base, index, period): 1,
                    player_var(xi_base, index, period): -1,
                },
                -np.inf,
                0,
            )
            add(
                {
                    player_var(transfer_in_base, index, period): 1,
                    player_var(transfer_out_base, index, period): 1,
                },
                -np.inf,
                1,
            )
            initial = 1 if player.element_id in team.squad_ids else 0
            if period == 0:
                add(
                    {
                        player_var(squad_base, index, period): 1,
                        player_var(transfer_in_base, index, period): -1,
                        player_var(transfer_out_base, index, period): 1,
                    },
                    initial,
                    initial,
                )
            else:
                add(
                    {
                        player_var(squad_base, index, period): 1,
                        player_var(squad_base, index, period - 1): -1,
                        player_var(transfer_in_base, index, period): -1,
                        player_var(transfer_out_base, index, period): 1,
                    },
                    0,
                    0,
                )

        balance = {
            player_var(transfer_in_base, index, period): 1
            for index in range(player_count)
        }
        balance.update(
            {
                player_var(transfer_out_base, index, period): -1
                for index in range(player_count)
            }
        )
        add(balance, 0, 0)

        add(
            {
                state_var(period, free_transfers, transfers): 1
                for free_transfers in range(max_free_transfers + 1)
                for transfers in range(max_transfers)
            },
            1,
            1,
        )
        transfer_counter = {
            player_var(transfer_in_base, index, period): 1
            for index in range(player_count)
        }
        transfer_counter.update(
            {
                state_var(period, free_transfers, transfers): -transfers
                for free_transfers in range(max_free_transfers + 1)
                for transfers in range(max_transfers)
            }
        )
        add(transfer_counter, 0, 0)

        if period == 0:
            add(
                {
                    state_var(
                        period,
                        int(team.free_transfers),
                        transfers,
                    ): 1
                    for transfers in range(max_transfers)
                },
                1,
                1,
            )
        else:
            for current_ft in range(max_free_transfers + 1):
                coefficients = {
                    state_var(period, current_ft, transfers): 1
                    for transfers in range(max_transfers)
                }
                for previous_ft in range(max_free_transfers + 1):
                    for previous_transfers in range(max_transfers):
                        next_ft = min(
                            max_free_transfers,
                            max(
                                1,
                                previous_ft - previous_transfers + 1,
                            ),
                        )
                        if next_ft == current_ft:
                            key = state_var(
                                period - 1,
                                previous_ft,
                                previous_transfers,
                            )
                            coefficients[key] = coefficients.get(key, 0) - 1
                add(coefficients, 0, 0)

        cash = {bank_base + period: 1}
        player_map = official.player_map()
        for index, player_id in enumerate(player_ids):
            buy = player_map[player_id].price_tenths
            sell = (
                team.selling_prices_tenths.get(player_id, buy)
                if player_id in team.squad_ids
                else buy
            )
            cash[player_var(transfer_in_base, index, period)] = buy
            cash[player_var(transfer_out_base, index, period)] = -sell
        if period == 0:
            add(cash, team.bank_tenths, team.bank_tenths)
        else:
            cash[bank_base + period - 1] = -1
            add(cash, 0, 0)

    lower_variable_bounds = np.zeros(variable_count)
    upper_variable_bounds = np.ones(variable_count)
    integrality = np.ones(variable_count, dtype=int)
    for period in range(horizon_count):
        lower_variable_bounds[bank_base + period] = 0
        upper_variable_bounds[bank_base + period] = 2000
        integrality[bank_base + period] = 0

    def solve(objective, extras=()):
        solve_rows = list(rows)
        solve_lower = list(lower_bounds)
        solve_upper = list(upper_bounds)
        for coefficients, extra_lower, extra_upper in extras:
            solve_rows.append(coefficients)
            solve_lower.append(extra_lower)
            solve_upper.append(extra_upper)

        matrix = lil_matrix((len(solve_rows), variable_count))
        for row_index, coefficients in enumerate(solve_rows):
            for column, value in coefficients.items():
                matrix[row_index, column] = value
        return milp(
            c=objective,
            integrality=integrality,
            bounds=Bounds(
                lower_variable_bounds,
                upper_variable_bounds,
            ),
            constraints=LinearConstraint(
                matrix.tocsr(),
                np.asarray(solve_lower),
                np.asarray(solve_upper),
            ),
            options={"time_limit": 120, "mip_rel_gap": 1e-09},
        )

    objective_coefficients = {
        index: float(value)
        for index, value in enumerate(expected_value)
        if abs(value) > 1e-15
    }

    def path_exclusion(solution):
        coefficients = {}
        selected_count = 0
        for period in range(horizon_count):
            for index in range(player_count):
                variable = player_var(squad_base, index, period)
                if solution[variable] > 0.5:
                    coefficients[variable] = 1.0
                    selected_count += 1
        if selected_count != 15 * horizon_count:
            raise RuntimeError(
                "decoded transfer path does not contain 15 players per horizon"
            )
        return (
            coefficients,
            -np.inf,
            float(selected_count - 1),
        )

    def decode(solution):
        weeks = []
        exact_objective = 0.0
        free_transfer_state = int(team.free_transfers)
        for period, horizon in enumerate(horizons):
            squad = tuple(
                sorted(
                    player_ids[index]
                    for index in range(player_count)
                    if solution[
                        player_var(squad_base, index, period)
                    ] > 0.5
                )
            )
            transfers_in = tuple(
                sorted(
                    player_ids[index]
                    for index in range(player_count)
                    if solution[
                        player_var(transfer_in_base, index, period)
                    ] > 0.5
                )
            )
            transfers_out = tuple(
                sorted(
                    player_ids[index]
                    for index in range(player_count)
                    if solution[
                        player_var(transfer_out_base, index, period)
                    ] > 0.5
                )
            )
            transfers_made = len(transfers_in)
            hits = max(0, transfers_made - free_transfer_state)
            bank = int(round(solution[bank_base + period]))
            gameweek = (
                min(official.deadlines) + horizon - 1
                if official.deadlines
                else horizon
            )
            mechanics = best_fixed_squad_mechanics(
                official,
                surface,
                squad,
                horizon=horizon,
                xi_excluded=(
                    excluded_h1
                    if period == 0
                    else frozenset()
                ),
            )
            weeks.append(
                TransferWeek(
                    horizon,
                    gameweek,
                    squad,
                    transfers_in,
                    transfers_out,
                    bank,
                    free_transfer_state,
                    hits,
                    mechanics.submitted_ev,
                )
            )
            exact_objective += (
                mechanics.submitted_ev
                - rules.transfer_hit_cost * hits
            )
            free_transfer_state = min(
                max_free_transfers,
                max(
                    1,
                    free_transfer_state - transfers_made + 1,
                ),
            )
        return tuple(weeks), float(exact_objective)

    first = solve(-expected_value)
    if first.x is None:
        return TransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            None,
            {"message": str(first.message)},
        )

    primary_optimum = float(expected_value @ first.x)
    regret_points = max(
        0.25,
        abs(primary_optimum) * float(candidate_regret_fraction),
    )
    shortlist_floor = primary_optimum - regret_points

    exclusions = []
    candidates = []
    current = first
    shortlist_complete = False
    next_message = None

    for generation_rank in range(1, int(candidate_limit) + 1):
        if current.x is None:
            shortlist_complete = True
            break

        approximate_objective = float(expected_value @ current.x)
        if approximate_objective < shortlist_floor - 1e-7:
            shortlist_complete = True
            break

        preserve_candidate_objective = (
            objective_coefficients,
            approximate_objective - 1e-7,
            np.inf,
        )
        secondary = solve(
            transfer_count_objective,
            extras=tuple(exclusions) + (preserve_candidate_objective,),
        )
        solution = (
            secondary.x
            if secondary.x is not None
            else current.x
        )
        actual_approximate = float(expected_value @ solution)
        weeks, exact_objective = decode(solution)
        path_key = tuple(week.squad_ids for week in weeks)
        candidates.append(
            {
                "generation_rank": generation_rank,
                "approximate_objective": actual_approximate,
                "exact_objective": exact_objective,
                "weeks": weeks,
                "solution": solution,
                "path_key": path_key,
                "primary_message": str(current.message),
                "secondary_message": str(secondary.message),
            }
        )

        exclusion = path_exclusion(solution)
        exclusions.append(exclusion)
        current = solve(
            -expected_value,
            extras=tuple(exclusions),
        )
        next_message = str(current.message)
        if current.x is None:
            shortlist_complete = True
            break
        if float(expected_value @ current.x) < shortlist_floor - 1e-7:
            shortlist_complete = True
            break

    if not candidates:
        return TransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            primary_optimum,
            {"message": "transfer shortlist produced no decodable candidate"},
        )

    if shortlist_complete:
        selected = min(
            candidates,
            key=lambda candidate: (
                -candidate["exact_objective"],
                candidate["path_key"],
            ),
        )
        selection_policy = "EXACT_CONTINGENCY_CERTIFIED_SHORTLIST"
        reason = None
    else:
        selected = candidates[0]
        selection_policy = "PRIMARY_MAX_EV_FALLBACK_UNCERTIFIED_SHORTLIST"
        reason = (
            "exact contingency shortlist reached its candidate limit before "
            "the configured primary-objective regret band was exhausted; "
            "primary max-EV path retained"
        )

    weeks = selected["weeks"]
    first_week = weeks[0]
    decision = decision_from_fixed_squad(
        official,
        surface,
        first_week.squad_ids,
        horizon=1,
        transfers_in=first_week.transfers_in,
        transfers_out=first_week.transfers_out,
        transfer_hits=first_week.hits,
        decision_mode="TRANSFER_HORIZON",
        xi_excluded=excluded_h1,
    )

    solver = {
        "primary_message": str(first.message),
        "secondary_message": selected["secondary_message"],
        "transfer_tiebreak": True,
        "selection_policy": selection_policy,
        "shortlist_complete": shortlist_complete,
        "candidate_count": len(candidates),
        "candidate_limit": int(candidate_limit),
        "candidate_regret_fraction": float(candidate_regret_fraction),
        "candidate_regret_points": float(regret_points),
        "shortlist_floor": float(shortlist_floor),
        "selected_generation_rank": int(selected["generation_rank"]),
        "selected_approximate_objective": float(
            selected["approximate_objective"]
        ),
        "selected_exact_objective": float(selected["exact_objective"]),
        "next_candidate_message": next_message,
        "candidate_objectives": [
            {
                "generation_rank": int(candidate["generation_rank"]),
                "approximate_objective": float(
                    candidate["approximate_objective"]
                ),
                "exact_objective": float(candidate["exact_objective"]),
            }
            for candidate in candidates
        ],
    }
    if reason:
        solver["reason"] = reason

    return TransferOptimisationResult(
        decision,
        tuple(weeks),
        "OPTIMAL",
        primary_optimum,
        solver,
    )
