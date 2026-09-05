from __future__ import annotations

from dataclasses import replace

import numpy as np
from scipy.optimize import LinearConstraint
from scipy.sparse import lil_matrix, vstack

from apex.domain.models import OfficialSnapshot, ProductionProjectionSurface, TeamState

from . import stochastic_transfers as stochastic_solver
from .price_scenarios import PriceScenario
from .price_transitions import PriceStateError
from .stochastic_counterfactuals import (
    _COUNTERFACTUAL_SOLVE_LOCK,
    _solver_players_and_tree,
)


def optimise_stochastic_transfer_policy_for_root_transfer_count(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    team: TeamState,
    scenarios: tuple[PriceScenario, ...],
    *,
    max_horizon: int,
    root_transfer_count: int,
    excluded_h1: frozenset[int] = frozenset(),
):
    """Exact diagnostic optimum conditional on the H1 transfer count.

    The canonical D033 stochastic solver remains the only optimiser. This seam
    injects one equality constraint on the H1 transfer-in binaries so the solver
    chooses the best legal root action among all actions using exactly
    ``root_transfer_count`` transfers. Existing transfer-balance constraints force
    the same number of transfers out. Every H2+ decision, price transition, bank,
    purchase/selling-price mechanic, free-transfer mechanic, hit deduction and
    expected-FPL-points term remains owned by the canonical stochastic solver.

    The seam is diagnostic-only, requires a non-flat stochastic price tree, runs
    exactly one underlying MILP and exposes no manager-private player IDs in
    diagnostics. It exists so owner-facing canaries can compare ROLL, free-transfer
    counts and explicit hit bands on the same evidence without enumerating or
    hand-selecting player combinations.
    """
    if isinstance(root_transfer_count, bool) or not isinstance(root_transfer_count, int):
        raise PriceStateError("root_transfer_count must be an integer")
    if root_transfer_count < 0 or root_transfer_count > 15:
        raise PriceStateError("root_transfer_count must be between 0 and 15")

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

    player_ids, _transact, tree, flat_tree = _solver_players_and_tree(
        official,
        surface,
        team,
        scenarios,
        max_horizon=max_horizon,
    )
    if flat_tree:
        raise PriceStateError(
            "root transfer-count counterfactuals require a non-flat stochastic price tree"
        )

    nodes = list(tree.nodes)
    root_indices = [index for index, node in enumerate(nodes) if node.node_id == tree.root_id]
    if len(root_indices) != 1:
        raise PriceStateError("stochastic information tree must contain exactly one root")
    root_index = root_indices[0]
    player_count = len(player_ids)
    node_count = len(nodes)
    block = player_count * node_count
    transfer_in_base = 3 * block

    original_milp = stochastic_solver.milp
    observed_calls = 0

    def constrained_milp(*args, **kwargs):
        nonlocal observed_calls
        observed_calls += 1
        if observed_calls != 1:
            raise RuntimeError(
                "transfer-count counterfactual unexpectedly invoked MILP more than once"
            )

        c = kwargs.get("c")
        constraints = kwargs.get("constraints")
        if c is None or not isinstance(constraints, LinearConstraint):
            raise RuntimeError("unexpected stochastic MILP call signature")
        variable_count = len(c)
        extra = lil_matrix((1, variable_count))
        for p_index in range(player_count):
            transfer_in = transfer_in_base + root_index * player_count + p_index
            if transfer_in >= variable_count:
                raise RuntimeError("stochastic MILP variable layout changed")
            extra[0, transfer_in] = 1.0

        matrix = vstack([constraints.A, extra.tocsr()], format="csr")
        target = np.asarray([float(root_transfer_count)])
        lower = np.concatenate([np.asarray(constraints.lb), target])
        upper = np.concatenate([np.asarray(constraints.ub), target])
        constrained = LinearConstraint(matrix, lower, upper)
        return original_milp(
            *args,
            **{**kwargs, "constraints": constrained},
        )

    with _COUNTERFACTUAL_SOLVE_LOCK:
        if stochastic_solver.milp is not original_milp:
            raise RuntimeError(
                "stochastic MILP dependency changed before transfer-count counterfactual solve"
            )
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
            "transfer-count counterfactual did not execute exactly one MILP"
        )
    if result.status == "OPTIMAL":
        if result.decision is None:
            raise RuntimeError("optimal transfer-count counterfactual has no root decision")
        if len(tuple(result.decision.transfers_in)) != root_transfer_count:
            raise RuntimeError("root transfer-count constraint was not preserved")
        if len(tuple(result.decision.transfers_out)) != root_transfer_count:
            raise RuntimeError("root transfer balance disagrees with constrained count")

    diagnostics = dict(result.solver)
    diagnostics["counterfactual_root_transfer_count_pinned"] = True
    diagnostics["counterfactual_root_transfer_count"] = root_transfer_count
    diagnostics["counterfactual_diagnostic_only"] = True
    return replace(result, solver=diagnostics)
