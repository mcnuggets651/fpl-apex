from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any

import pandas as pd

from apex_fpl.constants import POSITION
from apex_fpl.data.http import CachedHttp

BASE = "https://fantasy.premierleague.com/api"
VALID_POSITIONS = {1, 2, 3, 4}


def _digest(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate(bootstrap: dict[str, Any], fixtures: list[dict[str, Any]]) -> None:
    elements = bootstrap.get("elements")
    teams = bootstrap.get("teams")
    events = bootstrap.get("events")
    if not isinstance(elements, list) or not elements:
        raise ValueError("Official FPL bootstrap has no player pool")
    if not isinstance(teams, list) or not teams:
        raise ValueError("Official FPL bootstrap has no teams")
    if not isinstance(events, list) or not events:
        raise ValueError("Official FPL bootstrap has no gameweeks")
    team_ids = {int(t["id"]) for t in teams}
    ids = [int(p["id"]) for p in elements]
    if len(ids) != len(set(ids)):
        raise ValueError("Official FPL contains duplicate player IDs")
    for p in elements:
        pid = int(p["id"])
        if int(p.get("element_type", 0)) not in VALID_POSITIONS:
            raise ValueError(f"Official FPL has unknown position for player_id={pid}")
        if int(p.get("team", -1)) not in team_ids:
            raise ValueError(f"Official FPL has unknown club for player_id={pid}")
        if float(p.get("now_cost", 0) or 0) <= 0:
            raise ValueError(f"Official FPL has invalid price for player_id={pid}")
    if not isinstance(fixtures, list):
        raise ValueError("Official FPL fixtures payload is not a list")
    fixture_ids = [int(f["id"]) for f in fixtures if f.get("id") is not None]
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("Official FPL contains duplicate fixture IDs")
    for f in fixtures:
        if int(f.get("team_h", -1)) not in team_ids or int(f.get("team_a", -1)) not in team_ids:
            raise ValueError(f"Official FPL fixture {f.get('id')} references an unknown team")


@dataclass
class OfficialSnapshot:
    players: pd.DataFrame
    teams: pd.DataFrame
    fixtures: pd.DataFrame
    events: pd.DataFrame
    raw_bootstrap: dict[str, Any]
    raw_fixtures: list[dict[str, Any]] | None = None
    retrieved_at: str = ""
    bootstrap_sha256: str = ""
    fixtures_sha256: str = ""


class OfficialFPLClient:
    def __init__(self, http: CachedHttp):
        self.http = http

    def snapshot(self, force: bool = False) -> OfficialSnapshot:
        bootstrap = self.http.get_json(f"{BASE}/bootstrap-static/", "official_bootstrap", force)
        fixtures = self.http.get_json(f"{BASE}/fixtures/", "official_fixtures", force)
        _validate(bootstrap, fixtures)
        players = pd.DataFrame(bootstrap["elements"]).copy()
        teams = pd.DataFrame(bootstrap["teams"]).copy()
        events = pd.DataFrame(bootstrap["events"]).copy()
        players["position"] = players["element_type"].map(POSITION)
        players["price"] = pd.to_numeric(players["now_cost"], errors="coerce") / 10.0
        team_map = teams.set_index("id")["name"].to_dict()
        players["team_name"] = players["team"].map(team_map)
        players["player_id"] = players["id"].astype(int)
        return OfficialSnapshot(
            players=players,
            teams=teams,
            fixtures=pd.DataFrame(fixtures),
            events=events,
            raw_bootstrap=bootstrap,
            raw_fixtures=fixtures,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
            bootstrap_sha256=_digest(bootstrap),
            fixtures_sha256=_digest(fixtures),
        )
