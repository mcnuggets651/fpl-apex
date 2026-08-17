import pandas as pd
import pytest

from apex_fpl.data.core_insights import FPLCoreClient


def test_stable_identity_rows_deduplicates_identical_rows() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 101, 202],
            "player_id": [1, 1, 2],
        }
    )

    result = FPLCoreClient._stable_identity_rows(rows, "test")

    assert result.to_dict("records") == [
        {"player_code": 101, "player_id": 1},
        {"player_code": 202, "player_id": 2},
    ]


def test_stable_identity_rows_rejects_conflicting_code_mapping() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 101],
            "player_id": [1, 2],
        }
    )

    with pytest.raises(ValueError, match="conflicting player_code mappings"):
        FPLCoreClient._stable_identity_rows(rows, "test")


def test_stable_identity_rows_rejects_conflicting_id_mapping() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 202],
            "player_id": [1, 1],
        }
    )

    with pytest.raises(ValueError, match="conflicting player_id mappings"):
        FPLCoreClient._stable_identity_rows(rows, "test")


def test_stable_identity_rows_preserves_unambiguous_team_code() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 101, 202],
            "player_id": [1, 1, 2],
            "team_code": [90, 90, 14],
        }
    )

    result = FPLCoreClient._stable_identity_rows(rows, "test")

    assert result.to_dict("records") == [
        {"player_code": 101, "player_id": 1, "team_code": 90},
        {"player_code": 202, "player_id": 2, "team_code": 14},
    ]


def test_stable_identity_rows_rejects_conflicting_team_membership() -> None:
    rows = pd.DataFrame(
        {
            "player_code": [101, 101],
            "player_id": [1, 1],
            "team_code": [90, 21],
        }
    )

    with pytest.raises(ValueError, match="conflicting team_code mappings"):
        FPLCoreClient._stable_identity_rows(rows, "test")


def test_previous_season_bridge_marks_club_change_without_changing_identity(monkeypatch) -> None:
    client = object.__new__(FPLCoreClient)
    client.season = "2026-2027"
    client.ref = "pin"
    client.http = None

    current_players = pd.DataFrame(
        {
            "player_code": [101, 202],
            "player_id": [11, 22],
            "team_code": [21, 14],
        }
    )
    prior_players = pd.DataFrame(
        {
            "player_code": [101, 202],
            "player_id": [1, 2],
            "team_code": [90, 14],
        }
    )
    prior_stats = pd.DataFrame(
        {
            "player_id": [1, 2],
            "minutes": [3000, 2800],
            "starts": [34, 32],
        }
    )

    monkeypatch.setattr(client, "players", lambda force=False: current_players)

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
        out = client.previous_season_playerstats()
    finally:
        monkeypatch.setattr(FPLCoreClient, "__init__", original_init)
        monkeypatch.setattr(FPLCoreClient, "players", original_players)
        monkeypatch.setattr(FPLCoreClient, "playerstats", original_playerstats)

    moved = out.loc[out.player_id == 11].iloc[0]
    stayed = out.loc[out.player_id == 22].iloc[0]
    assert bool(moved["club_changed"]) is True
    assert moved["previous_team_code"] == 90
    assert moved["current_team_code"] == 21
    assert bool(stayed["club_changed"]) is False
