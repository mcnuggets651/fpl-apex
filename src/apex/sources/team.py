from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import requests

from apex.domain.models import ExecutionDecision, OfficialSnapshot, TeamState
from apex.domain.rules import (
    calculate_selling_price,
    derive_next_free_transfers,
    season_rules,
)

BASE = "https://fantasy.premierleague.com/api"


def _dt(value):
    d = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(
        timezone.utc
    )


def replay_free_transfers(
    history: dict[str, Any],
    latest_event: int,
    latest_entry_history: dict | None = None,
    latest_active_chip: str | None = None,
    season="2026-2027",
) -> int:
    rules = season_rules(season)
    rows = {
        int(r["event"]): dict(r)
        for r in history.get("current", [])
        if r.get("event") is not None and int(r["event"]) <= latest_event
    }
    if latest_entry_history:
        r = dict(latest_entry_history)
        r.setdefault("event", latest_event)
        rows[latest_event] = r
    chips = {
        int(r["event"]): str(r.get("name", "")).casefold().replace("_", "")
        for r in history.get("chips", [])
        if r.get("event") is not None
    }
    if latest_active_chip:
        chips[latest_event] = str(latest_active_chip).casefold().replace("_", "")
    ft = rules.initial_free_transfers
    for gw in range(1, latest_event + 1):
        transfers = int(rows.get(gw, {}).get("event_transfers", 0) or 0)
        chip = chips.get(gw)
        if chip in {"wildcard", "freehit"}:
            ft = min(
                rules.max_rolled_free_transfers,
                max(rules.first_post_deadline_free_transfers, ft),
            )
        else:
            ft = derive_next_free_transfers(
                ft,
                transfers,
                rules=rules,
                next_gameweek=gw + 1,
            )
    return ft


def _authenticated_headers() -> dict[str, str] | None:
    """Build auth headers only from runtime secrets, never repository config."""
    cookie = os.getenv("FPL_SESSION_COOKIE", "").strip()
    token = os.getenv("FPL_X_API_AUTHORIZATION", "").strip()
    if not cookie and not token:
        return None
    headers = {
        "Accept": "application/json",
        "Referer": "https://fantasy.premierleague.com/",
        "User-Agent": "fpl-apex-v2/1",
    }
    if cookie:
        headers["Cookie"] = cookie
    if token:
        headers["X-API-Authorization"] = (
            token if token.casefold().startswith("bearer ") else f"Bearer {token}"
        )
    return headers


def _pending_chip(payload: dict[str, Any]) -> str | None:
    pending = [
        str(chip.get("name"))
        for chip in payload.get("chips", [])
        if chip.get("is_pending") is True and chip.get("name")
    ]
    if len(pending) > 1:
        raise RuntimeError("Official FPL reports multiple pending chips")
    return pending[0] if pending else None


def _authenticated_team_state(
    entry_id: int,
    official: OfficialSnapshot,
    *,
    http,
    headers: dict[str, str],
    timeout: float,
    published_gw: int,
) -> TeamState:
    me = http.get(f"{BASE}/me/", headers=headers, timeout=timeout)
    if me.status_code in {401, 403}:
        raise RuntimeError("Official FPL team-state credential was rejected")
    me.raise_for_status()
    me_payload = me.json()
    authenticated_entry = (me_payload.get("player") or {}).get("entry")
    if authenticated_entry is None or int(authenticated_entry) != int(entry_id):
        raise RuntimeError(
            "Official FPL credential belongs to a different manager entry"
        )

    response = http.get(
        f"{BASE}/my-team/{int(entry_id)}/",
        headers=headers,
        timeout=timeout,
    )
    if response.status_code in {401, 403}:
        raise RuntimeError("Official FPL current-team request was not authorized")
    response.raise_for_status()
    payload = response.json()
    picks = payload.get("picks", []) if isinstance(payload, dict) else []
    if len(picks) != 15:
        raise RuntimeError(
            f"Official FPL current team must contain 15 picks; got {len(picks)}"
        )

    squad = tuple(sorted(int(row["element"]) for row in picks))
    if len(set(squad)) != 15:
        raise RuntimeError("Official FPL current team contains duplicate player IDs")
    players = official.player_map()
    unknown = sorted(set(squad) - set(players))
    if unknown:
        raise RuntimeError(
            f"Official FPL current team contains IDs outside authority snapshot: {unknown}"
        )

    purchase: dict[int, int] = {}
    selling: dict[int, int] = {}
    for row in picks:
        player_id = int(row["element"])
        if row.get("purchase_price") is None or row.get("selling_price") is None:
            raise RuntimeError(
                "Official FPL authenticated team omitted purchase/selling prices"
            )
        purchase_price = int(row["purchase_price"])
        selling_price = int(row["selling_price"])
        if purchase_price <= 0 or selling_price <= 0:
            raise RuntimeError("Official FPL returned non-positive owned-player price")
        expected_selling = calculate_selling_price(
            purchase_price,
            players[player_id].price_tenths,
        )
        if selling_price != expected_selling:
            raise RuntimeError(
                "Official FPL team price state does not match the frozen Official "
                f"market price for element {player_id}: expected sell "
                f"{expected_selling}, got {selling_price}. Restart acquisition from "
                "a fresh Official seal."
            )
        purchase[player_id] = purchase_price
        selling[player_id] = selling_price

    transfers = payload.get("transfers") or {}
    if transfers.get("bank") is None:
        raise RuntimeError("Official FPL authenticated team omitted bank state")
    bank = int(transfers["bank"])
    if bank < 0:
        raise RuntimeError("Official FPL returned a negative bank balance")

    transfer_status = str(transfers.get("status") or "").casefold()
    limit = transfers.get("limit")
    made = int(transfers.get("made", 0) or 0)
    if made < 0:
        raise RuntimeError("Official FPL returned a negative transfer count")

    # In the authenticated my-team contract, limit is the number of free transfers
    # available at the start of the current transfer period and made is how many have
    # already been used. A null limit / unlimited status means a Wildcard/Free Hit or
    # pre-season unlimited window, which V2 does not yet optimise as an ordinary FT GW.
    unlimited = transfer_status == "unlimited" or limit is None
    if unlimited:
        free_transfers = 0
    else:
        limit_value = int(limit)
        if limit_value < 0:
            raise RuntimeError("Official FPL returned a negative free-transfer limit")
        free_transfers = max(0, limit_value - made)

    active_chip = _pending_chip(payload)
    complete = not unlimited
    return TeamState(
        1,
        int(entry_id),
        int(published_gw),
        squad,
        bank,
        free_transfers,
        purchase,
        selling,
        active_chip,
        complete,
    )


