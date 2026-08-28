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


_SEASONS = {
    "2025-2026": SeasonRules("2025-2026", free_transfer_top_ups=((16, 5),)),
    "2026-2027": SeasonRules("2026-2027"),
}


def normalise_season(value: str) -> str:
    text = str(value).strip().replace("/", "-")
    if len(text) == 7 and text[4] == "-":
        start = int(text[:4])
        return f"{start:04d}-{start // 100 * 100 + int(text[5:]):04d}"
    return text


def season_rules(season: str) -> SeasonRules:
    key = normalise_season(season)
    if key not in _SEASONS:
        raise ValueError(f"unsupported FPL season rules: {season}")
    return _SEASONS[key]


def derive_next_free_transfers(
    current_ft: int,
    transfers_made: int,
    *,
    chip: str | None = None,
    next_gameweek: int | None = None,
    rules: SeasonRules | None = None,
) -> int:
    rules = rules or season_rules("2026-2027")
    chip_key = str(chip or "").casefold().replace("_", "")
    if chip_key in {"wildcard", "freehit"}:
        result = min(
            rules.max_rolled_free_transfers,
            max(rules.first_post_deadline_free_transfers, int(current_ft)),
        )
    else:
        result = min(
            rules.max_rolled_free_transfers,
            max(
                rules.first_post_deadline_free_transfers,
                int(current_ft) - int(transfers_made) + 1,
            ),
        )
    if next_gameweek is not None:
        top_up = rules.top_up_for_gameweek(next_gameweek)
        if top_up is not None:
            result = min(rules.max_rolled_free_transfers, max(result, int(top_up)))
    return result


def validate_squad(
    players: dict[int, OfficialPlayer],
    squad_ids: tuple[int, ...] | list[int],
    *,
    bank_tenths: int = 0,
    price_tenths: dict[int, int] | None = None,
) -> tuple[str, ...]:
    ids = tuple(int(pid) for pid in squad_ids)
    errors: list[str] = []
    if len(ids) != SQUAD_SIZE or len(set(ids)) != SQUAD_SIZE:
        errors.append("squad must contain 15 unique players")
    missing = sorted(set(ids) - set(players))
    if missing:
        errors.append(f"unknown player ids: {missing}")
        return tuple(errors)
    counts = Counter(players[pid].position for pid in ids)
    for position, required in SQUAD_COUNTS.items():
        if counts[position] != required:
            errors.append(f"squad requires {required} {position.value}; got {counts[position]}")
    teams = Counter(players[pid].team_id for pid in ids)
    bad_teams = {team: count for team, count in teams.items() if count > MAX_PER_TEAM}
    if bad_teams:
        errors.append(f"club limit exceeded: {bad_teams}")
    prices = price_tenths or {pid: players[pid].price_tenths for pid in ids}
    total = sum(int(prices[pid]) for pid in ids)
    if total > BUDGET_TENTHS + int(bank_tenths):
        errors.append(f"budget exceeded: {total} > {BUDGET_TENTHS + int(bank_tenths)}")
    return tuple(errors)


def validate_xi(
    players: dict[int, OfficialPlayer],
    squad_ids: tuple[int, ...] | list[int],
    xi_ids: tuple[int, ...] | list[int],
) -> tuple[str, ...]:
    squad = set(int(pid) for pid in squad_ids)
    xi = tuple(int(pid) for pid in xi_ids)
    errors: list[str] = []
    if len(xi) != STARTING_XI_SIZE or len(set(xi)) != STARTING_XI_SIZE:
        errors.append("XI must contain 11 unique players")
    if not set(xi).issubset(squad):
        errors.append("XI contains player outside squad")
        return tuple(errors)
    counts = Counter(players[pid].position for pid in xi)
    for pos in Position:
        if counts[pos] < XI_MIN[pos] or counts[pos] > XI_MAX[pos]:
            errors.append(
                f"illegal XI {pos.value} count {counts[pos]} not in [{XI_MIN[pos]}, {XI_MAX[pos]}]"
            )
    return tuple(errors)


def validate_bench_order(
    players: dict[int, OfficialPlayer],
    squad_ids: tuple[int, ...] | list[int],
    xi_ids: tuple[int, ...] | list[int],
    bench_order: tuple[int, ...] | list[int],
) -> tuple[str, ...]:
    bench = set(int(pid) for pid in squad_ids) - set(int(pid) for pid in xi_ids)
    order = tuple(int(pid) for pid in bench_order)
    errors: list[str] = []
    if len(order) != 4 or set(order) != bench:
        errors.append("bench order must contain exactly the four benched players")
        return tuple(errors)
    if players[order[0]].position != Position.GK:
        errors.append("bench slot 0 must be the reserve goalkeeper")
    if any(players[pid].position == Position.GK for pid in order[1:]):
        errors.append("outfield bench slots cannot contain goalkeeper")
    return tuple(errors)
