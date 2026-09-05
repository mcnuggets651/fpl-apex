from __future__ import annotations

from dataclasses import replace
from threading import RLock

import numpy as np
from scipy.optimize import LinearConstraint
from scipy.sparse import lil_matrix, vstack

from apex.domain.models import OfficialSnapshot, ProductionProjectionSurface, TeamState

from . import stochastic_transfers as stochastic_solver
from .mechanics import xp_map
from .price_information_tree import PriceInformationTree, build_price_information_tree
from .price_scenarios import PriceScenario
from .price_transitions import PriceStateError


_COUNTERFACTUAL_SOLVE_LOCK = RLock()


def _normalise_root_action(
    transfers_in: tuple[int, ...],
    transfers_out: tuple[int, ...],
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    incoming = tuple(sorted(map(int, transfers_in)))
    outgoing = tuple(sorted(map(int, transfers_out)))
    if len(incoming) != len(outgoing):
        raise PriceStateError("root transfer-in and transfer-out counts must match")
    if len(incoming) != len(set(incoming)) or len(outgoing) != len(set(outgoing)):
        raise PriceStateError("root transfer IDs must be unique")
    if set(incoming) & set(outgoing):
        raise PriceStateError("the same element cannot be transferred in and out at root")
    return incoming, outgoing


def _solver_players_and_tree(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    team: TeamState,
    scenarios: tuple[PriceScenario, ...],
    *,
    max_horizon: int,
) -> tuple[tuple[int, ...], dict[int, bool], PriceInformationTree, bool]:
    if isinstance(max_horizon, bool) or not isinstance(max_horizon, int):
        raise PriceStateError("max_horizon must be an integer")
    if max_horizon < 2:
        raise PriceStateError("root-action counterfactuals require H2+ planning")

    horizons = list(range(1, max_horizon + 1))
    xp = {horizon: xp_map(surface, horizon) for horizon in horizons}
    universe = set.intersection(*(set(xp[horizon]) for horizon in horizons))
    players = tuple(
        player
        for player in official.players
        if player.element_id in universe
        and (player.can_transact or player.element_id in team.squad_ids)
    )
    player_ids = tuple(int(player.element_id) for player in players)
    if not set(map(int, team.squad_ids)).issubset(player_ids):
        raise PriceStateError("current squad missing from stochastic forecast universe")

    tree = build_price_information_tree(
        official,
        scenarios,
        max_horizon=max_horizon,
        relevant_element_ids=player_ids,
    )
    current_prices = {
        int(player.element_id): int(player.price_tenths)
        for player in official.players
    }
    flat_tree = all(
        all(
            int(price) == int(current_prices[element_id])
            for element_id, price in node.market_prices_tenths
        )
        for node in tree.nodes
    )
    transact = {int(player.element_id): bool(player.can_transact) for player in players}
    return player_ids, transact, tree, flat_tree


def optimise_stochastic_transfer_policy_for_root_action(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    team: TeamState,
    scenarios: tuple[PriceScenario, ...],
    *,
    max_horizon: int,
    root_transfers_in: tuple[int, ...],
    root_transfers_out: tuple[int, ...],
    excluded_h1: frozenset[int] = frozenset(),
):
    """Exact diagnostic counterfactual for one fixed H1 transfer action.

    This is deliberately not a second optimiser. It calls the canonical D033
    stochastic solver and adds equality constraints only to its H1 transfer-in /
    transfer-out binary variables. Every H2+ variable, price-state transition,
    exact FPL mechanic and expected-football-points objective remains owned by
    ``optimise_stochastic_transfer_policy``.

    The seam is diagnostic-only and is intended for canary comparisons such as
    ROLL versus the unconstrained stochastic root on the *same* synthetic price
    tree. It is rejected for a flat tree so the accepted deterministic
    compatibility path remains untouched. No root player IDs are copied into
    solver diagnostics.
    """
    incoming, outgoing = _normalise_root_action(
        root_transfers_in,
        root_transfers_out,
    )

    owned = set(map(int, team.squad_ids))
    if (
        not team.state_complete_for_transfers
        or len(owned) != 15
        or set(map(int, team.purchase_prices_tenths)) != owned
        or set(map(int, team.selling_prices_tenths)) != owned
    ):
        raise PriceStateError(
            "exact owner purchase/selling-price TeamState is incomplete for counterfactual"
        )

    player_ids, transact, tree, flat_tree = _solver_players_and_tree(
        official,
        surface,
        team,
        scenarios,
        max_horizon=max_horizon,
    )
    if flat_tree:
        raise PriceStateError(
            "root-action counterfactuals require a non-flat stochastic price tree"
        )

    unknown = sorted((set(incoming) | set(outgoing)) - set(player_ids))
    if unknown:
        raise PriceStateError("root action references elements outside solver universe")
    if not set(outgoing).issubset(owned):
        raise PriceStateError("root action cannot sell an unowned element")
    if set(incoming) & owned:
        raise PriceStateError("root action cannot buy an already-owned element")
    if any(not transact[element_id] for element_id in incoming):
        raise PriceStateError("root action cannot buy an untransactable element")

    nodes = list(tree.nodes)
    root_indices = [index for index, node in enumerate(nodes) if node.node_id == tree.root_id]
    if len(root_indices) != 1:
        raise PriceStateError("stochastic information tree must contain exactly one root")
    root_index = root_indices[0]
    player_count = len(player_ids)
    node_count = len(nodes)
    block = player_count * node_count
    transfer_in_base = 3 * block
    transfer_out_base = 4 * block
    incoming_set = set(incoming)
    outgoing_set = set(outgoing)

    original_milp = stochastic_solver.milp
    observed_calls = 0

    def constrained_milp(*args, **kwargs):
        nonlocal observed_calls
        observed_calls += 1
        if observed_calls != 1:
            raise RuntimeError(
                "counterfactual stochastic solve unexpectedly invoked MILP more than once"
            )

        c = kwargs.get("c")
        constraints = kwargs.get("constraints")
        if c is None or not isinstance(constraints, LinearConstraint):
            raise RuntimeError("unexpected stochastic MILP call signature")
        variable_count = len(c)
        extra = lil_matrix((2 * player_count, variable_count))
        target = np.zeros(2 * player_count)
        for p_index, element_id in enumerate(player_ids):
            transfer_in = transfer_in_base + root_index * player_count + p_index
            transfer_out = transfer_out_base + root_index * player_count + p_index
            if transfer_out >= variable_count:
                raise RuntimeError("stochastic MILP variable layout changed")
            extra[p_index, transfer_in] = 1.0
            extra[player_count + p_index, transfer_out] = 1.0
            target[p_index] = 1.0 if element_id in incoming_set else 0.0
            target[player_count + p_index] = 1.0 if element_id in outgoing_set else 0.0

        matrix = vstack([constraints.A, extra.tocsr()], format="csr")
        lower = np.concatenate([np.asarray(constraints.lb), target])
        upper = np.concatenate([np.asarray(constraints.ub), target])
        constrained = LinearConstraint(matrix, lower, upper)
        return original_milp(
            *args,
            **{**kwargs, "constraints": constrained},
        )

    # The solver module stores scipy.optimize.milp as a module-level dependency.
    # Serialise this temporary exact constraint injection so concurrent callers
    # can never observe the diagnostic replacement.
    with _COUNTERFACTUAL_SOLVE_LOCK:
        if stochastic_solver.milp is not original_milp:
            raise RuntimeError("stochastic MILP dependency changed before counterfactual solve")
        stochastic_solver.milp = constrained_milp
        try:
            result = stochastic_solver.optimise_stochastic_transfer_policy(
                official,
                surface,
                team,
                scenarios,
                max_horizon=max_horizon,
                excluded_h1=excluded_h1,
            )
        finally:
            stochastic_solver.milp = original_milp

    if observed_calls != 1:
        raise RuntimeError(
            "counterfactual stochastic solve did not execute exactly one MILP"
        )
    if result.status == "OPTIMAL":
        if result.decision is None:
            raise RuntimeError("optimal counterfactual has no root decision")
        if tuple(sorted(map(int, result.decision.transfers_in))) != incoming:
            raise RuntimeError("counterfactual root transfer-in constraint was not preserved")
        if tuple(sorted(map(int, result.decision.transfers_out))) != outgoing:
            raise RuntimeError("counterfactual root transfer-out constraint was not preserved")

    diagnostics = dict(result.solver)
    diagnostics["counterfactual_root_pinned"] = True
    diagnostics["counterfactual_root_transfer_count"] = len(incoming)
    diagnostics["counterfactual_diagnostic_only"] = True
    return replace(result, solver=diagnostics)
