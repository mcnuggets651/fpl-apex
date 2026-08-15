import numpy as np
import pandas as pd

from apex_fpl.evaluation.historical_minutes_preseason import (
    aggregate_outcomes,
    aggregate_preseason_role,
    aggregate_prior_role,
    decomposed_minutes_challenger,
    score_minutes_models,
)


def test_preseason_start_rate_uses_team_friendlies_not_only_appearances():
    players = pd.DataFrame(
        [
            {"player_id": 1, "team_code": 10},
            {"player_id": 2, "team_code": 10},
        ]
    )
    matches = pd.DataFrame(
        [
            {"match_id": "a", "home_team": 10, "away_team": 90},
            {"match_id": "b", "home_team": 10, "away_team": 91},
            {"match_id": "c", "home_team": 10, "away_team": 92},
            {"match_id": "d", "home_team": 10, "away_team": 93},
        ]
    )
    stats = pd.DataFrame(
        [
            {"player_id": 1, "match_id": "a", "minutes_played": 75, "start_min": 0},
            {"player_id": 1, "match_id": "b", "minutes_played": 20, "start_min": 70},
            {"player_id": 2, "match_id": "a", "minutes_played": 45, "start_min": 0},
            {"player_id": 2, "match_id": "b", "minutes_played": 45, "start_min": 0},
        ]
    )

    out = aggregate_preseason_role(players, matches, stats).set_index("player_id")

    assert out.loc[1, "preseason_team_friendlies"] == 4
    assert out.loc[1, "preseason_starts"] == 1
    assert out.loc[1, "preseason_start_probability_team"] == 0.25
    assert np.isclose(out.loc[1, "preseason_bench_appearance_probability"], 1 / 3)
    assert out.loc[2, "preseason_start_probability_team"] == 0.5


def test_prior_role_maps_stable_player_code_and_estimates_bench_propensity():
    current = pd.DataFrame(
        [
            {"player_code": 1001, "player_id": 51},
            {"player_code": 1002, "player_id": 52},
        ]
    )
    prior = pd.DataFrame(
        [
            {"player_code": 1001, "player_id": 1},
            {"player_code": 1002, "player_id": 2},
        ]
    )
    rows = pd.DataFrame(
        [
            {"player_id": 1, "match_id": "g1", "minutes_played": 80, "start_min": 0},
            {"player_id": 1, "match_id": "g2", "minutes_played": 70, "start_min": 0},
            {"player_id": 1, "match_id": "g3", "minutes_played": 15, "start_min": 75},
            {"player_id": 2, "match_id": "g1", "minutes_played": 10, "start_min": 80},
        ]
    )

    out = aggregate_prior_role(current, prior, rows, prior_team_matches=4).set_index(
        "player_id"
    )

    assert out.loc[51, "prior_starts"] == 2
    assert out.loc[51, "prior_appearances"] == 3
    assert out.loc[51, "prior_start_probability"] == 0.5
    assert out.loc[51, "prior_bench_appearance_probability"] == 0.5
    assert out.loc[51, "prior_minutes_if_start"] == 75
    assert out.loc[51, "prior_minutes_if_sub"] == 15
    assert out.loc[52, "prior_start_probability"] == 0.0


def test_decomposed_challenger_obeys_generative_minutes_identity():
    players = pd.DataFrame([{"player_id": 1}])
    incumbent = pd.DataFrame(
        [
            {
                "preseason_role_weight": 0.4,
                "availability_probability": 1.0,
                "historical_start_probability": 0.5,
            }
        ]
    )
    prior = pd.DataFrame(
        [
            {
                "player_id": 1,
                "prior_start_probability": 0.5,
                "prior_bench_appearance_probability": 0.4,
                "prior_minutes_if_start": 75,
                "prior_minutes_if_sub": 18,
            }
        ]
    )
    preseason = pd.DataFrame(
        [
            {
                "player_id": 1,
                "preseason_start_probability_team": 0.75,
                "preseason_bench_appearance_probability": 0.5,
                "preseason_minutes_if_start": 80,
                "preseason_minutes_if_sub": 20,
            }
        ]
    )

    out = decomposed_minutes_challenger(players, incumbent, prior, preseason).iloc[0]

    expected_from_states = (
        out["challenger_role_start_probability"] * out["challenger_minutes_if_start"]
        + (1 - out["challenger_role_start_probability"])
        * out["challenger_role_bench_probability"]
        * out["challenger_minutes_if_sub"]
    )
    assert np.isclose(out["challenger_expected_minutes"], expected_from_states)
    assert out["challenger_appearance_probability"] >= out["challenger_start_probability"]


def test_outcomes_include_zero_minute_absences_and_metrics_reward_better_model():
    players = pd.DataFrame([{"player_id": 1}, {"player_id": 2}])
    actual = pd.DataFrame(
        [
            {"player_id": 1, "gw": 1, "minutes_played": 90, "start_min": 0},
            {"player_id": 2, "gw": 2, "minutes_played": 20, "start_min": 70},
        ]
    )
    outcomes = aggregate_outcomes(players, actual, (1, 2))

    assert len(outcomes) == 4
    missing = outcomes[(outcomes.player_id == 1) & (outcomes.gw == 2)].iloc[0]
    assert missing.actual_minutes == 0
    assert missing.actual_appearance == 0

    scored = outcomes.copy()
    scored["incumbent_start_probability"] = 0.5
    scored["incumbent_appearance_probability"] = 0.7
    scored["incumbent_bench_appearance_probability"] = 0.5
    scored["incumbent_expected_minutes"] = 45.0
    scored["incumbent_minutes_if_start"] = 70.0
    scored["incumbent_minutes_if_sub"] = 25.0

    scored["challenger_start_probability"] = [0.9, 0.1, 0.1, 0.1]
    scored["challenger_appearance_probability"] = [0.95, 0.1, 0.1, 0.8]
    scored["challenger_bench_appearance_probability"] = [0.2, 0.1, 0.1, 0.8]
    scored["challenger_expected_minutes"] = [82.0, 8.0, 8.0, 18.0]
    scored["challenger_minutes_if_start"] = 85.0
    scored["challenger_minutes_if_sub"] = 20.0

    metrics = score_minutes_models(scored)
    assert metrics["challenger"]["start_brier"] < metrics["incumbent"]["start_brier"]
    assert metrics["challenger"]["minutes_mae"] < metrics["incumbent"]["minutes_mae"]
