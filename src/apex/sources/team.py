from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
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
_AUTHENTICATED_PRICE_SCALES = (1, 10)


@dataclass(frozen=True)
class TeamStateAcquisition:
    """Non-secret provenance for the manager-state acquisition boundary.

    Public FPL manager pages are deadline snapshots for other viewers. They are
    useful evidence, but they cannot prove the owner's editable pre-deadline team.
    Authentication material is never stored here; only whether it was present.
    """

    state: TeamState | None
    mode: str
    credential_present: bool
    target_gameweek: int | None
    public_transfers: tuple[dict[str, Any], ...] = ()
    public_transfer_error: str | None = None
    detail: str = ""

    def provenance(self) -> dict[str, Any]:
        rows = list(self.public_transfers)
        encoded = json.dumps(
            rows,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode()
        events = sorted(
            {
                int(row["event"])
                for row in rows
                if row.get("event") is not None
            }
        )
        target_rows = (
            sum(
                1
                for row in rows
                if row.get("event") is not None
                and int(row["event"]) == int(self.target_gameweek)
            )
            if self.target_gameweek is not None
            else 0
        )
        state = self.state
        return {
            "schema_version": 1,
            "mode": self.mode,
            "credential_present": self.credential_present,
            "target_gameweek": self.target_gameweek,
            "published_gw": state.published_gw if state else None,
            "state_complete_for_transfers": (
                state.state_complete_for_transfers if state else False
            ),
            "purchase_price_count": (
                len(state.purchase_prices_tenths) if state else 0
            ),
            "selling_price_count": (
                len(state.selling_prices_tenths) if state else 0
            ),
            "public_transfer_ledger": {
                "available": self.public_transfer_error is None,
                "row_count": len(rows),
                "events": events,
                "last_visible_event": max(events) if events else None,
                "target_gameweek_row_count": target_rows,
                "sha256": hashlib.sha256(encoded).hexdigest(),
                "error": self.public_transfer_error,
                "visibility_contract": (
                    "OWNER_AUTHENTICATED_CURRENT_STATE"
                    if self.mode == "AUTHENTICATED_MY_TEAM"
                    else "PUBLIC_OTHER_VIEWERS_DEADLINE_REDACTED"
                ),
            },
            "detail": self.detail,
        }


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


def _authenticated_money_error() -> RuntimeError:
    """Return a privacy-safe failure for owner-private monetary inconsistencies."""
    return RuntimeError(
        "Official FPL authenticated monetary state is inconsistent with the frozen "
        "Official market snapshot. Restart acquisition from a fresh Official seal."
    )


def _normalise_authenticated_owned_prices(
    picks: list[dict[str, Any]],
    players,
) -> tuple[int, dict[int, int], dict[int, int]]:
    """Prove one source scale against all 15 Official selling-price identities.

    Apex's canonical money unit remains £0.1m. The undocumented owner endpoint has
    historically emitted tenths, but live FPL clients can change representation.
    A non-standard representation is accepted only when one common integer scale
    makes every owned player's purchase/selling pair obey the exact FPL half-profit
    rule against the frozen Official market snapshot. Mixed or ambiguous scales fail.
    """
    raw_rows: list[tuple[int, int, int]] = []
    for row in picks:
        if row.get("purchase_price") is None or row.get("selling_price") is None:
            raise RuntimeError(
                "Official FPL authenticated team omitted purchase/selling prices"
            )
        try:
            player_id = int(row["element"])
            raw_purchase = int(row["purchase_price"])
            raw_selling = int(row["selling_price"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _authenticated_money_error() from exc
        if raw_purchase <= 0 or raw_selling <= 0:
            raise _authenticated_money_error()
        raw_rows.append((player_id, raw_purchase, raw_selling))

    candidates: list[tuple[int, dict[int, int], dict[int, int]]] = []
    for scale in _AUTHENTICATED_PRICE_SCALES:
        purchase: dict[int, int] = {}
        selling: dict[int, int] = {}
        valid = True
        for player_id, raw_purchase, raw_selling in raw_rows:
            if raw_purchase % scale != 0 or raw_selling % scale != 0:
                valid = False
                break
            purchase_price = raw_purchase // scale
            selling_price = raw_selling // scale
            if purchase_price <= 0 or selling_price <= 0:
                valid = False
                break
            if (
                calculate_selling_price(
                    purchase_price,
                    players[player_id].price_tenths,
                )
                != selling_price
            ):
                valid = False
                break
            purchase[player_id] = purchase_price
            selling[player_id] = selling_price
        if valid:
            candidates.append((scale, purchase, selling))

    if len(candidates) != 1:
        raise _authenticated_money_error()
    return candidates[0]


def _derive_current_bank_from_authenticated_ledger(
    entry_id: int,
    *,
    http,
    headers: dict[str, str],
    timeout: float,
    published_gw: int,
    target_gameweek: int | None,
) -> int:
    """Reconstruct current bank in canonical tenths from independent FPL surfaces."""
    if published_gw <= 0 or target_gameweek is None:
        raise _authenticated_money_error()

    baseline_response = http.get(
        f"{BASE}/entry/{int(entry_id)}/event/{int(published_gw)}/picks/",
        timeout=timeout,
    )
    if baseline_response.status_code != 200:
        raise _authenticated_money_error()
    baseline_payload = baseline_response.json()
    if not isinstance(baseline_payload, dict):
        raise _authenticated_money_error()
    entry_history = baseline_payload.get("entry_history") or {}
    if entry_history.get("bank") is None:
        raise _authenticated_money_error()
    try:
        baseline_bank = int(entry_history["bank"])
    except (TypeError, ValueError) as exc:
        raise _authenticated_money_error() from exc
    if baseline_bank < 0:
        raise _authenticated_money_error()

    latest_response = http.get(
        f"{BASE}/entry/{int(entry_id)}/transfers-latest/",
        headers=headers,
        timeout=timeout,
    )
    if latest_response.status_code in {401, 403}:
        raise _authenticated_money_error()
    latest_response.raise_for_status()
    rows = latest_response.json()
    if not isinstance(rows, list):
        raise _authenticated_money_error()

    bank = baseline_bank
    for row in rows:
        if not isinstance(row, dict):
            raise _authenticated_money_error()
        try:
            if int(row.get("entry")) != int(entry_id):
                raise _authenticated_money_error()
            if int(row.get("event")) != int(target_gameweek):
                raise _authenticated_money_error()
            element_in_cost = int(row["element_in_cost"])
            element_out_cost = int(row["element_out_cost"])
        except (KeyError, TypeError, ValueError) as exc:
            raise _authenticated_money_error() from exc
        if element_in_cost <= 0 or element_out_cost <= 0:
            raise _authenticated_money_error()
        bank += element_out_cost - element_in_cost

    if bank < 0:
        raise _authenticated_money_error()
    return bank


def _normalise_authenticated_bank(
    raw_bank_value: Any,
    *,
    owned_price_scale: int,
    entry_id: int,
    http,
    headers: dict[str, str],
    timeout: float,
    published_gw: int,
    target_gameweek: int | None,
) -> int:
    try:
        raw_bank = int(raw_bank_value)
    except (TypeError, ValueError) as exc:
        raise _authenticated_money_error() from exc
    if raw_bank < 0:
        raise RuntimeError("Official FPL returned a negative bank balance")

    # Preserve the established /my-team tenths contract on the standard path. If
    # owned-price representation changed, independently reconstruct current bank
    # from the last locked public bank plus authenticated current-period transfers.
    if owned_price_scale == 1:
        return raw_bank

    expected_bank = _derive_current_bank_from_authenticated_ledger(
        entry_id,
        http=http,
        headers=headers,
        timeout=timeout,
        published_gw=published_gw,
        target_gameweek=target_gameweek,
    )
    normalized_values = {
        raw_bank // scale
        for scale in _AUTHENTICATED_PRICE_SCALES
        if raw_bank % scale == 0 and raw_bank // scale == expected_bank
    }
    if normalized_values != {expected_bank}:
        raise _authenticated_money_error()
    return expected_bank


def _authenticated_team_state(
    entry_id: int,
    official: OfficialSnapshot,
    *,
    http,
    headers: dict[str, str],
    timeout: float,
    published_gw: int,
    target_gameweek: int | None,
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

    try:
        squad = tuple(sorted(int(row["element"]) for row in picks))
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("Official FPL current team contains invalid player identities") from exc
    if len(set(squad)) != 15:
        raise RuntimeError("Official FPL current team contains duplicate player IDs")
    players = official.player_map()
    if set(squad) - set(players):
        raise RuntimeError(
            "Official FPL current team contains a player outside the frozen authority snapshot"
        )

    owned_price_scale, purchase, selling = _normalise_authenticated_owned_prices(
        picks,
        players,
    )

    transfers = payload.get("transfers") or {}
    if transfers.get("bank") is None:
        raise RuntimeError("Official FPL authenticated team omitted bank state")
    bank = _normalise_authenticated_bank(
        transfers["bank"],
        owned_price_scale=owned_price_scale,
        entry_id=entry_id,
        http=http,
        headers=headers,
        timeout=timeout,
        published_gw=published_gw,
        target_gameweek=target_gameweek,
    )

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


def _public_transfer_ledger(
    entry_id: int,
    *,
    http,
    timeout: float,
) -> tuple[tuple[dict[str, Any], ...], str | None]:
    """Acquire public transfer history as evidence, never as current-state proof."""
    try:
        response = http.get(
            f"{BASE}/entry/{int(entry_id)}/transfers/",
            timeout=timeout,
        )
        if response.status_code != 200:
            return (), f"HTTP {response.status_code}"
        payload = response.json()
        if not isinstance(payload, list):
            return (), "public transfer endpoint returned a non-list payload"
        rows = tuple(dict(row) for row in payload if isinstance(row, dict))
        return rows, None
    except Exception as exc:
        return (), f"{type(exc).__name__}: {exc}"


def acquire_team_state(
    entry_id: int,
    official: OfficialSnapshot,
    *,
    session: requests.Session | None = None,
    timeout=20.0,
    now: datetime | None = None,
) -> TeamStateAcquisition:
    """Acquire manager state plus non-secret provenance for the frozen snapshot."""
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
    future = sorted(
        gw
        for gw, deadline in official.deadlines.items()
        if _dt(deadline) > now
    )
    target_gameweek = future[0] if future else None

    headers = _authenticated_headers()
    if headers is not None:
        state = _authenticated_team_state(
            entry_id,
            official,
            http=http,
            headers=headers,
            timeout=float(timeout),
            published_gw=elapsed[0] if elapsed else 0,
            target_gameweek=target_gameweek,
        )
        return TeamStateAcquisition(
            state=state,
            mode="AUTHENTICATED_MY_TEAM",
            credential_present=True,
            target_gameweek=target_gameweek,
            detail=(
                "Official authenticated /my-team state acquired and bound to the "
                "configured entry; purchase/selling prices, bank and remaining FT "
                "state are exact for the editable current team."
            ),
        )

    if not elapsed:
        return TeamStateAcquisition(
            state=None,
            mode="NO_PUBLIC_DEADLINE",
            credential_present=False,
            target_gameweek=target_gameweek,
            detail="No elapsed Official FPL deadline; no public 15-player team exists yet.",
        )

    state = _public_team_state(
        entry_id,
        official,
        http=http,
        timeout=float(timeout),
        elapsed=elapsed,
    )
    public_transfers, transfer_error = _public_transfer_ledger(
        entry_id,
        http=http,
        timeout=float(timeout),
    )
    return TeamStateAcquisition(
        state=state,
        mode="PUBLIC_DEADLINE_FALLBACK",
        credential_present=False,
        target_gameweek=target_gameweek,
        public_transfers=public_transfers,
        public_transfer_error=transfer_error,
        detail=(
            "Public manager state is a locked last-deadline snapshot. Official FPL "
            "redacts another manager's post-deadline transfers until the next "
            "deadline, so this path cannot certify the editable current team and "
            "must withhold discretionary transfer optimisation."
        ),
    )


def fetch_team_state(
    entry_id: int,
    official: OfficialSnapshot,
    *,
    session: requests.Session | None = None,
    timeout=20.0,
    now: datetime | None = None,
) -> TeamState | None:
    """Compatibility wrapper returning only the acquired state."""
    return acquire_team_state(
        entry_id,
        official,
        session=session,
        timeout=timeout,
        now=now,
    ).state


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
