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
from apex.domain.rules import MAX_PER_TEAM, SQUAD_COUNTS, XI_MAX, XI_MIN, season_rules

from .mechanics import decision_from_fixed_squad, xp_map


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
) -> TransferOptimisationResult:
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
    by_player = {player_id: index for index, player_id in enumerate(player_ids)}
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
    max_free_transfers = season_rules(
        official.season
    ).max_rolled_free_transfers
    max_transfers = 16
    state_base = bank_base + horizon_count
    variable_count = (
        state_base
        + horizon_count * max_free_transfers * max_transfers
    )

    def player_var(base, index, period):
        return base + period * player_count + index

    def state_var(period, free_transfers, transfers):
        return (
            state_base
            + (period * max_free_transfers + (free_transfers - 1))
            * max_transfers
            + transfers
        )

    expected_value = np.zeros(variable_count)
    transfer_count_objective = np.zeros(variable_count)
    rules = season_rules(official.season)
    for period, horizon in enumerate(horizons):
        for index, player_id in enumerate(player_ids):
            expected_value[player_var(xi_base, index, period)] += xp[horizon][
                player_id
            ]
            expected_value[
                player_var(captain_base, index, period)
            ] += xp[horizon][player_id]
            transfer_count_objective[
                player_var(transfer_in_base, index, period)
            ] = 1
        for free_transfers in range(1, max_free_transfers + 1):
            for transfers in range(max_transfers):
                expected_value[
                    state_var(period, free_transfers, transfers)
                ] -= rules.transfer_hit_cost * max(
                    0, transfers - free_transfers
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
                for free_transfers in range(1, max_free_transfers + 1)
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
                for free_transfers in range(1, max_free_transfers + 1)
                for transfers in range(max_transfers)
            }
        )
        add(transfer_counter, 0, 0)
        if period == 0:
            add(
                {
                    state_var(period, team.free_transfers, transfers): 1
                    for transfers in range(max_transfers)
                },
                1,
                1,
            )
        else:
            for current_ft in range(1, max_free_transfers + 1):
                coefficients = {
                    state_var(period, current_ft, transfers): 1
                    for transfers in range(max_transfers)
                }
                for previous_ft in range(1, max_free_transfers + 1):
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

    def solve(objective, extra=None):
        solve_rows = list(rows)
        solve_lower = list(lower_bounds)
        solve_upper = list(upper_bounds)
        if extra:
            coefficients, extra_lower, extra_upper = extra
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
            bounds=Bounds(lower_variable_bounds, upper_variable_bounds),
            constraints=LinearConstraint(
                matrix.tocsr(),
                np.asarray(solve_lower),
                np.asarray(solve_upper),
            ),
            options={"time_limit": 120, "mip_rel_gap": 1e-09},
        )

    first = solve(-expected_value)
    if first.x is None:
        return TransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            None,
            {"message": str(first.message)},
        )
    optimum = float(expected_value @ first.x)
    extra = (
        {
            index: float(value)
            for index, value in enumerate(expected_value)
            if abs(value) > 1e-15
        },
        optimum - 1e-07,
        np.inf,
    )
    second = solve(transfer_count_objective, extra)
    solution = second.x if second.x is not None else first.x

    weeks = []
    free_transfer_state = team.free_transfers
    for period, horizon in enumerate(horizons):
        squad = tuple(
            sorted(
                player_ids[index]
                for index in range(player_count)
                if solution[player_var(squad_base, index, period)] > 0.5
            )
        )
        transfers_in = tuple(
            sorted(
                player_ids[index]
                for index in range(player_count)
                if solution[
                    player_var(transfer_in_base, index, period)
                ]
                > 0.5
            )
        )
        transfers_out = tuple(
            sorted(
                player_ids[index]
                for index in range(player_count)
                if solution[
                    player_var(transfer_out_base, index, period)
                ]
                > 0.5
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
        week_decision = decision_from_fixed_squad(
            official,
            surface,
            squad,
            horizon=horizon,
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
                week_decision.objective,
            )
        )
        free_transfer_state = min(
            max_free_transfers,
            max(1, free_transfer_state - transfers_made + 1),
        )

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
    return TransferOptimisationResult(
        decision,
        tuple(weeks),
        "OPTIMAL",
        optimum,
        {
            "primary_message": str(first.message),
            "secondary_message": str(second.message),
            "transfer_tiebreak": True,
        },
    )
