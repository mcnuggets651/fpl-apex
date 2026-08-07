from __future__ import annotations

import pandas as pd

from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.models.fixtures import fixture_multipliers


class DummyHttp:
    pass


def test_core_elo_maps_historical_team_code_to_official_fpl_id(monkeypatch):
    client = FPLCoreClient(DummyHttp(), "2026-2027", ref="pin")

    def fake_csv(name: str, force: bool = False):
        if name == "teams.csv":
            return pd.DataFrame(
                [
                    {"code": 3, "id": 1, "name": "Arsenal"},
                    {"code": 9, "id": 7, "name": "Coventry"},
                ]
            )
        if name == "By Gameweek/GW1/fixtures.csv":
            return pd.DataFrame(
                [
                    {
                        "gameweek": 1,
                        "home_team": 3,
                        "home_team_elo": 2060,
                        "away_team": 9,
                        "away_team_elo": 1660,
                    }
                ]
            )
        raise AssertionError(name)

    monkeypatch.setattr(client, "_csv", fake_csv)
    out = client.fixture_elos([1])
    home = out[(out.team == 1) & (out.is_home)].iloc[0]
    away = out[(out.team == 7) & (~out.is_home)].iloc[0]
    assert home["opponent"] == 7
    assert home["team_elo"] == 2060
    assert away["opponent"] == 1
    assert away["team_elo"] == 1660


def test_elo_strengthens_fixture_prior_without_overpowering_official_strength():
    teams = pd.DataFrame(
        [
            {
                "id": 1,
                "strength": 1000,
                "strength_attack_home": 1000,
                "strength_defence_home": 1000,
                "strength_attack_away": 1000,
                "strength_defence_away": 1000,
            },
            {
                "id": 2,
                "strength": 1000,
                "strength_attack_home": 1000,
                "strength_defence_home": 1000,
                "strength_attack_away": 1000,
                "strength_defence_away": 1000,
            },
        ]
    )
    fixtures = pd.DataFrame([{"event": 1, "team_h": 1, "team_a": 2}])
    base = fixture_multipliers(fixtures, teams, [1])
    elos = pd.DataFrame(
        [
            {
                "gw": 1,
                "team": 1,
                "opponent": 2,
                "is_home": True,
                "team_elo": 2050,
                "opponent_elo": 1650,
            },
            {
                "gw": 1,
                "team": 2,
                "opponent": 1,
                "is_home": False,
                "team_elo": 1650,
                "opponent_elo": 2050,
            },
        ]
    )
    adjusted = fixture_multipliers(fixtures, teams, [1], core_elos=elos)
    base_home = base[base.team == 1].iloc[0]
    elo_home = adjusted[adjusted.team == 1].iloc[0]
    assert elo_home["expected_team_goals"] > base_home["expected_team_goals"]
    assert 1.0 < elo_home["elo_multiplier"] < 1.25
    assert elo_home["team_elo"] == 2050
