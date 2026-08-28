from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

import requests

from apex.domain.models import (
    OfficialFixture,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
)

BASE_URL = "https://fantasy.premierleague.com/api"
_POSITION = {1: Position.GK, 2: Position.DEF, 3: Position.MID, 4: Position.FWD}


def _canonical_hash(*payloads: Any) -> str:
    payload = json.dumps(
        payloads,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def fetch_official_snapshot(
    *,
    season="2026-2027",
    session: requests.Session | None = None,
    timeout: float = 20.0,
):
    http = session or requests.Session()
    bootstrap_response = http.get(f"{BASE_URL}/bootstrap-static/", timeout=timeout)
    bootstrap_response.raise_for_status()
    fixtures_response = http.get(f"{BASE_URL}/fixtures/", timeout=timeout)
    fixtures_response.raise_for_status()
    bootstrap = bootstrap_response.json()
    fixtures_raw = fixtures_response.json()
    if not isinstance(bootstrap, dict) or not isinstance(
        bootstrap.get("elements"), list
    ):
        raise ValueError("Official FPL bootstrap payload malformed")
    if not isinstance(fixtures_raw, list):
        raise ValueError("Official FPL fixtures payload malformed")

    players = []
    for row in bootstrap["elements"]:
        element_id = int(row["id"])
        element_type = int(row["element_type"])
        if element_type not in _POSITION:
            raise ValueError(
                f"unknown Official FPL element_type {element_type} for {element_id}"
            )
        players.append(
            OfficialPlayer(
                element_id,
                str(row.get("web_name", element_id)),
                int(row["team"]),
                _POSITION[element_type],
                int(row["now_cost"]),
                str(row.get("status", "")),
                bool(row.get("can_transact", True)),
            )
        )
    if len({player.element_id for player in players}) != len(players):
        raise ValueError("Official FPL duplicate element IDs")

    fixtures = tuple(
        OfficialFixture(
            int(row["id"]),
            int(row["event"]) if row.get("event") is not None else None,
            int(row["team_h"]),
            int(row["team_a"]),
            str(row["kickoff_time"]) if row.get("kickoff_time") else None,
        )
        for row in fixtures_raw
    )
    deadlines = {
        int(event["id"]): str(event["deadline_time"])
        for event in bootstrap.get("events", [])
        if event.get("id") is not None and event.get("deadline_time")
    }
    acquired_at = datetime.now(timezone.utc).isoformat()
    digest = _canonical_hash(bootstrap, fixtures_raw)
    return (
        OfficialSnapshot(
            1,
            season,
            acquired_at,
            digest,
            tuple(players),
            fixtures,
            deadlines,
        ),
        {"bootstrap": bootstrap, "fixtures": fixtures_raw},
    )
