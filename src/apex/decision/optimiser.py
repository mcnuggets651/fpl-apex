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

LEXICOGRAPHIC_BLOCK_SIZE = 40


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
    candidate_limit: int = 16,
    candidate_regret_fraction: float = 0.005,
) -> OptimisationResult:
    """Generate max-xP squads and exact-rescore a bounded near-optimal shortlist.

    The primary MILP objective is authoritative. If multiple squads share that
    exact primary optimum, a hierarchical lexicographic solve canonicalises the
    15-player squad before shortlist generation. The tie-break is performed only
    under an equality lock on the primary optimum, so it cannot trade away xP.
    """
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    if not 0.0 <= float(candidate_regret_fraction) <= 0.05:
        raise ValueError("candidate_regret_fraction must be between 0 and 5%")

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

    values = np.array([max(xp[player.element_id], 0.0) for player in candidates])
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
        {squad_var(i): candidates[i].price_tenths for i in range(count)},
        -np.inf,
        budget_tenths,
    )
    for position, required in SQUAD_COUNTS.items():
        indices = [
            i for i, player in enumerate(candidates) if player.position == position
        ]
        add({squad_var(i): 1 for i in indices}, required, required)
        add(
            {xi_var(i): 1 for i in indices},
            XI_MIN[position],
            XI_MAX[position],
        )
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

    variable_count = 3 * count

    def solve(extras=(), *, cost=None):
        solve_rows = list(rows)
        solve_lower = list(lower_bounds)
        solve_upper = list(upper_bounds)
        for coefficients, lower, upper in extras:
            solve_rows.append(coefficients)
            solve_lower.append(lower)
            solve_upper.append(upper)

        matrix = lil_matrix((len(solve_rows), variable_count))
        for row_index, coefficients in enumerate(solve_rows):
            for column, value in coefficients.items():
                matrix[row_index, column] = value

        return milp(
            c=(-objective if cost is None else cost),
            integrality=np.ones(variable_count),
            bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
            constraints=LinearConstraint(
                matrix.tocsr(),
                np.asarray(solve_lower),
                np.asarray(solve_upper),
            ),
            options={"time_limit": 60, "mip_rel_gap": 1e-09},
        )

    first = solve()
    if not first.success or first.x is None:
        return OptimisationResult(
            None,
            "INFEASIBLE",
            {"message": str(first.message)},
        )

    # Re-evaluate the primary optimum on the integral incumbent. This avoids
    # baking solver feasibility noise into the equality constraint below.
    primary_solution = np.rint(first.x)
    primary_optimum = float(objective @ primary_solution)
    primary_coefficients = {
        index: float(value)
        for index, value in enumerate(objective)
        if value != 0.0
    }
    primary_lock = (primary_coefficients, primary_optimum, primary_optimum)

    # Canonicalise equal-primary squads without adding a synthetic EV term.
    # Each block encodes <=40 squad bits as an exact integer (<2^40 < 2^53),
    # fixes the best value, then advances to the next block. Earlier/lower FPL
    # element IDs dominate later IDs, yielding a stable lexicographically-small
    # squad independent of candidate ordering or HiGHS incumbent ordering.
    ordered_indices = sorted(
        range(count),
        key=lambda index: candidates[index].element_id,
    )
    tie_locks = [primary_lock]
    canonical = first
    for offset in range(0, count, LEXICOGRAPHIC_BLOCK_SIZE):
        block = ordered_indices[offset : offset + LEXICOGRAPHIC_BLOCK_SIZE]
        block_cost = np.zeros(variable_count)
        block_weights: dict[int, float] = {}
        width = len(block)
        for rank, candidate_index in enumerate(block):
            weight = float(1 << (width - rank - 1))
            variable = squad_var(candidate_index)
            block_weights[variable] = weight
            block_cost[variable] = -weight
        candidate = solve(tuple(tie_locks), cost=block_cost)
        if not candidate.success or candidate.x is None:
            return OptimisationResult(
                None,
                "ERROR",
                {
                    "message": "primary-optimum deterministic tie-break failed",
                    "primary_message": str(first.message),
                },
            )
        canonical = candidate
        achieved = float(
            sum(
                weight * int(candidate.x[variable] > 0.5)
                for variable, weight in block_weights.items()
            )
        )
        tie_locks.append((block_weights, achieved, achieved))

    regret_points = max(
        0.10,
        abs(primary_optimum) * float(candidate_regret_fraction),
    )
    shortlist_floor = primary_optimum - regret_points

    exclusions = []
    generated = []
    current = canonical
    shortlist_complete = False

    for generation_rank in range(1, int(candidate_limit) + 1):
        if current.x is None:
            shortlist_complete = True
            break
        approximate = float(objective @ np.rint(current.x))
        if approximate < shortlist_floor - 1e-7:
            shortlist_complete = True
            break

        squad = tuple(
            sorted(
                candidates[i].element_id
                for i in range(count)
                if current.x[squad_var(i)] > 0.5
            )
        )
        decision = decision_from_fixed_squad(
            official,
            surface,
            squad,
            horizon=horizon,
            decision_mode="INITIAL_SQUAD",
        )
        generated.append(
            {
                "generation_rank": generation_rank,
                "approximate_objective": approximate,
                "exact_objective": float(decision.objective),
                "squad": squad,
                "decision": decision,
                "message": str(current.message),
            }
        )

        exclusion = {
            squad_var(i): 1.0
            for i in range(count)
            if current.x[squad_var(i)] > 0.5
        }
        exclusions.append((exclusion, -np.inf, 14.0))
        current = solve(tuple(exclusions))
        if current.x is None:
            shortlist_complete = True
            break
        if float(objective @ np.rint(current.x)) < shortlist_floor - 1e-7:
            shortlist_complete = True
            break

    if not generated:
        return OptimisationResult(
            None,
            "INFEASIBLE",
            {"message": "initial shortlist produced no decodable candidate"},
        )

    if shortlist_complete:
        selected = min(
            generated,
            key=lambda candidate: (
                -candidate["exact_objective"],
                candidate["squad"],
            ),
        )
        selection_policy = "EXACT_CONTINGENCY_CERTIFIED_SHORTLIST"
        reason = None
    else:
        selected = generated[0]
        selection_policy = "PRIMARY_MAX_EV_FALLBACK_UNCERTIFIED_SHORTLIST"
        reason = (
            "exact contingency shortlist reached its candidate limit before "
            "the configured primary-objective regret band was exhausted; "
            "deterministic primary max-EV squad retained"
        )

    raw_solver = {
        "message": selected["message"],
        "mip_gap": float(getattr(first, "mip_gap", 0) or 0),
        "primary_tiebreak": "LEXICOGRAPHIC_SQUAD_BLOCKS_UNDER_EXACT_PRIMARY_LOCK",
        "primary_tiebreak_block_size": LEXICOGRAPHIC_BLOCK_SIZE,
        "selection_policy": selection_policy,
        "shortlist_complete": shortlist_complete,
        "candidate_count": len(generated),
        "candidate_limit": int(candidate_limit),
        "candidate_regret_fraction": float(candidate_regret_fraction),
        "candidate_regret_points": float(regret_points),
        "shortlist_floor": float(shortlist_floor),
        "primary_objective": float(primary_optimum),
        "selected_generation_rank": int(selected["generation_rank"]),
        "selected_approximate_objective": float(selected["approximate_objective"]),
        "selected_exact_objective": float(selected["exact_objective"]),
        "candidate_objectives": [
            {
                "generation_rank": int(candidate["generation_rank"]),
                "approximate_objective": float(candidate["approximate_objective"]),
                "exact_objective": float(candidate["exact_objective"]),
            }
            for candidate in generated
        ],
    }
    if reason:
        raw_solver["reason"] = reason

    return OptimisationResult(
        selected["decision"],
        "OPTIMAL",
        raw_solver,
    )
