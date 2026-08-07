from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from apex_fpl.data.http import CachedHttp
from apex_fpl.rules import MAX_ROLLED_FREE_TRANSFERS

BASE = "https://fantasy.premierleague.com/api"


@dataclass
class PublicEntryState:
    entry_id: int
    entry_name: str
    manager_name: str
    published_gw: int
    squad: set[int]
    bank: float
    free_transfers: int
    team_value: float | None
    captain_id: int | None
    vice_captain_id: int | None
    active_chip: str | None
    transfers: list[dict[str, Any]]
    chips_used: list[dict[str, Any]]


def _parse_deadline(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _next_free_transfers(ft: int, transfers: int) -> int:
    return min(MAX_ROLLED_FREE_TRANSFERS, max(1, int(ft) - int(transfers) + 1))


def derive_next_free_transfers(
    history: dict[str, Any],
    latest_event: int,
    latest_entry_history: dict[str, Any] | None = None,
    latest_active_chip: str | None = None,
) -> int:
    """Replay public entry history to estimate FTs available for the next deadline.

    Modern FPL preserves banked free transfers when a Wildcard or Free Hit is used.
    The latest picks payload is allowed to override the history row because it is
    available immediately after the deadline and can be fresher than /history/.
    """
    rows = {
        int(row.get("event")): dict(row)
        for row in history.get("current", [])
        if row.get("event") is not None and int(row.get("event")) <= latest_event
    }
    if latest_entry_history:
        row = dict(latest_entry_history)
        row.setdefault("event", latest_event)
        rows[latest_event] = row

    chips = {
        int(row.get("event")): str(row.get("name", "")).casefold().replace("_", "")
        for row in history.get("chips", [])
        if row.get("event") is not None
    }
    if latest_active_chip:
        chips[latest_event] = str(latest_active_chip).casefold().replace("_", "")

    ft = 1
    for gw in range(1, latest_event + 1):
        row = rows.get(gw, {})
        transfers = int(row.get("event_transfers", 0) or 0)
        chip = chips.get(gw, "")
        if chip in {"wildcard", "freehit"}:
            # Banked FTs are retained through these chips; no additional roll is
            # awarded for the chip week itself.
            ft = min(MAX_ROLLED_FREE_TRANSFERS, max(1, ft))
        else:
            ft = _next_free_transfers(ft, transfers)
    return ft


class OfficialEntryClient:
    """Read a manager's public FPL state from their entry ID.

    Public picks are deadline snapshots. They are perfect for starting a new
    Gameweek transfer analysis, but intentionally do not claim to expose private
    transfers made after the latest deadline and before the next one.
    """

    def __init__(self, http: CachedHttp, entry_id: int):
        self.http = http
        self.entry_id = int(entry_id)

    def summary(self, force: bool = False) -> dict[str, Any]:
        return self.http.get_json(
            f"{BASE}/entry/{self.entry_id}/",
            f"entry_{self.entry_id}_summary",
            force,
        )

    def history(self, force: bool = False) -> dict[str, Any]:
        return self.http.get_json(
            f"{BASE}/entry/{self.entry_id}/history/",
            f"entry_{self.entry_id}_history",
            force,
        )

    def transfers(self, force: bool = False) -> list[dict[str, Any]]:
        payload = self.http.get_json(
            f"{BASE}/entry/{self.entry_id}/transfers/",
            f"entry_{self.entry_id}_transfers",
            force,
        )
        return payload if isinstance(payload, list) else []

    def picks(self, event: int, force: bool = False) -> dict[str, Any]:
        return self.http.get_json(
            f"{BASE}/entry/{self.entry_id}/event/{int(event)}/picks/",
            f"entry_{self.entry_id}_gw{int(event)}_picks",
            force,
        )

    def latest_public_state(
        self,
        events: pd.DataFrame,
        force: bool = False,
        now: datetime | None = None,
    ) -> PublicEntryState | None:
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        summary = self.summary(force=force)

        eligible: list[int] = []
        if not events.empty:
            for _, row in events.iterrows():
                deadline = _parse_deadline(row.get("deadline_time"))
                if deadline is not None and deadline <= now:
                    eligible.append(int(row["id"]))
        if not eligible:
            # Before GW1 this is the expected result. The entry summary alone is
            # enough to prove the configured ID exists; there is no public draft.
            return None

        payload: dict[str, Any] | None = None
        published_gw: int | None = None
        for gw in sorted(set(eligible), reverse=True):
            try:
                candidate = self.picks(gw, force=force)
            except Exception:
                continue
            picks = candidate.get("picks", []) if isinstance(candidate, dict) else []
            if len(picks) == 15:
                payload = candidate
                published_gw = gw
                break
        if payload is None or published_gw is None:
            return None

        # History/transfer calls are only needed once a public deadline squad
        # actually exists. This keeps the pre-GW1 sync minimal and robust.
        history = self.history(force=force)
        try:
            transfers = self.transfers(force=force)
        except Exception:
            # Transfer history improves selling-price reconstruction but is not
            # necessary to identify the manager's published 15-player squad.
            transfers = []

        picks = payload.get("picks", [])
        squad = {int(row["element"]) for row in picks if row.get("element") is not None}
        if len(squad) != 15:
            return None
        entry_history = payload.get("entry_history") or {}
        bank_tenths = entry_history.get("bank", summary.get("last_deadline_bank", 0))
        value_tenths = entry_history.get("value", summary.get("last_deadline_value"))
        active_chip = payload.get("active_chip")
        free_transfers = derive_next_free_transfers(
            history,
            published_gw,
            latest_entry_history=entry_history,
            latest_active_chip=active_chip,
        )
        captain = next(
            (int(row["element"]) for row in picks if row.get("is_captain")),
            None,
        )
        vice = next(
            (int(row["element"]) for row in picks if row.get("is_vice_captain")),
            None,
        )
        manager_name = " ".join(
            str(summary.get(key, "")).strip()
            for key in ("player_first_name", "player_last_name")
            if str(summary.get(key, "")).strip()
        )
        chip_rows = [
            dict(row)
            for row in history.get("chips", [])
            if isinstance(row, dict) and row.get("event") is not None
        ]
        return PublicEntryState(
            entry_id=self.entry_id,
            entry_name=str(summary.get("name", f"Entry {self.entry_id}")),
            manager_name=manager_name,
            published_gw=published_gw,
            squad=squad,
            bank=float(bank_tenths or 0) / 10.0,
            free_transfers=free_transfers,
            team_value=(float(value_tenths) / 10.0 if value_tenths is not None else None),
            captain_id=captain,
            vice_captain_id=vice,
            active_chip=str(active_chip) if active_chip else None,
            transfers=transfers,
            chips_used=chip_rows,
        )