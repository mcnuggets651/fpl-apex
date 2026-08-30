from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

DRAFT_API_BASE = "https://draft.premierleague.com/api"


class DraftAPIError(RuntimeError):
    """Raised when the official FPL Draft API cannot provide a usable response."""


@dataclass(frozen=True)
class DraftLeagueEntry:
    entry_id: int
    entry_name: str
    player_first_name: str = ""
    player_last_name: str = ""


@dataclass(frozen=True)
class DraftLeagueSnapshot:
    league_id: int
    league_name: str
    entries: tuple[DraftLeagueEntry, ...]
    element_status: tuple[dict[str, Any], ...]

    @property
    def available_element_ids(self) -> tuple[int, ...]:
        return tuple(
            int(row["element"])
            for row in self.element_status
            if row.get("status") == "a" and row.get("element") is not None
        )

    @property
    def locked_element_ids(self) -> tuple[int, ...]:
        return tuple(
            int(row["element"])
            for row in self.element_status
            if row.get("status") == "l" and row.get("element") is not None
        )

    def owner_by_element(self) -> dict[int, int]:
        owners: dict[int, int] = {}
        for row in self.element_status:
            element = row.get("element")
            owner = row.get("owner")
            if element is None or owner is None:
                continue
            owners[int(element)] = int(owner)
        return owners

    def resolve_entry_id(self, entry_name: str) -> int:
        wanted = entry_name.strip().casefold()
        matches = [
            entry.entry_id
            for entry in self.entries
            if entry.entry_name.strip().casefold() == wanted
        ]
        if not matches:
            raise DraftAPIError(
                f"Draft entry {entry_name!r} was not found in league {self.league_id}"
            )
        if len(matches) > 1:
            raise DraftAPIError(
                f"Draft entry name {entry_name!r} is ambiguous in league {self.league_id}"
            )
        return matches[0]


class DraftFPLClient:
    """Small read-only client for official FPL Draft league state.

    Draft support is intentionally separate from the canonical Classic FPL production
    engine. This client is for waiver/trade/ownership diagnostics only.
    """

    def __init__(
        self,
        session: requests.Session | None = None,
        *,
        base_url: str = DRAFT_API_BASE,
        timeout: float = 20.0,
    ) -> None:
        self.session = session or requests.Session()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get_json(self, path: str) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            raise DraftAPIError(f"FPL Draft API request failed for {url}: {exc}") from exc

    def league_details(self, league_id: int) -> dict[str, Any]:
        return dict(self._get_json(f"league/{int(league_id)}/details"))

    def element_status(self, league_id: int) -> list[dict[str, Any]]:
        payload = self._get_json(f"league/{int(league_id)}/element-status")
        if isinstance(payload, dict):
            rows = payload.get("element_status", payload.get("elements", []))
        else:
            rows = payload
        if not isinstance(rows, list):
            raise DraftAPIError("FPL Draft element-status response is not a list")
        return [dict(row) for row in rows]

    def bootstrap_static(self) -> dict[str, Any]:
        return dict(self._get_json("bootstrap-static"))

    def snapshot(self, league_id: int) -> DraftLeagueSnapshot:
        details = self.league_details(league_id)
        league = details.get("league") or {}
        raw_entries = details.get("league_entries") or []
        entries = tuple(
            DraftLeagueEntry(
                entry_id=int(row["id"]),
                entry_name=str(row.get("entry_name") or ""),
                player_first_name=str(row.get("player_first_name") or ""),
                player_last_name=str(row.get("player_last_name") or ""),
            )
            for row in raw_entries
            if row.get("id") is not None
        )
        return DraftLeagueSnapshot(
            league_id=int(league_id),
            league_name=str(league.get("name") or ""),
            entries=entries,
            element_status=tuple(self.element_status(league_id)),
        )


def build_draft_pool(
    snapshot: DraftLeagueSnapshot,
    bootstrap: dict[str, Any],
) -> list[dict[str, Any]]:
    """Join Draft ownership status to Draft player metadata.

    Draft element IDs are intentionally kept in their own namespace; they are not
    assumed to equal Classic-FPL element IDs. Apex projection joins should therefore
    reconcile on identity fields (name/club/position) rather than raw numeric ID.
    """

    teams = {
        int(row["id"]): str(row.get("name") or row.get("short_name") or "")
        for row in bootstrap.get("teams", [])
        if row.get("id") is not None
    }
    positions = {
        int(row["id"]): str(row.get("singular_name_short") or row.get("singular_name") or "")
        for row in bootstrap.get("element_types", [])
        if row.get("id") is not None
    }
    players = {
        int(row["id"]): row
        for row in bootstrap.get("elements", [])
        if row.get("id") is not None
    }
    entry_names = {entry.entry_id: entry.entry_name for entry in snapshot.entries}

    output: list[dict[str, Any]] = []
    for status_row in snapshot.element_status:
        element_raw = status_row.get("element")
        if element_raw is None:
            continue
        element_id = int(element_raw)
        player = players.get(element_id, {})
        owner_raw = status_row.get("owner")
        owner_id = int(owner_raw) if owner_raw is not None else None
        output.append(
            {
                "draft_element_id": element_id,
                "first_name": str(player.get("first_name") or ""),
                "second_name": str(player.get("second_name") or ""),
                "web_name": str(player.get("web_name") or player.get("second_name") or ""),
                "team": teams.get(int(player.get("team") or 0), ""),
                "position": positions.get(int(player.get("element_type") or 0), ""),
                "status": str(status_row.get("status") or ""),
                "owner_entry_id": owner_id,
                "owner_entry_name": entry_names.get(owner_id, "") if owner_id is not None else "",
            }
        )
    return output
