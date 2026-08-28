from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from apex.domain.models import OfficialSnapshot, Position, ProjectionSurface, SystemDecision
from apex.domain.rules import BUDGET_TENTHS, MAX_PER_TEAM, SQUAD_COUNTS, XI_MAX, XI_MIN


@dataclass(frozen=True)
class OptimisationResult:
    decision: SystemDecision | None
    status: str
    raw_solver: dict


def _xp_by_player(surface: ProjectionSurface, horizon: int) -> dict[int, float]:
    result: dict[int, float] = {}
    for row in surface.rows:
        if row.horizon == int(horizon) and row.expected_points is not None:
            result[int(row.element_id)] = float(row.expected_points)
    return result


def optimise_initial_squad(
    official: OfficialSnapshot,
    surface: ProjectionSurface,
    *,
    horizon: int = 1,
    budget_tenths: int = BUDGET_TENTHS,
) -> OptimisationResult:
    """Exact max-EV initial-squad MILP using only the serving production surface.

    This input type cannot carry shadow/disagreement information.
    """
    xp = _xp_by_player(surface, horizon)
    candidates = [p for p in official.players if p.element_id in xp and p.can_transact]
    n = len(candidates)
    if n == 0:
        return OptimisationResult(None, "INFEASIBLE", {})

    def s(i: int) -> int:
        return i

    def x(i: int) -> int:
        return n + i

    def c(i: int) -> int:
        return 2 * n + i

    objective = np.zeros(3 * n, dtype=float)
    values = np.array([max(xp[p.element_id], 0.0) for p in candidates], dtype=float)
    # Primary objective: submitted XI + captain copy. The 1e-6 squad term is
    # deterministic tie-breaking only and cannot materially displace XI EV.
    objective[:n] = 1e-6 * values
    objective[n : 2 * n] = values
    objective[2 * n : 3 * n] = values

    rows: list[dict[int, float]] = []
    lower: list[float] = []
    upper: list[float] = []

    def add(coeffs: dict[int, float], lo: float, hi: float) -> None:
        rows.append(coeffs)
        lower.append(lo)
        upper.append(hi)

    add({s(i): 1.0 for i in range(n)}, 15, 15)
    add({x(i): 1.0 for i in range(n)}, 11, 11)
    add({c(i): 1.0 for i in range(n)}, 1, 1)
    add(
        {s(i): float(candidates[i].price_tenths) for i in range(n)},
        -np.inf,
        budget_tenths,
    )
    for position, count in SQUAD_COUNTS.items():
        idx = [i for i, p in enumerate(candidates) if p.position == position]
        add({s(i): 1.0 for i in idx}, count, count)
        add({x(i): 1.0 for i in idx}, XI_MIN[position], XI_MAX[position])
    for team_id in sorted({p.team_id for p in candidates}):
        idx = [i for i, p in enumerate(candidates) if p.team_id == team_id]
        add({s(i): 1.0 for i in idx}, -np.inf, MAX_PER_TEAM)
    for i in range(n):
        add({x(i): 1.0, s(i): -1.0}, -np.inf, 0)
        add({c(i): 1.0, x(i): -1.0}, -np.inf, 0)

    matrix = lil_matrix((len(rows), 3 * n), dtype=float)
    for r, coeffs in enumerate(rows):
        for col, val in coeffs.items():
            matrix[r, col] = val
    res = milp(
        c=-objective,
        integrality=np.ones(3 * n),
        bounds=Bounds(np.zeros(3 * n), np.ones(3 * n)),
        constraints=LinearConstraint(
            matrix.tocsr(),
            np.array(lower),
            np.array(upper),
        ),
        options={"time_limit": 60},
    )
    if not res.success or res.x is None:
        return OptimisationResult(None, "INFEASIBLE", {"message": str(res.message)})
    chosen = tuple(
        sorted(candidates[i].element_id for i in range(n) if res.x[s(i)] > 0.5)
    )
    xi = tuple(sorted(candidates[i].element_id for i in range(n) if res.x[x(i)] > 0.5))
    captain = next(candidates[i].element_id for i in range(n) if res.x[c(i)] > 0.5)
    vice = max((pid for pid in xi if pid != captain), key=lambda pid: (xp[pid], -pid))
    players = official.player_map()
    bench = sorted(set(chosen) - set(xi))
    bench_gk = next(pid for pid in bench if players[pid].position == Position.GK)
    outfield = sorted((pid for pid in bench if pid != bench_gk), key=lambda pid: (-xp[pid], pid))
    decision = SystemDecision(
        schema_version=1,
        squad_ids=chosen,
        xi_ids=xi,
        captain_id=captain,
        vice_captain_id=vice,
        bench_order=(bench_gk, *outfield),
        objective=float(-res.fun),
        horizon=horizon,
    )
    return OptimisationResult(decision, "OPTIMAL", {"message": str(res.message)})
