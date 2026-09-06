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


def _official_authority_payload(
    bootstrap: dict[str, Any], fixtures_raw: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return only Official FPL facts that can change an Apex decision.

    The raw bootstrap contains continuously changing market/ownership counters such as
    ``transfers_in_event`` and ``selected_by_percent``. Those values are useful raw
    evidence but are not part of Apex's factual authority contract. Hashing the whole
    payload made a long provider build fail merely because an irrelevant counter moved.

    The acquisition sandwich therefore seals the subset Apex is actually allowed to
    treat as canonical: stable player identity/team/position/price/availability,
    transaction state, event deadlines, and fixture identity/schedule/state. Raw
    payload hashes are retained separately for forensic replay.
    """
    players = []
    for row in bootstrap.get("elements", []):
        players.append(
            {
                "id": row.get("id"),
                "code": row.get("code"),
                "team": row.get("team"),
                "element_type": row.get("element_type"),
                "now_cost": row.get("now_cost"),
                "status": row.get("status"),
                "can_transact": row.get("can_transact", True),
                "chance_of_playing_this_round": row.get(
                    "chance_of_playing_this_round"
                ),
                "chance_of_playing_next_round": row.get(
                    "chance_of_playing_next_round"
                ),
                "news": row.get("news", ""),
                "news_added": row.get("news_added"),
            }
        )
    players.sort(key=lambda row: int(row["id"]))

    events = []
    for row in bootstrap.get("events", []):
        if row.get("id") is None:
            continue
        events.append(
            {
                "id": row.get("id"),
                "deadline_time": row.get("deadline_time"),
                "finished": row.get("finished"),
                "is_current": row.get("is_current"),
                "is_next": row.get("is_next"),
            }
        )
    events.sort(key=lambda row: int(row["id"]))

    fixtures = []
    for row in fixtures_raw:
        fixtures.append(
            {
                "id": row.get("id"),
                "event": row.get("event"),
                "team_h": row.get("team_h"),
                "team_a": row.get("team_a"),
                "kickoff_time": row.get("kickoff_time"),
                "started": row.get("started"),
                "finished": row.get("finished"),
                "provisional_start_time": row.get("provisional_start_time"),
            }
        )
    fixtures.sort(key=lambda row: int(row["id"]))

    return {"players": players, "events": events, "fixtures": fixtures}


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

    teams_raw = bootstrap.get("teams")
    team_ids: set[int] | None = None
    if teams_raw is not None:
        if not isinstance(teams_raw, list):
            raise ValueError("Official FPL teams payload malformed")
        team_ids = {int(row["id"]) for row in teams_raw}
        if len(team_ids) != len(teams_raw):
            raise ValueError("Official FPL duplicate team IDs")

    players = []
    for row in bootstrap["elements"]:
        element_id = int(row["id"])
        element_type = int(row["element_type"])
        if element_type not in _POSITION:
            raise ValueError(
                f"unknown Official FPL element_type {element_type} for {element_id}"
            )
        raw_code = row.get("code")
        if raw_code in (None, ""):
            raise ValueError(f"Official FPL player {element_id} missing stable code")
        team_id = int(row["team"])
        if team_ids is not None and team_id not in team_ids:
            raise ValueError(
                f"Official FPL player {element_id} references unknown team {team_id}"
            )
        price_tenths = int(row["now_cost"])
        if price_tenths <= 0:
            raise ValueError(
                f"Official FPL player {element_id} has nonpositive price {price_tenths}"
            )
        can_transact = row.get("can_transact", True)
        if not isinstance(can_transact, bool):
            raise ValueError(
                f"Official FPL player {element_id} has non-boolean can_transact"
            )
        players.append(
            OfficialPlayer(
                element_id=element_id,
                web_name=str(row.get("web_name", element_id)),
                team_id=team_id,
                position=_POSITION[element_type],
                price_tenths=price_tenths,
                status=str(row.get("status", "")),
                can_transact=can_transact,
                fpl_code=int(raw_code),
            )
        )
    if len({player.element_id for player in players}) != len(players):
        raise ValueError("Official FPL duplicate element IDs")
    codes = [player.fpl_code for player in players]
    if len(set(codes)) != len(codes):
        raise ValueError("Official FPL duplicate stable player codes")

    fixture_ids: set[int] = set()
    fixtures: list[OfficialFixture] = []
    for row in fixtures_raw:
        fixture_id = int(row["id"])
        if fixture_id in fixture_ids:
            raise ValueError(f"Official FPL duplicate fixture ID {fixture_id}")
        fixture_ids.add(fixture_id)
        team_h = int(row["team_h"])
        team_a = int(row["team_a"])
        if team_ids is not None and (team_h not in team_ids or team_a not in team_ids):
            raise ValueError(
                f"Official FPL fixture {fixture_id} references unknown team"
            )
        fixtures.append(
            OfficialFixture(
                fixture_id,
                int(row["event"]) if row.get("event") is not None else None,
                team_h,
                team_a,
                str(row["kickoff_time"]) if row.get("kickoff_time") else None,
            )
        )

    deadlines = {
        int(event["id"]): str(event["deadline_time"])
        for event in bootstrap.get("events", [])
        if event.get("id") is not None and event.get("deadline_time")
    }
    acquired_at = datetime.now(timezone.utc).isoformat()
    authority_payload = _official_authority_payload(bootstrap, fixtures_raw)
    authority_hash = _canonical_hash(authority_payload)
    raw_hashes = {
        "bootstrap_sha256": _canonical_hash(bootstrap),
        "fixtures_sha256": _canonical_hash(fixtures_raw),
    }
    return (
        OfficialSnapshot(
            1,
            season,
            acquired_at,
            authority_hash,
            tuple(players),
            tuple(fixtures),
            deadlines,
        ),
        {
            "bootstrap": bootstrap,
            "fixtures": fixtures_raw,
            "authority_payload": authority_payload,
            "authority_sha256": authority_hash,
            "raw_hashes": raw_hashes,
        },
    )
