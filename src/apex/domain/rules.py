from __future__ import annotations
from collections import Counter
from dataclasses import dataclass
from .models import OfficialPlayer, Position
SQUAD_COUNTS = {Position.GK: 2, Position.DEF: 5, Position.MID: 5, Position.FWD: 3}
XI_MIN = {Position.GK: 1, Position.DEF: 3, Position.MID: 2, Position.FWD: 1}
XI_MAX = {Position.GK: 1, Position.DEF: 5, Position.MID: 5, Position.FWD: 3}
BUDGET_TENTHS = 1000
MAX_PER_TEAM = 3
SQUAD_SIZE = 15
STARTING_XI_SIZE = 11

@dataclass(frozen=True)
class SeasonRules:
    season: str
    max_rolled_free_transfers: int = 5
    initial_free_transfers: int = 0
    first_post_deadline_free_transfers: int = 1
    transfer_hit_cost: int = 4
    free_transfer_top_ups: tuple[tuple[int, int], ...] = ()

    def top_up_for_gameweek(self, gameweek: int) -> int | None:
        return dict(self.free_transfer_top_ups).get(int(gameweek))
_SEASONS = {'2025-2026': SeasonRules('2025-2026', free_transfer_top_ups=((16, 5),)), '2026-2027': SeasonRules('2026-2027')}

def normalise_season(value: str) -> str:
    text = str(value).strip().replace('/', '-')
    if len(text) == 7 and text[4] == '-':
        start = int(text[:4])
        return f'{start:04d}-{start // 100 * 100 + int(text[5:]):04d}'
    return text

def season_rules(season: str) -> SeasonRules:
    key = normalise_season(season)
    if key not in _SEASONS:
        raise ValueError(f'unsupported FPL season rules: {season}')
    return _SEASONS[key]

def derive_next_free_transfers(current_ft: int, transfers_made: int, *, chip: str | None=None, next_gameweek: int | None=None, rules: SeasonRules | None=None) -> int:
    rules = rules or season_rules('2026-2027')
    chip_key = str(chip or '').casefold().replace('_', '')
    if chip_key in {'wildcard', 'freehit'}:
        result = min(rules.max_rolled_free_transfers, max(rules.first_post_deadline_free_transfers, int(current_ft)))
    else:
        result = min(rules.max_rolled_free_transfers, max(rules.first_post_deadline_free_transfers, int(current_ft) - int(transfers_made) + 1))
    if next_gameweek is not None:
        top_up = rules.top_up_for_gameweek(next_gameweek)
        if top_up is not None:
            result = min(rules.max_rolled_free_transfers, max(result, int(top_up)))
    return result

def calculate_selling_price(purchase_tenths: int, current_tenths: int) -> int:
    purchase, current = (int(purchase_tenths), int(current_tenths))
    if current <= purchase:
        return current
    return purchase + (current - purchase) // 2

def validate_squad(players: dict[int, OfficialPlayer], squad_ids, *, budget_tenths: int | None=BUDGET_TENTHS, price_tenths: dict[int, int] | None=None) -> tuple[str, ...]:
    ids = tuple((int(pid) for pid in squad_ids))
    errors = []
    if len(ids) != SQUAD_SIZE or len(set(ids)) != SQUAD_SIZE:
        errors.append('squad must contain 15 unique players')
    missing = sorted(set(ids) - set(players))
    if missing:
        return tuple(errors + [f'unknown player ids: {missing}'])
    counts = Counter((players[p].position for p in ids))
    for pos, req in SQUAD_COUNTS.items():
        if counts[pos] != req:
            errors.append(f'squad requires {req} {pos.value}; got {counts[pos]}')
    teams = Counter((players[p].team_id for p in ids))
    bad = {t: c for t, c in teams.items() if c > MAX_PER_TEAM}
    if bad:
        errors.append(f'club limit exceeded: {bad}')
    if budget_tenths is not None:
        prices = price_tenths or {p: players[p].price_tenths for p in ids}
        total = sum((int(prices[p]) for p in ids))
        if total > int(budget_tenths):
            errors.append(f'budget exceeded: {total} > {int(budget_tenths)}')
    return tuple(errors)

def validate_xi(players: dict[int, OfficialPlayer], squad_ids, xi_ids) -> tuple[str, ...]:
    squad = set(map(int, squad_ids))
    xi = tuple(map(int, xi_ids))
    errors = []
    if len(xi) != STARTING_XI_SIZE or len(set(xi)) != STARTING_XI_SIZE:
        errors.append('XI must contain 11 unique players')
    unknown = sorted(set(xi) - set(players))
    outside = not set(xi).issubset(squad)
    if unknown:
        errors.append(f'XI contains unknown player ids: {unknown}')
    if outside:
        errors.append('XI contains player outside squad')
    if unknown or outside:
        return tuple(errors)
    counts = Counter((players[p].position for p in xi))
    for pos in Position:
        if counts[pos] < XI_MIN[pos] or counts[pos] > XI_MAX[pos]:
            errors.append(f'illegal XI {pos.value} count {counts[pos]} not in [{XI_MIN[pos]}, {XI_MAX[pos]}]')
    return tuple(errors)

def validate_bench_order(players: dict[int, OfficialPlayer], squad_ids, xi_ids, bench_order) -> tuple[str, ...]:
    bench = set(map(int, squad_ids)) - set(map(int, xi_ids))
    order = tuple(map(int, bench_order))
    errors = []
    if len(order) != 4 or set(order) != bench:
        return ('bench order must contain exactly the four benched players',)
    unknown = sorted(set(order) - set(players))
    if unknown:
        return (f'bench order contains unknown player ids: {unknown}',)
    if players[order[0]].position != Position.GK:
        errors.append('bench slot 0 must be the reserve goalkeeper')
    if any((players[p].position == Position.GK for p in order[1:])):
        errors.append('outfield bench slots cannot contain goalkeeper')
    return tuple(errors)
