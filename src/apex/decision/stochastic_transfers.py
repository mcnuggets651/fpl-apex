from __future__ import annotations

from dataclasses import dataclass, replace

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
    derive_next_free_transfers,
    season_rules,
)

from .mechanics import best_fixed_squad_mechanics, decision_from_fixed_squad, xp_map
from .price_information_tree import PriceInformationTree, build_price_information_tree
from .price_scenarios import PriceScenario
from .price_transitions import (
    PriceStateError,
    TransferPriceState,
    apply_transfer_price_transition,
    fpl_selling_price_tenths,
)
from .transfers import optimise_transfer_horizon


@dataclass(frozen=True)
class StochasticTransferNodeDecision:
    node_id: str
    parent_id: str | None
    horizon: int
    probability: float
    squad_ids: tuple[int, ...]
    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    bank_tenths: int
    free_transfers: int
    hits: int
    submitted_ev: float
    purchase_prices_tenths: tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class StochasticTransferOptimisationResult:
    decision: SystemDecision | None
    node_decisions: tuple[StochasticTransferNodeDecision, ...]
    status: str
    expected_objective: float | None
    solver: dict
    information_tree: PriceInformationTree | None = None


def _current_prices(official: OfficialSnapshot) -> dict[int, int]:
    return {
        int(player.element_id): int(player.price_tenths)
        for player in official.players
    }


def _wrap_deterministic_result(
    official: OfficialSnapshot,
    team: TeamState,
    tree: PriceInformationTree,
    deterministic,
) -> StochasticTransferOptimisationResult:
    if not deterministic.weeks:
        return StochasticTransferOptimisationResult(
            deterministic.decision,
            (),
            deterministic.status,
            deterministic.primary_objective,
            {
                "mode": "DETERMINISTIC_COMPATIBILITY",
                "single_milp": deterministic.status == "OPTIMAL",
                "reason": deterministic.solver.get("reason"),
                "delegated_status": deterministic.status,
            },
            tree,
        )

    current_prices = _current_prices(official)
    state = TransferPriceState.from_team_state(team, current_prices)
    node_decisions: list[StochasticTransferNodeDecision] = []
    exact_objective = 0.0
    rules = season_rules(official.season)

    for week in deterministic.weeks:
        nodes = tree.nodes_for_horizon(week.horizon)
        if len(nodes) != 1:
            raise PriceStateError(
                "deterministic compatibility requires one price node per horizon"
            )
        node = nodes[0]
        market = node.market_price_map()
        transition = apply_transfer_price_transition(
            state,
            transfers_in=tuple(map(int, week.transfers_in)),
            transfers_out=tuple(map(int, week.transfers_out)),
            market_prices_tenths=market,
        )
        state = transition.state
        if state.bank_tenths != int(week.bank_tenths):
            raise PriceStateError(
                "deterministic compatibility bank disagrees with exact price replay"
            )
        node_decisions.append(
            StochasticTransferNodeDecision(
                node_id=node.node_id,
                parent_id=node.parent_id,
                horizon=int(week.horizon),
                probability=float(node.probability),
                squad_ids=tuple(map(int, week.squad_ids)),
                transfers_in=tuple(map(int, week.transfers_in)),
                transfers_out=tuple(map(int, week.transfers_out)),
                bank_tenths=int(week.bank_tenths),
                free_transfers=int(week.free_transfers),
                hits=int(week.hits),
                submitted_ev=float(week.submitted_ev),
                purchase_prices_tenths=state.purchase_prices_tenths,
            )
        )
        exact_objective += (
            float(week.submitted_ev)
            - rules.transfer_hit_cost * int(week.hits)
        )

    return StochasticTransferOptimisationResult(
        deterministic.decision,
        tuple(node_decisions),
        deterministic.status,
        float(exact_objective),
        {
            "mode": "DETERMINISTIC_COMPATIBILITY",
            "single_milp": True,
            "delegated_status": deterministic.status,
            "delegated_selection_policy": deterministic.solver.get("selection_policy"),
            "node_count": len(node_decisions),
        },
        tree,
    )


