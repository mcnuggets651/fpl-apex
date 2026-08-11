from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math

import pandas as pd

from apex_fpl.constants import SQUAD_COUNTS, XI_MAX, XI_MIN
from apex_fpl.replay.state import ReplayState, WeeklyAction
from apex_fpl.rules import CHIPS_PER_HALF, MAX_PER_TEAM, season_rules


@dataclass(frozen=True)
class Sale:
    player_id: int
    market_price: float
    purchase_price: float
    selling_price: float


def fpl_selling_price(purchase_price: float, market_price: float) -> float:
    """Reproduce FPL's 50% profit rule to one decimal million."""
    purchase = int(round(float(purchase_price) * 10))
    market = int(round(float(market_price) * 10))
    if market <= purchase:
        return market / 10.0
    return (purchase + math.floor((market - purchase) / 2)) / 10.0


def _player_map(players: pd.DataFrame) -> dict[int, dict]:
    required = {"player_id", "position", "team", "price"}
    missing = sorted(required - set(players.columns))
    if missing:
        raise ValueError(f"replay player snapshot missing columns: {missing}")
    rows = players.drop_duplicates("player_id").to_dict("records")
    return {int(row["player_id"]): row for row in rows}


def initialise_replay_state(
    *,
    season: str,
    squad: tuple[int, ...],
    players: pd.DataFrame,
    budget: float = 100.0,
) -> ReplayState:
    """Create the pre-GW1 state after unlimited initial-squad selection."""
    player_map = _player_map(players)
    if len(squad) != 15 or len(set(squad)) != 15:
        raise ValueError("initial squad requires 15 unique players")
    missing = sorted(set(squad) - set(player_map))
    if missing:
        raise ValueError(f"initial squad contains unknown players: {missing}")
    positions = Counter(str(player_map[pid]["position"]) for pid in squad)
    if dict(positions) != SQUAD_COUNTS:
        raise ValueError(f"illegal initial position counts: {dict(positions)}")
    teams = Counter(str(player_map[pid]["team"]) for pid in squad)
    if teams and max(teams.values()) > MAX_PER_TEAM:
        raise ValueError("initial squad exceeds three players from one club")
    cost = sum(float(player_map[pid]["price"]) for pid in squad)
    if cost > float(budget) + 1e-9:
        raise ValueError(f"initial squad exceeds budget: {cost:.1f} > {budget:.1f}")
    rules = season_rules(season)
    return ReplayState(
        season=rules.season,
        next_gameweek=1,
        squad=tuple(squad),
        bank=round(float(budget) - cost, 4),
        free_transfers=rules.initial_free_transfers,
        purchase_prices=tuple(sorted((pid, float(player_map[pid]["price"])) for pid in squad)),
    )


