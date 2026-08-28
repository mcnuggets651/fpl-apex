from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex.domain.models import (
    OfficialSnapshot,
    ProductionProjectionSurface,
    SystemDecision,
)
from apex.domain.rules import (
    BUDGET_TENTHS,
    MAX_PER_TEAM,
    SQUAD_COUNTS,
    XI_MAX,
    XI_MIN,
)

from .mechanics import decision_from_fixed_squad, xp_map


@dataclass(frozen=True)
class OptimisationResult:
    decision: SystemDecision | None
    status: str
    raw_solver: dict


def optimise_initial_squad(
    official: OfficialSnapshot,
    surface: ProductionProjectionSurface,
    *,
    horizon: int = 1,
    budget_tenths: int = BUDGET_TENTHS,
    excluded_ids: frozenset[int] = frozenset(),
) -> OptimisationResult:
    xp = xp_map(surface, horizon)
    candidates = [
        player
        for player in official.players
        if player.element_id in xp
        and player.can_transact
        and player.element_id not in excluded_ids
    ]
    count = len(candidates)
    if count == 0:
        return OptimisationResult(None, "INFEASIBLE", {})

    def squad_var(index):
        return index

    def xi_var(index):
        return count + index

    def captain_var(index):
        return 2 * count + index

    values = np.array(
        [max(xp[player.element_id], 0.0) for player in candidates]
    )
    objective = np.zeros(3 * count)
    objective[:count] = 1e-09 * values
    objective[count : 2 * count] = values
    objective[2 * count :] = values
    rows = []
    lower_bounds = []
    upper_bounds = []

    def add(coefficients, lower, upper):
        rows.append(coefficients)
        lower_bounds.append(lower)
        upper_bounds.append(upper)

    add({squad_var(i): 1 for i in range(count)}, 15, 15)
    add({xi_var(i): 1 for i in range(count)}, 11, 11)
    add({captain_var(i): 1 for i in range(count)}, 1, 1)
    add(
        {
            squad_var(i): candidates[i].price_tenths
            for i in range(count)
        },
        -np.inf,
        budget_tenths,
    )
    for position, required in SQUAD_COUNTS.items():
        indices = [
            i for i, player in enumerate(candidates) if player.position == position
        ]
        add({squad_var(i): 1 for i in indices}, required, required)
        add({xi_var(i): 1 for i in indices}, XI_MIN[position], XI_MAX[position])
    for team_id in sorted({player.team_id for player in candidates}):
        add(
            {
                squad_var(i): 1
                for i, player in enumerate(candidates)
                if player.team_id == team_id
            },
            -np.inf,
            MAX_PER_TEAM,
        )
    for i in range(count):
        add({xi_var(i): 1, squad_var(i): -1}, -np.inf, 0)
        add({captain_var(i): 1, xi_var(i): -1}, -np.inf, 0)

    matrix = lil_matrix((len(rows), 3 * count))
    for row_index, coefficients in enumerate(rows):
        for column, value in coefficients.items():
            matrix[row_index, column] = value

    result = milp(
        c=-objective,
        integrality=np.ones(3 * count),
        bounds=Bounds(np.zeros(3 * count), np.ones(3 * count)),
        constraints=LinearConstraint(
            matrix.tocsr(),
            np.array(lower_bounds),
            np.array(upper_bounds),
        ),
        options={"time_limit": 60, "mip_rel_gap": 1e-09},
    )
    if not result.success or result.x is None:
        return OptimisationResult(
            None,
            "INFEASIBLE",
            {"message": str(result.message)},
        )
    squad = tuple(
        sorted(
            candidates[i].element_id
            for i in range(count)
            if result.x[squad_var(i)] > 0.5
        )
    )
    decision = decision_from_fixed_squad(
        official,
        surface,
        squad,
        horizon=horizon,
        decision_mode="INITIAL_SQUAD",
    )
    return OptimisationResult(
        decision,
        "OPTIMAL",
        {
            "message": str(result.message),
            "mip_gap": float(getattr(result, "mip_gap", 0) or 0),
        },
    )
