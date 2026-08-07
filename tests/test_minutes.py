import pandas as pd

from apex_fpl.models.minutes import expected_minutes, minutes_profile


def test_injury_reduces_expected_minutes():
    df = pd.DataFrame([
        {"minutes": 900, "starts": 10, "status": "a", "starts_per_90": 1.0},
        {"minutes": 900, "starts": 10, "status": "i", "starts_per_90": 1.0},
    ])
    m = expected_minutes(df)
    assert m.iloc[0] > 80
    assert m.iloc[1] < 10


def test_prior_season_playing_time_produces_player_specific_preseason_prior():
    df = pd.DataFrame(
        [
            {
                "minutes": 0,
                "starts": 0,
                "previous_minutes": 2850,
                "previous_starts": 33,
                "previous_minutes_per_match": 2850 / 38,
                "previous_start_probability": 33 / 38,
                "status": "a",
            },
            {
                "minutes": 0,
                "starts": 0,
                "previous_minutes": 500,
                "previous_starts": 4,
                "previous_minutes_per_match": 500 / 38,
                "previous_start_probability": 4 / 38,
                "status": "a",
            },
        ]
    )
    out = minutes_profile(df)
    assert out.loc[0, "start_probability"] > 0.80
    assert out.loc[0, "expected_minutes"] > 65
    assert out.loc[1, "start_probability"] < 0.20
    assert out.loc[0, "minutes_confidence"] > out.loc[1, "minutes_confidence"]


def test_current_matches_gradually_override_prior_season():
    base = {
        "previous_minutes": 2850,
        "previous_starts": 33,
        "previous_minutes_per_match": 2850 / 38,
        "previous_start_probability": 33 / 38,
        "status": "a",
    }
    df = pd.DataFrame(
        [
            {**base, "minutes": 0, "starts": 0, "current_team_matches": 0},
            {**base, "minutes": 90, "starts": 1, "current_team_matches": 6},
        ]
    )
    out = minutes_profile(df)
    assert out.loc[1, "start_probability"] < out.loc[0, "start_probability"]
