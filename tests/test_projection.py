import pandas as pd

from apex_fpl.models.projection import project_players


def _player(pid, team, pos="MID"):
    return {
        "player_id": pid,
        "team": team,
        "position": pos,
        "expected_minutes": 80,
        "expected_goals_per_90": 0.3,
        "expected_assists_per_90": 0.2,
    }


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
