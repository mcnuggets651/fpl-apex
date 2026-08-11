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


def test_repeated_preseason_starts_supersede_stale_squad_role():
    df = pd.DataFrame(
        [
            {
                "minutes": 0,
                "starts": 0,
                "previous_minutes": 300,
                "previous_starts": 2,
                "previous_minutes_per_match": 300 / 38,
                "previous_start_probability": 2 / 38,
                "preseason_minutes": 315,
                "preseason_starts": 4,
                "preseason_appearances": 4,
                "status": "a",
            },
            {
                "minutes": 0,
                "starts": 0,
                "previous_minutes": 300,
                "previous_starts": 2,
                "previous_minutes_per_match": 300 / 38,
                "previous_start_probability": 2 / 38,
                "preseason_minutes": 20,
                "preseason_starts": 0,
                "preseason_appearances": 1,
                "status": "a",
            },
        ]
    )
    out = minutes_profile(df)
    assert out.loc[0, "start_probability"] > 0.80
    assert out.loc[0, "expected_minutes"] > 65
    assert out.loc[0, "expected_minutes"] > out.loc[1, "expected_minutes"]


def test_verified_lineup_override_replaces_role_prior_but_not_injury_status():
    base = {
        "minutes": 0,
        "starts": 0,
        "previous_minutes": 300,
        "previous_starts": 2,
        "previous_minutes_per_match": 300 / 38,
        "previous_start_probability": 2 / 38,
        "expected_minutes_override": 78,
        "start_probability_override": 0.88,
        "appearance_probability_override": 0.96,
        "minutes_evidence_confidence": 0.90,
    }
    df = pd.DataFrame(
        [
            {**base, "status": "a"},
            {**base, "status": "i"},
        ]
    )
    out = minutes_profile(df)
    assert out.loc[0, "expected_minutes"] == 78
    assert out.loc[0, "start_probability"] == 0.88
    assert out.loc[0, "appearance_probability"] == 0.96
    assert out.loc[0, "minutes_confidence"] >= 0.90
    assert out.loc[1, "expected_minutes"] < 5
    assert out.loc[1, "start_probability"] < 0.05
