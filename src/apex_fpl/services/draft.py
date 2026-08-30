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
        matches = [entry.entry_id for entry in self.entries if entry.entry_name.strip().casefold() == wanted]
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
