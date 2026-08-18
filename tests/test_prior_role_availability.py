import pandas as pd
import pytest

from apex_fpl.data.core_insights import FPLCoreClient


def test_longitudinal_role_counts_exclude_old_injury_absence() -> None:
    rows = pd.DataFrame(
        {
            "player_id": [1, 1, 1, 1],
            "gw": [1, 2, 3, 4],
            "minutes": [90, 90, 90, 180],
            "starts": [1, 1, 1, 2],
            "status": ["a", "i", "i", "a"],
        }
    )

    out = FPLCoreClient._longitudinal_role_counts(rows).iloc[0]

    assert out["appearances"] == 2
    assert out["role_games"] == 2


def test_longitudinal_role_counts_keep_healthy_unused_bench_as_rotation() -> None:
    rows = pd.DataFrame(
        {
            "player_id": [1, 1, 1, 1],
            "gw": [1, 2, 3, 4],
            "minutes": [90, 90, 180, 180],
            "starts": [1, 1, 2, 2],
            "status": ["a", "a", "a", "a"],
        }
    )

    out = FPLCoreClient._longitudinal_role_counts(rows).iloc[0]

    assert out["appearances"] == 2
    assert out["role_games"] == 4


def test_previous_season_role_is_conditional_on_available_games(monkeypatch) -> None:
    client = object.__new__(FPLCoreClient)
    client.season = "2026-2027"
    client.ref = "pin"
    client.http = None

    current_players = pd.DataFrame(
        {"player_code": [101], "player_id": [11], "team_code": [21]}
    )
    prior_players = pd.DataFrame(
        {"player_code": [101], "player_id": [1], "team_code": [21]}
    )
    prior_stats = pd.DataFrame(
        {
            "player_id": [1, 1, 1, 1],
            "gw": [1, 2, 3, 4],
            "minutes": [90, 90, 90, 180],
            "starts": [1, 1, 1, 2],
            "status": ["a", "i", "i", "a"],
            "expected_goals_per_90": [0.4, 0.4, 0.4, 0.4],
            "expected_assists_per_90": [0.3, 0.3, 0.3, 0.3],
            "defensive_contribution_per_90": [2.0, 2.0, 2.0, 2.0],
        }
    )

    original_init = FPLCoreClient.__init__
    original_players = FPLCoreClient.players
    original_playerstats = FPLCoreClient.playerstats

    def fake_init(self, http, season, ref="main"):
        self.http = http
        self.season = season
        self.ref = ref

    def fake_players(self, force=False):
        if self is client:
            return current_players
        return prior_players

    def fake_playerstats(self, force=False):
        return prior_stats

    monkeypatch.setattr(FPLCoreClient, "__init__", fake_init)
    monkeypatch.setattr(FPLCoreClient, "players", fake_players)
    monkeypatch.setattr(FPLCoreClient, "playerstats", fake_playerstats)
    try:
        out = client.previous_season_playerstats().iloc[0]
    finally:
        monkeypatch.setattr(FPLCoreClient, "__init__", original_init)
        monkeypatch.setattr(FPLCoreClient, "players", original_players)
        monkeypatch.setattr(FPLCoreClient, "playerstats", original_playerstats)

    assert out["previous_appearances"] == 2
    assert out["previous_role_games"] == 2
    assert out["previous_start_probability"] == pytest.approx(1.0)
    assert out["previous_minutes_per_match"] == pytest.approx(90.0)
