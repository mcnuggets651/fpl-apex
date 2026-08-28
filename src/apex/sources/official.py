from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import requests

from apex.domain.models import OfficialFixture, OfficialPlayer, OfficialSnapshot, Position


BASE_URL = "https://fantasy.premierleague.com/api"
_POSITION = {1: Position.GK, 2: Position.DEF, 3: Position.MID, 4: Position.FWD}


def _canonical_hash(*payloads: Any) -> str:
    raw = json.dumps(payloads, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def fetch_official_snapshot(
    *,
    season: str = "2026-2027",
    session: requests.Session | None = None,
    timeout: float = 20.0,
) -> tuple[OfficialSnapshot, dict[str, Any]]:
    http = session or requests.Session()
    bootstrap_response = http.get(f"{BASE_URL}/bootstrap-static/", timeout=timeout)
    bootstrap_response.raise_for_status()
    fixtures_response = http.get(f"{BASE_URL}/fixtures/", timeout=timeout)
    fixtures_response.raise_for_status()
    bootstrap = bootstrap_response.json()
    fixtures_raw = fixtures_response.json()
    if not isinstance(bootstrap, dict) or not isinstance(bootstrap.get("elements"), list):
        raise ValueError("Official FPL bootstrap payload malformed")
    if not isinstance(fixtures_raw, list):
        raise ValueError("Official FPL fixtures payload malformed")

    players: list[OfficialPlayer] = []
    for row in bootstrap["elements"]:
        element_id = int(row["id"])
        element_type = int(row["element_type"])
        if element_type not in _POSITION:
            raise ValueError(
                f"unknown Official FPL element_type {element_type} for {element_id}"
            )
        players.append(
            OfficialPlayer(
                element_id=element_id,
                web_name=str(row.get("web_name", element_id)),
                team_id=int(row["team"]),
                position=_POSITION[element_type],
                price_tenths=int(row["now_cost"]),
                status=str(row.get("status", "")),
                can_transact=bool(row.get("can_transact", True)),
            )
        )
    if len({p.element_id for p in players}) != len(players):
        raise ValueError("Official FPL duplicate element IDs")

    fixtures: list[OfficialFixture] = []
    for row in fixtures_raw:
        fixtures.append(
            OfficialFixture(
                fixture_id=int(row["id"]),
                gameweek=(int(row["event"]) if row.get("event") is not None else None),
                home_team_id=int(row["team_h"]),
                away_team_id=int(row["team_a"]),
                kickoff_time=(str(row["kickoff_time"]) if row.get("kickoff_time") else None),
            )
        )
    deadlines = {
        int(event["id"]): str(event["deadline_time"])
        for event in bootstrap.get("events", [])
        if event.get("id") is not None and event.get("deadline_time")
    }
    acquired_at = datetime.now(timezone.utc).isoformat()
    digest = _canonical_hash(bootstrap, fixtures_raw)
    snapshot = OfficialSnapshot(
        schema_version=1,
        season=season,
        acquired_at=acquired_at,
        source_hash=digest,
        players=tuple(players),
        fixtures=tuple(fixtures),
        deadlines=deadlines,
    )
    return snapshot, {"bootstrap": bootstrap, "fixtures": fixtures_raw}
