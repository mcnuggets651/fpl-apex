from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix
from apex.domain.models import OfficialSnapshot, ProductionProjectionSurface, SystemDecision, TeamState
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

def optimise_transfer_horizon(official: OfficialSnapshot, surface: ProductionProjectionSurface, team: TeamState, *, max_horizon: int, excluded_h1: frozenset[int]=frozenset()) -> TransferOptimisationResult:
    if max_horizon < 2:
        d = decision_from_fixed_squad(official, surface, team.squad_ids, horizon=1, decision_mode='HOLD_H1_ONLY', xi_excluded=excluded_h1)
        return TransferOptimisationResult(d, (), 'WITHHELD_H1_ONLY', d.objective, {'reason': 'discretionary transfers require H2+ qualified forecast'})
    if not team.state_complete_for_transfers or len(team.selling_prices_tenths) != 15:
        d = decision_from_fixed_squad(official, surface, team.squad_ids, horizon=1, decision_mode='HOLD_TEAM_STATE_INCOMPLETE', xi_excluded=excluded_h1)
        return TransferOptimisationResult(d, (), 'WITHHELD_TEAM_STATE_INCOMPLETE', d.objective, {'reason': 'exact selling-price state incomplete'})
    horizons = list(range(1, max_horizon + 1))
    xp = {h: xp_map(surface, h) for h in horizons}
    universe = set.intersection(*(set(xp[h]) for h in horizons))
    players = [p for p in official.players if p.element_id in universe and (p.can_transact or p.element_id in team.squad_ids)]
    n = len(players)
    T = len(horizons)
    pids = [p.element_id for p in players]
    by = {pid: i for i, pid in enumerate(pids)}
    if not set(team.squad_ids).issubset(by):
        return TransferOptimisationResult(None, (), 'INFEASIBLE', None, {'reason': 'current squad missing from forecast universe'})
    block = n * T
    S0 = 0
    X0 = block
    C0 = 2 * block
    IN0 = 3 * block
    OUT0 = 4 * block
    BANK0 = 5 * block
    F = season_rules(official.season).max_rolled_free_transfers
    K = 16
    Y0 = BANK0 + T
    m = Y0 + T * F * K

    def q(base, i, t):
        return base + t * n + i

    def y(t, ft, k):
        return Y0 + (t * F + (ft - 1)) * K + k
    ev = np.zeros(m)
    transfer_count = np.zeros(m)
    rules = season_rules(official.season)
    for t, h in enumerate(horizons):
        for i, pid in enumerate(pids):
            ev[q(X0, i, t)] += xp[h][pid]
            ev[q(C0, i, t)] += xp[h][pid]
            transfer_count[q(IN0, i, t)] = 1
        for ft in range(1, F + 1):
            for k in range(K):
                ev[y(t, ft, k)] -= rules.transfer_hit_cost * max(0, k - ft)
    rows = []
    lo = []
    hi = []

    def add(d, l, h):
        rows.append(d)
        lo.append(l)
        hi.append(h)
    for t, h in enumerate(horizons):
        add({q(S0, i, t): 1 for i in range(n)}, 15, 15)
        add({q(X0, i, t): 1 for i in range(n)}, 11, 11)
        add({q(C0, i, t): 1 for i in range(n)}, 1, 1)
        for pos, count in SQUAD_COUNTS.items():
            idx = [i for i, p in enumerate(players) if p.position == pos]
            add({q(S0, i, t): 1 for i in idx}, count, count)
            add({q(X0, i, t): 1 for i in idx}, XI_MIN[pos], XI_MAX[pos])
        for team_id in sorted({p.team_id for p in players}):
            add({q(S0, i, t): 1 for i, p in enumerate(players) if p.team_id == team_id}, -np.inf, MAX_PER_TEAM)
        for i, p in enumerate(players):
            if t == 0 and p.element_id in excluded_h1:
                add({q(X0, i, t): 1}, 0, 0)
                add({q(C0, i, t): 1}, 0, 0)
            add({q(X0, i, t): 1, q(S0, i, t): -1}, -np.inf, 0)
            add({q(C0, i, t): 1, q(X0, i, t): -1}, -np.inf, 0)
            add({q(IN0, i, t): 1, q(OUT0, i, t): 1}, -np.inf, 1)
            initial = 1 if p.element_id in team.squad_ids else 0
            if t == 0:
                add({q(S0, i, t): 1, q(IN0, i, t): -1, q(OUT0, i, t): 1}, initial, initial)
            else:
                add({q(S0, i, t): 1, q(S0, i, t - 1): -1, q(IN0, i, t): -1, q(OUT0, i, t): 1}, 0, 0)
        bal = {q(IN0, i, t): 1 for i in range(n)}
        bal.update({q(OUT0, i, t): -1 for i in range(n)})
        add(bal, 0, 0)
        add({y(t, ft, k): 1 for ft in range(1, F + 1) for k in range(K)}, 1, 1)
        cnt = {q(IN0, i, t): 1 for i in range(n)}
        cnt.update({y(t, ft, k): -k for ft in range(1, F + 1) for k in range(K)})
        add(cnt, 0, 0)
        if t == 0:
            add({y(t, team.free_transfers, k): 1 for k in range(K)}, 1, 1)
        else:
            for ft_now in range(1, F + 1):
                d = {y(t, ft_now, k): 1 for k in range(K)}
                for ft_prev in range(1, F + 1):
                    for k_prev in range(K):
                        nxt = min(F, max(1, ft_prev - k_prev + 1))
                        if nxt == ft_now:
                            d[y(t - 1, ft_prev, k_prev)] = d.get(y(t - 1, ft_prev, k_prev), 0) - 1
                add(d, 0, 0)
        cash = {BANK0 + t: 1}
        for i, pid in enumerate(pids):
            buy = official.player_map()[pid].price_tenths
            sell = team.selling_prices_tenths.get(pid, buy) if pid in team.squad_ids else buy
            cash[q(IN0, i, t)] = buy
            cash[q(OUT0, i, t)] = -sell
        if t == 0:
            add(cash, team.bank_tenths, team.bank_tenths)
        else:
            cash[BANK0 + t - 1] = -1
            add(cash, 0, 0)
    lb = np.zeros(m)
    ub = np.ones(m)
    integrality = np.ones(m, dtype=int)
    for t in range(T):
        lb[BANK0 + t] = 0
        ub[BANK0 + t] = 2000
        integrality[BANK0 + t] = 0

    def solve(obj, extra=None):
        rr = list(rows)
        ll = list(lo)
        hh = list(hi)
        if extra:
            d, l, h = extra
            rr.append(d)
            ll.append(l)
            hh.append(h)
        A = lil_matrix((len(rr), m))
        for r, d in enumerate(rr):
            for col, val in d.items():
                A[r, col] = val
        return milp(c=obj, integrality=integrality, bounds=Bounds(lb, ub), constraints=LinearConstraint(A.tocsr(), np.asarray(ll), np.asarray(hh)), options={'time_limit': 120, 'mip_rel_gap': 1e-09})
    first = solve(-ev)
    if first.x is None:
        return TransferOptimisationResult(None, (), 'INFEASIBLE', None, {'message': str(first.message)})
    optimum = float(ev @ first.x)
    extra = ({i: float(v) for i, v in enumerate(ev) if abs(v) > 1e-15}, optimum - 1e-07, np.inf)
    second = solve(transfer_count, extra)
    sol = second.x if second.x is not None else first.x
    weeks = []
    ft_state = team.free_transfers
    for t, h in enumerate(horizons):
        squad = tuple(sorted((pids[i] for i in range(n) if sol[q(S0, i, t)] > 0.5)))
        ins = tuple(sorted((pids[i] for i in range(n) if sol[q(IN0, i, t)] > 0.5)))
        outs = tuple(sorted((pids[i] for i in range(n) if sol[q(OUT0, i, t)] > 0.5)))
        k = len(ins)
        hits = max(0, k - ft_state)
        bank = int(round(sol[BANK0 + t]))
        gw = min(official.deadlines) + h - 1 if official.deadlines else h
        week_decision = decision_from_fixed_squad(official, surface, squad, horizon=h)
        weeks.append(TransferWeek(h, gw, squad, ins, outs, bank, ft_state, hits, week_decision.objective))
        ft_state = min(F, max(1, ft_state - k + 1))
    w = weeks[0]
    d = decision_from_fixed_squad(official, surface, w.squad_ids, horizon=1, transfers_in=w.transfers_in, transfers_out=w.transfers_out, transfer_hits=w.hits, decision_mode='TRANSFER_HORIZON', xi_excluded=excluded_h1)
    return TransferOptimisationResult(d, tuple(weeks), 'OPTIMAL', optimum, {'primary_message': str(first.message), 'secondary_message': str(second.message), 'transfer_tiebreak': True})