def _public_team_state(
    entry_id: int,
    official: OfficialSnapshot,
    *,
    http,
    timeout: float,
    elapsed: list[int],
) -> TeamState | None:
    chosen = None
    published = None
    for gw in elapsed:
        response = http.get(
            f"{BASE}/entry/{int(entry_id)}/event/{gw}/picks/",
            timeout=timeout,
        )
        if response.status_code != 200:
            continue
        payload = response.json()
        picks = payload.get("picks", []) if isinstance(payload, dict) else []
        if len(picks) == 15:
            chosen = payload
            published = gw
            break
    if chosen is None or published is None:
        return None

    history_response = http.get(
        f"{BASE}/entry/{int(entry_id)}/history/",
        timeout=timeout,
    )
    history_response.raise_for_status()
    history = history_response.json()
    entry_history = chosen.get("entry_history") or {}
    bank = int(entry_history.get("bank", 0) or 0)
    active = chosen.get("active_chip")
    free_transfers = replay_free_transfers(
        history,
        published,
        entry_history,
        active,
        official.season,
    )
    squad = tuple(sorted(int(row["element"]) for row in chosen["picks"]))

    # Public picks intentionally describe the last locked deadline, not the editable
    # current team. Never synthesize transaction safety from them. Even if FPL starts
    # returning price fields here, the endpoint still cannot prove that no post-deadline
    # transfer has been made, so discretionary transfer planning must remain withheld.
    purchase = {
        int(row["element"]): int(row["purchase_price"])
        for row in chosen["picks"]
        if row.get("purchase_price") is not None
    }
    selling = {
        int(row["element"]): int(row["selling_price"])
        for row in chosen["picks"]
        if row.get("selling_price") is not None
    }
    return TeamState(
        1,
        int(entry_id),
        int(published),
        squad,
        bank,
        free_transfers,
        purchase,
        selling,
        str(active) if active else None,
        False,
    )


def fetch_team_state(
    entry_id: int,
    official: OfficialSnapshot,
    *,
    session: requests.Session | None = None,
    timeout=20.0,
    now: datetime | None = None,
) -> TeamState | None:
    http = session or requests.Session()
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    elapsed = sorted(
        (
            gw
            for gw, deadline in official.deadlines.items()
            if _dt(deadline) <= now
        ),
        reverse=True,
    )
    headers = _authenticated_headers()
    if headers is not None:
        return _authenticated_team_state(
            entry_id,
            official,
            http=http,
            headers=headers,
            timeout=float(timeout),
            published_gw=elapsed[0] if elapsed else 0,
        )
    if not elapsed:
        return None
    return _public_team_state(
        entry_id,
        official,
        http=http,
        timeout=float(timeout),
        elapsed=elapsed,
    )


def apply_execution_overlay(
    state: TeamState,
    execution: ExecutionDecision | None,
    official: OfficialSnapshot,
) -> TeamState:
    if execution is None:
        return state
    transfers_in = tuple(map(int, execution.transfers_in))
    transfers_out = tuple(map(int, execution.transfers_out))
    if len(transfers_in) != len(transfers_out):
        raise ValueError("execution overlay transfer-in/out counts differ")

    squad = tuple(sorted(map(int, execution.squad_ids)))
    players = official.player_map()
    if set(squad) - set(players):
        raise ValueError("execution overlay contains unknown Official FPL IDs")
    if set(transfers_out) - set(state.squad_ids):
        raise ValueError("execution overlay transfers out a player not currently owned")
    if set(transfers_in) & set(state.squad_ids):
        raise ValueError("execution overlay transfers in an already-owned player")
    if set(transfers_out) - set(state.selling_prices_tenths):
        raise ValueError("execution overlay lacks exact selling price for transfer out")

    purchase = dict(state.purchase_prices_tenths)
    selling = dict(state.selling_prices_tenths)
    bank = int(state.bank_tenths)
    for player_id in transfers_out:
        bank += int(selling[player_id])
        purchase.pop(player_id, None)
        selling.pop(player_id, None)
    for player_id in transfers_in:
        buy_price = int(players[player_id].price_tenths)
        bank -= buy_price
        purchase[player_id] = buy_price
        selling[player_id] = buy_price
    if bank < 0:
        raise ValueError("execution overlay produces a negative bank balance")

    free_transfers = max(0, int(state.free_transfers) - len(transfers_in))
    complete = (
        state.state_complete_for_transfers
        and len(purchase) == 15
        and len(selling) == 15
        and set(purchase) == set(squad)
        and set(selling) == set(squad)
    )
    return TeamState(
        state.schema_version,
        state.entry_id,
        state.published_gw,
        squad,
        bank,
        free_transfers,
        purchase,
        selling,
        state.active_chip,
        complete,
    )
