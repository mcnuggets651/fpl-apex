from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.evaluation.historical_minutes_preseason import (
    aggregate_outcomes,
    aggregate_preseason_role,
    aggregate_prior_role,
)
from apex_fpl.services.enrichment import add_preseason_features


def test_live_preseason_unused_roster_rows_are_not_role_or_return_evidence():
    players = pd.DataFrame({"player_id": [1, 2]})
    friendlies = pd.DataFrame(
        [
            {
                "player_id": 1,
                "match_id": "starter",
                "minutes_played": 75.0,
                "start_min": 0,
                "goals": 1.0,
                "total_shots": 3.0,
                "xg": 0.5,
            },
            {
                "player_id": 1,
                "match_id": "sub",
                "minutes_played": 20.0,
                "start_min": 70,
                "goals": 0.0,
                "total_shots": 1.0,
                "xg": 0.1,
            },
            {
                "player_id": 1,
                "match_id": "unused",
                "minutes_played": np.nan,
                "start_min": 0,
                "goals": 0.0,
                "total_shots": 0.0,
                "xg": 0.0,
            },
            {
                "player_id": 2,
                "match_id": "unused-only",
                "minutes_played": 0.0,
                "start_min": 0,
                "goals": 0.0,
                "total_shots": 0.0,
                "xg": 0.0,
            },
        ]
    )

    out = add_preseason_features(players, friendlies).set_index("player_id")

    assert out.loc[1, "preseason_minutes"] == 95
    assert out.loc[1, "preseason_appearances"] == 2
    assert out.loc[1, "preseason_starts"] == 1
    assert bool(out.loc[1, "preseason_goals_observed"])
    assert out.loc[2, "preseason_minutes"] == 0
    assert out.loc[2, "preseason_appearances"] == 0
    assert out.loc[2, "preseason_starts"] == 0
    assert pd.isna(out.loc[2, "preseason_xg90"])
    assert not bool(out.loc[2, "preseason_xg_observed"])
    assert not bool(out.loc[2, "preseason_goals_observed"])


def test_historical_preseason_role_ignores_zero_minute_start_sentinel():
    players = pd.DataFrame([{"player_id": 1, "team_code": 10}])
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
            {"player_id": 1, "match_id": "c", "minutes_played": 0, "start_min": 0},
        ]
    )

    out = aggregate_preseason_role(players, matches, stats).set_index("player_id")

    assert out.loc[1, "preseason_team_friendlies"] == 4
    assert out.loc[1, "preseason_appearances"] == 2
    assert out.loc[1, "preseason_starts"] == 1
    assert out.loc[1, "preseason_start_probability_team"] == 0.25
    assert np.isclose(out.loc[1, "preseason_bench_appearance_probability"], 1 / 3)
    assert out.loc[1, "preseason_minutes_if_start"] == 75
    assert out.loc[1, "preseason_minutes_if_sub"] == 20


def test_historical_prior_role_ignores_unused_roster_rows():
    current = pd.DataFrame([{"player_code": 1001, "player_id": 51}])
    prior = pd.DataFrame([{"player_code": 1001, "player_id": 1}])
    rows = pd.DataFrame(
        [
            {"player_id": 1, "match_id": "g1", "minutes_played": 80, "start_min": 0},
            {"player_id": 1, "match_id": "g2", "minutes_played": 15, "start_min": 75},
            {"player_id": 1, "match_id": "g3", "minutes_played": 0, "start_min": 0},
        ]
    )

    out = aggregate_prior_role(current, prior, rows, prior_team_matches=4).set_index(
        "player_id"
    )

    assert out.loc[51, "prior_appearances"] == 2
    assert out.loc[51, "prior_starts"] == 1
    assert out.loc[51, "prior_start_probability"] == 0.25
    assert np.isclose(out.loc[51, "prior_bench_appearance_probability"], 1 / 3)
    assert out.loc[51, "prior_minutes_if_start"] == 80
    assert out.loc[51, "prior_minutes_if_sub"] == 15


def test_historical_outcomes_treat_zero_minute_rows_as_absences():
    players = pd.DataFrame([{"player_id": 1}, {"player_id": 2}])
    actual = pd.DataFrame(
        [
            {"player_id": 1, "gw": 1, "minutes_played": 90, "start_min": 0},
            {"player_id": 1, "gw": 2, "minutes_played": 0, "start_min": 0},
            {"player_id": 2, "gw": 1, "minutes_played": 20, "start_min": 70},
        ]
    )

    outcomes = aggregate_outcomes(players, actual, (1, 2)).set_index(["player_id", "gw"])

    assert outcomes.loc[(1, 1), "actual_start"] == 1
    assert outcomes.loc[(1, 1), "actual_appearance"] == 1
    assert outcomes.loc[(1, 2), "actual_minutes"] == 0
    assert outcomes.loc[(1, 2), "actual_start"] == 0
    assert outcomes.loc[(1, 2), "actual_appearance"] == 0
    assert outcomes.loc[(1, 2), "actual_bench_appearance"] == 0
    assert outcomes.loc[(2, 1), "actual_start"] == 0
    assert outcomes.loc[(2, 1), "actual_appearance"] == 1
    assert outcomes.loc[(2, 1), "actual_bench_appearance"] == 1