def optimise_stochastic_transfer_policy(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    team: TeamState,
    scenarios: tuple[PriceScenario, ...],
    *,
    max_horizon: int,
    excluded_h1: frozenset[int] = frozenset(),
) -> StochasticTransferOptimisationResult:
    """Optimise one non-anticipative transfer policy over a price information tree.

    There is one MILP call for a genuinely branching/price-changing tree.
    Decisions are indexed by information nodes rather than full scenarios, so
    future actions can adapt only after the corresponding price history has been
    observed. Purchase-price basis is an endogenous binary state: a future buy
    records the actual node market price and every later sale uses exact FPL
    half-profit/full-loss mechanics from that basis.

    When every in-horizon node is exactly today's market price, this function
    delegates to the accepted deterministic optimiser with candidate_limit=1.
    That compatibility path guarantees the zero-price-variance decision signature
    without a second solve.
    """
    if isinstance(max_horizon, bool) or not isinstance(max_horizon, int):
        raise PriceStateError("max_horizon must be an integer")
    if max_horizon < 1:
        raise PriceStateError("max_horizon must be positive")

    horizons = list(range(1, max_horizon + 1))
    xp = {horizon: xp_map(surface, horizon) for horizon in horizons}
    universe = set.intersection(*(set(xp[horizon]) for horizon in horizons))
    players = [
        player
        for player in official.players
        if player.element_id in universe
        and (player.can_transact or player.element_id in team.squad_ids)
    ]
    player_ids = [int(player.element_id) for player in players]
    by_player = {player_id: index for index, player_id in enumerate(player_ids)}
    if not set(team.squad_ids).issubset(by_player):
        return StochasticTransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            None,
            {"reason": "current squad missing from forecast universe"},
        )

    tree = build_price_information_tree(
        official,
        scenarios,
        max_horizon=max_horizon,
        relevant_element_ids=tuple(player_ids),
    )
    current_prices = _current_prices(official)

    # Preserve the exact accepted deterministic semantics when price variance is
    # absent throughout the decision horizon.
    flat_tree = all(
        all(
            int(price) == int(current_prices[element_id])
            for element_id, price in node.market_prices_tenths
        )
        for node in tree.nodes
    )
    if flat_tree or max_horizon < 2:
        deterministic = optimise_transfer_horizon(
            official,
            surface,
            team,
            max_horizon=max_horizon,
            excluded_h1=excluded_h1,
            candidate_limit=1,
        )
        return _wrap_deterministic_result(
            official,
            team,
            tree,
            deterministic,
        )

    if (
        not team.state_complete_for_transfers
        or len(team.purchase_prices_tenths) != 15
        or len(team.selling_prices_tenths) != 15
    ):
        deterministic = optimise_transfer_horizon(
            official,
            surface,
            team,
            max_horizon=max_horizon,
            excluded_h1=excluded_h1,
            candidate_limit=1,
        )
        return StochasticTransferOptimisationResult(
            deterministic.decision,
            (),
            "WITHHELD_TEAM_STATE_INCOMPLETE",
            deterministic.primary_objective,
            {
                "mode": "STOCHASTIC_WITHHELD",
                "single_milp": False,
                "reason": "exact purchase/selling-price state incomplete",
            },
            tree,
        )

    initial_price_state = TransferPriceState.from_team_state(
        team,
        current_prices,
    )
    initial_purchase = initial_price_state.purchase_price_map()

    rules = season_rules(official.season)
    max_free_transfers = rules.max_rolled_free_transfers
    if not 0 <= int(team.free_transfers) <= max_free_transfers:
        return StochasticTransferOptimisationResult(
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
            tree,
        )

    nodes = list(tree.nodes)
    node_index = {node.node_id: index for index, node in enumerate(nodes)}
    player_count = len(players)
    node_count = len(nodes)
    block = player_count * node_count

    squad_base = 0
    xi_base = block
    captain_base = 2 * block
    transfer_in_base = 3 * block
    transfer_out_base = 4 * block
    bank_base = 5 * block

    free_transfer_state_count = max_free_transfers + 1
    max_transfers = 16
    state_base = bank_base + node_count
    basis_base = (
        state_base
        + node_count * free_transfer_state_count * max_transfers
    )

    def player_var(base: int, p_index: int, n_index: int) -> int:
        return base + n_index * player_count + p_index

    def state_var(n_index: int, free_transfers: int, transfers: int) -> int:
        return (
            state_base
            + (n_index * free_transfer_state_count + free_transfers)
            * max_transfers
            + transfers
        )

    market_by_node = {
        node.node_id: node.market_price_map()
        for node in nodes
    }
    basis_values: dict[int, tuple[int, ...]] = {}
    for player_id in player_ids:
        values = {
            int(market_by_node[node.node_id][player_id])
            for node in nodes
        }
        if player_id in initial_purchase:
            values.add(int(initial_purchase[player_id]))
        basis_values[player_id] = tuple(sorted(values))

    post_basis_var: dict[tuple[int, int, int], int] = {}
    sell_basis_var: dict[tuple[int, int, int], int] = {}
    cursor = basis_base
    for n_index, _node in enumerate(nodes):
        for player_id in player_ids:
            for basis in basis_values[player_id]:
                post_basis_var[(n_index, player_id, basis)] = cursor
                cursor += 1
    for n_index, _node in enumerate(nodes):
        for player_id in player_ids:
            for basis in basis_values[player_id]:
                sell_basis_var[(n_index, player_id, basis)] = cursor
                cursor += 1
    variable_count = cursor

    expected_value = np.zeros(variable_count)
    for n_index, node in enumerate(nodes):
        horizon = int(node.horizon)
        probability = float(node.probability)
        for p_index, player_id in enumerate(player_ids):
            points = float(xp[horizon][player_id])
            expected_value[
                player_var(xi_base, p_index, n_index)
            ] += probability * points
            expected_value[
                player_var(captain_base, p_index, n_index)
            ] += probability * points
        for free_transfers in range(max_free_transfers + 1):
            for transfers in range(max_transfers):
                expected_value[
                    state_var(n_index, free_transfers, transfers)
                ] -= (
                    probability
                    * rules.transfer_hit_cost
                    * max(0, transfers - free_transfers)
                )

    rows: list[dict[int, float]] = []
    lower_bounds: list[float] = []
    upper_bounds: list[float] = []

    def add(coefficients: dict[int, float], lower: float, upper: float) -> None:
        rows.append(coefficients)
        lower_bounds.append(lower)
        upper_bounds.append(upper)

    initial_owned = set(map(int, team.squad_ids))
    root_id = tree.root_id

    for n_index, node in enumerate(nodes):
        horizon = int(node.horizon)
        market = market_by_node[node.node_id]
        parent_index = (
            None
            if node.parent_id is None
            else node_index[node.parent_id]
        )

        add(
            {
                player_var(squad_base, p_index, n_index): 1
                for p_index in range(player_count)
            },
            15,
            15,
        )
        add(
            {
                player_var(xi_base, p_index, n_index): 1
                for p_index in range(player_count)
            },
            11,
            11,
        )
        add(
            {
                player_var(captain_base, p_index, n_index): 1
                for p_index in range(player_count)
            },
            1,
            1,
        )

        for position, required in SQUAD_COUNTS.items():
            indices = [
                p_index
                for p_index, player in enumerate(players)
                if player.position == position
            ]
            add(
                {
                    player_var(squad_base, p_index, n_index): 1
                    for p_index in indices
                },
                required,
                required,
            )
            add(
                {
                    player_var(xi_base, p_index, n_index): 1
                    for p_index in indices
                },
                XI_MIN[position],
                XI_MAX[position],
            )

        for team_id in sorted({player.team_id for player in players}):
            add(
                {
                    player_var(squad_base, p_index, n_index): 1
                    for p_index, player in enumerate(players)
                    if player.team_id == team_id
                },
                -np.inf,
                MAX_PER_TEAM,
            )

        for p_index, player_id in enumerate(player_ids):
            squad = player_var(squad_base, p_index, n_index)
            xi = player_var(xi_base, p_index, n_index)
            captain = player_var(captain_base, p_index, n_index)
            transfer_in = player_var(transfer_in_base, p_index, n_index)
            transfer_out = player_var(transfer_out_base, p_index, n_index)

            if node.node_id == root_id and player_id in excluded_h1:
                add({xi: 1}, 0, 0)
                add({captain: 1}, 0, 0)

            add({xi: 1, squad: -1}, -np.inf, 0)
            add({captain: 1, xi: -1}, -np.inf, 0)
            add({transfer_in: 1, transfer_out: 1}, -np.inf, 1)

            if parent_index is None:
                initial = 1 if player_id in initial_owned else 0
                add(
                    {
                        squad: 1,
                        transfer_in: -1,
                        transfer_out: 1,
                    },
                    initial,
                    initial,
                )
            else:
                parent_squad = player_var(
                    squad_base,
                    p_index,
                    parent_index,
                )
                add(
                    {
                        squad: 1,
                        parent_squad: -1,
                        transfer_in: -1,
                        transfer_out: 1,
                    },
                    0,
                    0,
                )

            basis_vars = {
                basis: post_basis_var[(n_index, player_id, basis)]
                for basis in basis_values[player_id]
            }
            sell_vars = {
                basis: sell_basis_var[(n_index, player_id, basis)]
                for basis in basis_values[player_id]
            }
            post_sum = {var: 1 for var in basis_vars.values()}
            post_sum[squad] = -1
            add(post_sum, 0, 0)

            sell_sum = {var: 1 for var in sell_vars.values()}
            sell_sum[transfer_out] = -1
            add(sell_sum, 0, 0)

            buy_basis = int(market[player_id])
            for basis in basis_values[player_id]:
                post = basis_vars[basis]
                sell = sell_vars[basis]
                coefficients = {
                    post: 1,
                    sell: 1,
                }
                if basis == buy_basis:
                    coefficients[transfer_in] = -1

                if parent_index is None:
                    pre = (
                        1
                        if player_id in initial_purchase
                        and int(initial_purchase[player_id]) == basis
                        else 0
                    )
                    add(coefficients, pre, pre)
                    if not pre:
                        add({sell: 1}, 0, 0)
                else:
                    parent_post = post_basis_var[
                        (parent_index, player_id, basis)
                    ]
                    coefficients[parent_post] = -1
                    add(coefficients, 0, 0)
                    add({sell: 1, parent_post: -1}, -np.inf, 0)

        balance = {
            player_var(transfer_in_base, p_index, n_index): 1
            for p_index in range(player_count)
        }
        balance.update(
            {
                player_var(transfer_out_base, p_index, n_index): -1
                for p_index in range(player_count)
            }
        )
        add(balance, 0, 0)

        add(
            {
                state_var(n_index, free_transfers, transfers): 1
                for free_transfers in range(max_free_transfers + 1)
                for transfers in range(max_transfers)
            },
            1,
            1,
        )
        transfer_counter = {
            player_var(transfer_in_base, p_index, n_index): 1
            for p_index in range(player_count)
        }
        transfer_counter.update(
            {
                state_var(n_index, free_transfers, transfers): -transfers
                for free_transfers in range(max_free_transfers + 1)
                for transfers in range(max_transfers)
            }
        )
        add(transfer_counter, 0, 0)

        if parent_index is None:
            add(
                {
                    state_var(
                        n_index,
                        int(team.free_transfers),
                        transfers,
                    ): 1
                    for transfers in range(max_transfers)
                },
                1,
                1,
            )
        else:
            current_gameweek = int(team.published_gw) + horizon
            for current_ft in range(max_free_transfers + 1):
                coefficients = {
                    state_var(n_index, current_ft, transfers): 1
                    for transfers in range(max_transfers)
                }
                for previous_ft in range(max_free_transfers + 1):
                    for previous_transfers in range(max_transfers):
                        next_ft = derive_next_free_transfers(
                            previous_ft,
                            previous_transfers,
                            next_gameweek=current_gameweek,
                            rules=rules,
                        )
                        if next_ft == current_ft:
                            parent_state = state_var(
                                parent_index,
                                previous_ft,
                                previous_transfers,
                            )
                            coefficients[parent_state] = (
                                coefficients.get(parent_state, 0) - 1
                            )
                add(coefficients, 0, 0)

        cash: dict[int, float] = {bank_base + n_index: 1}
        for p_index, player_id in enumerate(player_ids):
            transfer_in = player_var(
                transfer_in_base,
                p_index,
                n_index,
            )
            cash[transfer_in] = float(market[player_id])
            for basis in basis_values[player_id]:
                sell = sell_basis_var[(n_index, player_id, basis)]
                cash[sell] = -float(
                    fpl_selling_price_tenths(
                        basis,
                        int(market[player_id]),
                    )
                )
        if parent_index is None:
            add(cash, int(team.bank_tenths), int(team.bank_tenths))
        else:
            cash[bank_base + parent_index] = -1
            add(cash, 0, 0)

    lower_variable_bounds = np.zeros(variable_count)
    upper_variable_bounds = np.ones(variable_count)
    integrality = np.ones(variable_count, dtype=int)
    for n_index in range(node_count):
        lower_variable_bounds[bank_base + n_index] = 0
        upper_variable_bounds[bank_base + n_index] = 2000
        integrality[bank_base + n_index] = 0

    matrix = lil_matrix((len(rows), variable_count))
    for row_index, coefficients in enumerate(rows):
        for column, value in coefficients.items():
            matrix[row_index, column] = value

    result = milp(
        c=-expected_value,
        integrality=integrality,
        bounds=Bounds(
            lower_variable_bounds,
            upper_variable_bounds,
        ),
        constraints=LinearConstraint(
            matrix.tocsr(),
            np.asarray(lower_bounds),
            np.asarray(upper_bounds),
        ),
        options={"time_limit": 120, "mip_rel_gap": 1e-09},
    )
    if result.x is None:
        return StochasticTransferOptimisationResult(
            None,
            (),
            "INFEASIBLE",
            None,
            {
                "mode": "STOCHASTIC_PRICE_TREE",
                "single_milp": True,
                "message": str(result.message),
                "node_count": node_count,
                "scenario_count": len(scenarios),
            },
            tree,
        )

    solution = result.x
    decoded: list[StochasticTransferNodeDecision] = []
    exact_expected_objective = 0.0

    for n_index, node in enumerate(nodes):
        horizon = int(node.horizon)
        squad = tuple(
            sorted(
                player_ids[p_index]
                for p_index in range(player_count)
                if solution[
                    player_var(squad_base, p_index, n_index)
                ] > 0.5
            )
        )
        transfers_in = tuple(
            sorted(
                player_ids[p_index]
                for p_index in range(player_count)
                if solution[
                    player_var(transfer_in_base, p_index, n_index)
                ] > 0.5
            )
        )
        transfers_out = tuple(
            sorted(
                player_ids[p_index]
                for p_index in range(player_count)
                if solution[
                    player_var(transfer_out_base, p_index, n_index)
                ] > 0.5
            )
        )
        selected_states = [
            (free_transfers, transfers)
            for free_transfers in range(max_free_transfers + 1)
            for transfers in range(max_transfers)
            if solution[
                state_var(n_index, free_transfers, transfers)
            ] > 0.5
        ]
        if len(selected_states) != 1:
            raise RuntimeError(
                f"stochastic transfer node {node.node_id} has invalid FT state"
            )
        free_transfers, transfers_made = selected_states[0]
        if transfers_made != len(transfers_in):
            raise RuntimeError(
                f"stochastic transfer node {node.node_id} transfer count mismatch"
            )
        hits = max(0, transfers_made - free_transfers)
        bank = int(round(solution[bank_base + n_index]))
        purchase_pairs = []
        for player_id in squad:
            selected_basis = [
                basis
                for basis in basis_values[player_id]
                if solution[
                    post_basis_var[(n_index, player_id, basis)]
                ] > 0.5
            ]
            if len(selected_basis) != 1:
                raise RuntimeError(
                    f"stochastic transfer node {node.node_id} has invalid purchase basis "
                    f"for element {player_id}"
                )
            purchase_pairs.append((player_id, int(selected_basis[0])))

        mechanics = best_fixed_squad_mechanics(
            official,
            surface,
            squad,
            horizon=horizon,
            xi_excluded=(
                excluded_h1
                if node.node_id == root_id
                else frozenset()
            ),
        )
        submitted_ev = float(mechanics.submitted_ev)
        exact_expected_objective += float(node.probability) * (
            submitted_ev - rules.transfer_hit_cost * hits
        )
        decoded.append(
            StochasticTransferNodeDecision(
                node_id=node.node_id,
                parent_id=node.parent_id,
                horizon=horizon,
                probability=float(node.probability),
                squad_ids=squad,
                transfers_in=transfers_in,
                transfers_out=transfers_out,
                bank_tenths=bank,
                free_transfers=int(free_transfers),
                hits=int(hits),
                submitted_ev=submitted_ev,
                purchase_prices_tenths=tuple(sorted(purchase_pairs)),
            )
        )

    root_decoded = next(
        decision
        for decision in decoded
        if decision.node_id == root_id
    )
    decision = decision_from_fixed_squad(
        official,
        surface,
        root_decoded.squad_ids,
        horizon=1,
        transfers_in=root_decoded.transfers_in,
        transfers_out=root_decoded.transfers_out,
        transfer_hits=root_decoded.hits,
        decision_mode="STOCHASTIC_TRANSFER_HORIZON",
        xi_excluded=excluded_h1,
    )
    decision = replace(decision, horizon=int(max_horizon))

    approximate_objective = float(expected_value @ solution)
    return StochasticTransferOptimisationResult(
        decision,
        tuple(decoded),
        "OPTIMAL",
        float(exact_expected_objective),
        {
            "mode": "STOCHASTIC_PRICE_TREE",
            "single_milp": True,
            "node_count": node_count,
            "scenario_count": len(scenarios),
            "approximate_expected_objective": approximate_objective,
            "exact_expected_objective": float(exact_expected_objective),
            "message": str(result.message),
        },
        tree,
    )
