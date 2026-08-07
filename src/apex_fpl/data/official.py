from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from apex_fpl.constants import POSITION
from apex_fpl.data.http import CachedHttp

BASE = "https://fantasy.premierleague.com/api"


@dataclass
class OfficialSnapshot:
    players: pd.DataFrame
    teams: pd.DataFrame
    fixtures: pd.DataFrame
    events: pd.DataFrame
    raw_bootstrap: dict[str, Any]


class OfficialFPLClient:
    def __init__(self, http: CachedHttp):
        self.http = http

    def snapshot(self, force: bool = False) -> OfficialSnapshot:
        bootstrap = self.http.get_json(f"{BASE}/bootstrap-static/", "official_bootstrap", force)
        fixtures = self.http.get_json(f"{BASE}/fixtures/", "official_fixtures", force)
        players = pd.DataFrame(bootstrap["elements"]).copy()
        teams = pd.DataFrame(bootstrap["teams"]).copy()
        events = pd.DataFrame(bootstrap["events"]).copy()
        players["position"] = players["element_type"].map(POSITION)
        players["price"] = pd.to_numeric(players["now_cost"], errors="coerce") / 10.0
        team_map = teams.set_index("id")["name"].to_dict()
        players["team_name"] = players["team"].map(team_map)
        players["player_id"] = players["id"].astype(int)
        return OfficialSnapshot(players, teams, pd.DataFrame(fixtures), events, bootstrap)
