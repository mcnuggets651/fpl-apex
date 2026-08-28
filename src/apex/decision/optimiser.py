from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix
from apex.domain.models import OfficialSnapshot, ProductionProjectionSurface, SystemDecision
from apex.domain.rules import BUDGET_TENTHS, MAX_PER_TEAM, SQUAD_COUNTS, XI_MAX, XI_MIN
from .mechanics import decision_from_fixed_squad, xp_map

@dataclass(frozen=True)
class OptimisationResult:
    decision: SystemDecision | None
    status: str
    raw_solver: dict

def optimise_initial_squad(official: OfficialSnapshot, surface: ProductionProjectionSurface, *, horizon: int=1, budget_tenths: int=BUDGET_TENTHS, excluded_ids: frozenset[int]=frozenset()) -> OptimisationResult:
    xp = xp_map(surface, horizon)
    candidates = [p for p in official.players if p.element_id in xp and p.can_transact and (p.element_id not in excluded_ids)]
    n = len(candidates)
    if n == 0:
        return OptimisationResult(None, 'INFEASIBLE', {})

    def s(i):
        return i

    def x(i):
        return n + i

    def c(i):
        return 2 * n + i
    values = np.array([max(xp[p.element_id], 0.0) for p in candidates])
    objective = np.zeros(3 * n)
    objective[:n] = 1e-09 * values
    objective[n:2 * n] = values
    objective[2 * n:] = values
    rows = []
    lo = []
    hi = []

    def add(d, l, h):
        rows.append(d)
        lo.append(l)
        hi.append(h)
    add({s(i): 1 for i in range(n)}, 15, 15)
    add({x(i): 1 for i in range(n)}, 11, 11)
    add({c(i): 1 for i in range(n)}, 1, 1)
    add({s(i): candidates[i].price_tenths for i in range(n)}, -np.inf, budget_tenths)
    for pos, count in SQUAD_COUNTS.items():
        idx = [i for i, p in enumerate(candidates) if p.position == pos]
        add({s(i): 1 for i in idx}, count, count)
        add({x(i): 1 for i in idx}, XI_MIN[pos], XI_MAX[pos])
    for t in sorted({p.team_id for p in candidates}):
        add({s(i): 1 for i, p in enumerate(candidates) if p.team_id == t}, -np.inf, MAX_PER_TEAM)
    for i in range(n):
        add({x(i): 1, s(i): -1}, -np.inf, 0)
        add({c(i): 1, x(i): -1}, -np.inf, 0)
    A = lil_matrix((len(rows), 3 * n))
    for r, d in enumerate(rows):
        for col, val in d.items():
            A[r, col] = val
    res = milp(c=-objective, integrality=np.ones(3 * n), bounds=Bounds(np.zeros(3 * n), np.ones(3 * n)), constraints=LinearConstraint(A.tocsr(), np.array(lo), np.array(hi)), options={'time_limit': 60, 'mip_rel_gap': 1e-09})
    if not res.success or res.x is None:
        return OptimisationResult(None, 'INFEASIBLE', {'message': str(res.message)})
    squad = tuple(sorted((candidates[i].element_id for i in range(n) if res.x[s(i)] > 0.5)))
    decision = decision_from_fixed_squad(official, surface, squad, horizon=horizon, decision_mode='INITIAL_SQUAD')
    return OptimisationResult(decision, 'OPTIMAL', {'message': str(res.message), 'mip_gap': float(getattr(res, 'mip_gap', 0) or 0)})
