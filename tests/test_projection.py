import pandas as pd
import pytest

import apex_fpl.models.projection as projection
from apex_fpl.models.projection import project_players


def _player(pid, team, pos="MID", *, xg90=0.3, xa90=0.2):
    return {
        "player_id": pid,
        "first_name": f"Player{pid}",
        "second_name": "Test",
        "team": team,
        "position": pos,
        "expected_minutes": 80,
        "expected_goals_per_90": xg90,
        "expected_assists_per_90": xa90,
    }


@pytest.fixture(autouse=True)
def _stable_understat_rates(monkeypatch):
    def rates(players):
        return pd.DataFrame(
            {
                "player_id": players["player_id"].astype(int),
                "understat_xg90": 0.3,
                "understat_xa90": 0.2,
            }
        )

    monkeypatch.setattr(projection, "_production_understat_player_rates", rates)


def test_blank_gameweek_projects_zero():
    players = pd.DataFrame([_player(1, 1), _player(2, 2)])
    fx = pd.DataFrame([{"team": 1, "gw": 1, "attack_multiplier": 1.0, "defence_multiplier": 1.0}])
    out = project_players(players, fx, [1])
    assert out.loc[out.player_id == 1, "apex_xp"].iloc[0] > 0
    assert out.loc[out.player_id == 2, "apex_xp"].iloc[0] == 0


def test_double_gameweek_generates_two_fixture_rows():
    players = pd.DataFrame([_player(1, 1)])
    fx = pd.DataFrame([
        {"team": 1, "gw": 1, "attack_multiplier": 1.0, "defence_multiplier": 1.0},
        {"team": 1, "gw": 1, "attack_multiplier": 1.1, "defence_multiplier": 0.9},
    ])
    out = project_players(players, fx, [1])
    assert len(out) == 2
    assert out.apex_xp.sum() > out.apex_xp.iloc[0]


def test_promoted_understat_blend_changes_direct_attack_only(monkeypatch):
    monkeypatch.setattr(
        projection,
        "_production_understat_player_rates",
        lambda players: pd.DataFrame(
            [{"player_id": 1, "understat_xg90": 0.7, "understat_xa90": 0.6}]
        ),
    )
    players = pd.DataFrame([_player(1, 1, xg90=0.3, xa90=0.2)])
    fx = pd.DataFrame(
        [{"team": 1, "gw": 1, "attack_multiplier": 1.0, "defence_multiplier": 1.0}]
    )
    out = project_players(players, fx, [1]).iloc[0]

    assert out["model_xg90"] == pytest.approx(0.3)
    assert out["model_xa90"] == pytest.approx(0.2)
    assert out["attack_model_xg90"] == pytest.approx(0.5)
    assert out["attack_model_xa90"] == pytest.approx(0.32)
    assert bool(out["understat_player_matched"]) is True
    assert bool(out["understat_player_repricable"]) is True


def test_zero_baseline_attack_is_not_repriced(monkeypatch):
    monkeypatch.setattr(
        projection,
        "_production_understat_player_rates",
        lambda players: pd.DataFrame(
            [{"player_id": 1, "understat_xg90": 0.7, "understat_xa90": 0.6}]
        ),
    )
    players = pd.DataFrame([_player(1, 1, xg90=0.0, xa90=0.0)])
    fx = pd.DataFrame(
        [{"team": 1, "gw": 1, "attack_multiplier": 1.0, "defence_multiplier": 1.0}]
    )
    out = project_players(players, fx, [1]).iloc[0]

    assert out["attack_model_xg90"] == pytest.approx(0.0)
    assert out["attack_model_xa90"] == pytest.approx(0.0)
    assert bool(out["understat_player_matched"]) is True
    assert bool(out["understat_player_repricable"]) is False
