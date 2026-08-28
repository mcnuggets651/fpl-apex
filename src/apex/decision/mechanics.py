from __future__ import annotations
from dataclasses import dataclass
from itertools import combinations
from apex.domain.models import OfficialSnapshot, Position, ProductionProjectionSurface, SystemDecision

@dataclass(frozen=True)
class GameweekMechanics:
    xi_ids: tuple[int, ...]
    captain_id: int
    vice_captain_id: int
    bench_order: tuple[int, ...]
    submitted_ev: float
    mechanics_warning: str | None = None

def xp_map(surface: ProductionProjectionSurface, horizon: int) -> dict[int, float]:
    return {int(r.element_id): float(r.expected_points) for r in surface.rows_for_horizon(horizon) if r.expected_points is not None}

def _legal_xis(squad_ids, official: OfficialSnapshot):
    players = official.player_map()
    by = {p: tuple(sorted((pid for pid in squad_ids if players[pid].position == p))) for p in Position}
    for gk in by[Position.GK]:
        for nd in range(3, 6):
            for nm in range(2, 6):
                nf = 10 - nd - nm
                if nf < 1 or nf > 3:
                    continue
                for ds in combinations(by[Position.DEF], nd):
                    for ms in combinations(by[Position.MID], nm):
                        for fs in combinations(by[Position.FWD], nf):
                            yield tuple(sorted((gk, *ds, *ms, *fs)))

def best_fixed_squad_mechanics(official: OfficialSnapshot, surface: ProductionProjectionSurface, squad_ids, *, horizon: int=1, xi_excluded: frozenset[int]=frozenset()) -> GameweekMechanics:
    ids = tuple(sorted(map(int, squad_ids)))
    xp = xp_map(surface, horizon)
    players = official.player_map()
    best = None
    for xi in _legal_xis(ids, official):
        if set(xi) & set(xi_excluded):
            continue
        if any((pid not in xp for pid in xi)):
            continue
        ranked = sorted(xi, key=lambda p: (-xp[p], p))
        captain = ranked[0]
        vice = ranked[1]
        submitted = sum((xp[p] for p in xi)) + xp[captain]
        tie = (tuple(ranked), captain, vice)
        if best is None or submitted > best[0] + 1e-12 or (abs(submitted - best[0]) <= 1e-12 and tie < best[1]):
            best = (submitted, tie, xi, captain, vice)
    if best is None:
        raise ValueError('fixed squad has no legal XI with complete serving forecast')
    _, _, xi, captain, vice = best
    bench = set(ids) - set(xi)
    bgk = next((p for p in bench if players[p].position == Position.GK))
    out = sorted((p for p in bench if p != bgk), key=lambda p: (-xp.get(p, float('-inf')), p))
    rows = {r.element_id: r for r in surface.rows_for_horizon(horizon)}
    complete_probs = all((rows[p].p_appearance is not None for p in ids if p in rows))
    warning = None if complete_probs else 'serving provider lacks complete appearance probabilities; submitted EV excludes contingent autosub and vice fallback value'
    return GameweekMechanics(xi, captain, vice, (bgk, *out), float(best[0]), warning)

def decision_from_fixed_squad(official, surface, squad_ids, *, horizon=1, transfers_in=(), transfers_out=(), transfer_hits=0, decision_mode='HOLD', xi_excluded: frozenset[int]=frozenset()) -> SystemDecision:
    m = best_fixed_squad_mechanics(official, surface, squad_ids, horizon=horizon, xi_excluded=xi_excluded)
    return SystemDecision(1, tuple(sorted(squad_ids)), m.xi_ids, m.captain_id, m.vice_captain_id, m.bench_order, tuple(sorted(transfers_in)), tuple(sorted(transfers_out)), m.submitted_ev, horizon, int(transfer_hits), decision_mode)
