from __future__ import annotations

import pandas as pd

from apex_fpl.data.core_insights import FPLCoreClient


class DummyHttp:
    pass


def test_previous_season_stats_map_by_stable_player_code(monkeypatch):
    def fake_csv(self, name: str, force: bool = False):
        if name == "players.csv" and self.season == "2026-2027":
            return pd.DataFrame(
                [{"player_code": 123, "player_id": 99, "web_name": "Current"}]
            )
        if name == "players.csv" and self.season == "2025-2026":
            return pd.DataFrame(
                [{"player_code": 123, "player_id": 7, "web_name": "Prior"}]
            )
        if name == "playerstats.csv" and self.season == "2025-2026":
            return pd.DataFrame(
                [
                    {
                        "id": 7,
                        "minutes": 2850,
                        "starts": 33,
                        "expected_goals_per_90": 0.55,
                    }
                ]
            )
        raise AssertionError((self.season, name))

    monkeypatch.setattr(FPLCoreClient, "_csv", fake_csv)
    out = FPLCoreClient(DummyHttp(), "2026-2027", ref="pin").previous_season_playerstats()
    row = out.iloc[0]
    assert row["player_id"] == 99
    assert row["previous_minutes"] == 2850
    assert row["previous_starts"] == 33
    assert row["previous_start_probability"] == 33 / 38


def test_previous_season_uses_latest_longitudinal_snapshot(monkeypatch):
    def fake_csv(self, name: str, force: bool = False):
        if name == "players.csv" and self.season == "2026-2027":
            return pd.DataFrame([{"player_code": 123, "player_id": 99}])
        if name == "players.csv" and self.season == "2025-2026":
            return pd.DataFrame([{"player_code": 123, "player_id": 7}])
        if name == "playerstats.csv" and self.season == "2025-2026":
            return pd.DataFrame(
                [
                    {"id": 7, "gw": 1, "minutes": 90, "starts": 1},
                    {"id": 7, "gw": 38, "minutes": 2850, "starts": 33},
                ]
            )
        raise AssertionError((self.season, name))

    monkeypatch.setattr(FPLCoreClient, "_csv", fake_csv)
    out = FPLCoreClient(DummyHttp(), "2026-2027", ref="pin").previous_season_playerstats()
    assert len(out) == 1
    assert out.iloc[0]["previous_minutes"] == 2850
    assert out.iloc[0]["previous_starts"] == 33