def validate_action(
    state: ReplayState,
    action: WeeklyAction,
    players: pd.DataFrame,
) -> tuple[Sale, ...]:
    """Validate one submitted action against only its deadline player snapshot."""
    if action.gameweek != state.next_gameweek:
        raise ValueError("weekly action Gameweek does not match replay state")
    player_map = _player_map(players)
    missing = sorted(set(action.squad) - set(player_map))
    if missing:
        raise ValueError(f"action contains players absent from deadline snapshot: {missing}")

    positions = Counter(str(player_map[pid]["position"]) for pid in action.squad)
    if dict(positions) != SQUAD_COUNTS:
        raise ValueError(f"illegal squad position counts: {dict(positions)}")
    teams = Counter(str(player_map[pid]["team"]) for pid in action.squad)
    if teams and max(teams.values()) > MAX_PER_TEAM:
        raise ValueError("squad exceeds three players from one club")

    xi_positions = Counter(str(player_map[pid]["position"]) for pid in action.xi)
    for position, minimum in XI_MIN.items():
        count = xi_positions.get(position, 0)
        if not minimum <= count <= XI_MAX[position]:
            raise ValueError(f"illegal starting formation at {position}: {count}")

    transfer_out = [int(pair[0]) for pair in action.transfers]
    transfer_in = [int(pair[1]) for pair in action.transfers]
    if len(transfer_out) != len(set(transfer_out)) or len(transfer_in) != len(set(transfer_in)):
        raise ValueError("a player may appear in at most one transfer pair")
    chip = action.chip
    if chip == "free_hit":
        if action.transfers:
            raise ValueError("Free Hit action must not record permanent transfers")
        purchase = dict(state.purchase_prices)
        liquidation = float(state.bank) + sum(
            fpl_selling_price(purchase[pid], player_map[pid]["price"])
            for pid in state.squad
        )
        temporary_cost = sum(float(player_map[pid]["price"]) for pid in action.squad)
        if temporary_cost > liquidation + 1e-9:
            raise ValueError(
                f"Free Hit squad exceeds liquidation budget: {temporary_cost:.1f} > "
                f"{liquidation:.1f}"
            )
    else:
        if set(transfer_out) - set(state.squad):
            raise ValueError("cannot sell a player outside the permanent squad")
        if set(transfer_in) & set(state.squad):
            raise ValueError("cannot buy a player already in the permanent squad")
        expected = (set(state.squad) - set(transfer_out)) | set(transfer_in)
        if expected != set(action.squad):
            raise ValueError("transfers do not reconcile to submitted squad")

    rules = season_rules(state.season)
    if chip in {"wildcard", "free_hit"} and action.hit_cost:
        raise ValueError(f"{chip} cannot incur a transfer hit")
    expected_hit = 0 if chip == "wildcard" else max(0, len(action.transfers) - state.free_transfers) * int(rules.transfer_hit_cost)
    if chip != "free_hit" and action.hit_cost != expected_hit:
        raise ValueError(f"hit cost does not reconcile: {action.hit_cost} != {expected_hit}")

    if chip:
        half_start, half_end = (1, rules.first_half_end_gw) if action.gameweek <= rules.first_half_end_gw else (rules.first_half_end_gw + 1, 38)
        used = Counter(
            name
            for gameweek, name in state.chips_used
            if half_start <= int(gameweek) <= half_end
        )
        if used[chip] >= CHIPS_PER_HALF[chip]:
            raise ValueError(f"{chip} is unavailable in this half-season")
        if action.gameweek == 1 and chip in {"wildcard", "free_hit"}:
            raise ValueError(f"{chip} is unavailable in Gameweek 1")
        if chip == "free_hit" and state.chips_used and state.chips_used[-1] == (action.gameweek - 1, "free_hit"):
            raise ValueError("Free Hit cannot be used in consecutive Gameweeks")

    purchase = dict(state.purchase_prices)
    sales = tuple(
        Sale(
            player_id=pid,
            market_price=float(player_map[pid]["price"]),
            purchase_price=float(purchase[pid]),
            selling_price=fpl_selling_price(purchase[pid], player_map[pid]["price"]),
        )
        for pid in transfer_out
    )
    spend = sum(float(player_map[pid]["price"]) for pid in transfer_in)
    funds = float(state.bank) + sum(sale.selling_price for sale in sales)
    if spend > funds + 1e-9:
        raise ValueError(f"transfers exceed available cash: {spend:.1f} > {funds:.1f}")
    return sales


def advance_state(
    state: ReplayState,
    action: WeeklyAction,
    players: pd.DataFrame,
) -> ReplayState:
    sales = validate_action(state, action, players)
    player_map = _player_map(players)
    if action.chip == "free_hit":
        permanent_squad = state.squad
        bank = state.bank
        purchase_prices = state.purchase_prices
        permanent_transfers = 0
    else:
        transfer_out = {int(pair[0]) for pair in action.transfers}
        transfer_in = {int(pair[1]) for pair in action.transfers}
        permanent_squad = action.squad
        bank = float(state.bank) + sum(sale.selling_price for sale in sales) - sum(
            float(player_map[pid]["price"]) for pid in transfer_in
        )
        ledger = {pid: price for pid, price in state.purchase_prices if pid not in transfer_out}
        ledger.update({pid: float(player_map[pid]["price"]) for pid in transfer_in})
        purchase_prices = tuple(sorted(ledger.items()))
        permanent_transfers = len(action.transfers)

    from apex_fpl.replay.state import advance_free_transfers

    chips = state.chips_used + (((action.gameweek, action.chip),) if action.chip else ())
    return ReplayState(
        season=state.season,
        next_gameweek=action.gameweek + 1,
        squad=tuple(permanent_squad),
        bank=round(float(bank), 4),
        free_transfers=advance_free_transfers(
            season=state.season,
            gameweek=action.gameweek,
            free_transfers_before=state.free_transfers,
            permanent_transfers=permanent_transfers,
            active_chip=action.chip,
        ),
        purchase_prices=tuple(purchase_prices),
        chips_used=chips,
        previous_state_sha256=state.state_sha256,
    )
