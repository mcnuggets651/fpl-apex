from __future__ import annotations

from datetime import timedelta

import pandas as pd

from apex_fpl.evaluation.team_goals import run_team_goal_walk_forward


def _matches() -> pd.DataFrame:
    rows = []
    day = pd.Timestamp("2021-08-01", tz="UTC")
    for season in range(2021, 2025):
        for index in range(40):
            arsenal_home = index % 2 == 0
            rows.append(
                {
                    "date": day,
                    "season": season,
                    "team_home": "Arsenal" if arsenal_home else "Everton",
                    "team_away": "Everton" if arsenal_home else "Arsenal",
                    "xg_home": 2.4 if arsenal_home else 0.7,
                    "xg_away": 0.6 if arsenal_home else 2.0,
                    "goals_home": 2 if arsenal_home else 0,
                    "goals_away": 0 if arsenal_home else 2,
                }
            )
            day += timedelta(days=4)
        day += timedelta(days=60)
    return pd.DataFrame(rows)


def test_team_goal_backtest_is_chronological_and_includes_simple_baseline():
    result = run_team_goal_walk_forward(_matches(), minimum_prior_seasons=2)
    assert not result.predictions.empty
    assert set(result.summary["model"]) == {"model", "baseline"}
    assert set(result.ablation["variant"]) == {
        "time_decay_shrinkage",
        "no_time_decay",
        "no_shrinkage",
    }
    summary = result.summary.groupby("model")["goal_mae"].mean()
    assert summary["model"] < summary["baseline"]


def test_future_season_changes_cannot_change_an_earlier_fold():
    base = _matches()
    first = run_team_goal_walk_forward(base, minimum_prior_seasons=2)
    changed = base.copy()
    changed.loc[changed["season"] == 2024, ["xg_home", "xg_away"]] = 20.0
    second = run_team_goal_walk_forward(changed, minimum_prior_seasons=2)
    left = first.predictions[first.predictions["test_season"] == "2023"][
        ["model_home", "model_away"]
    ].reset_index(drop=True)
    right = second.predictions[second.predictions["test_season"] == "2023"][
        ["model_home", "model_away"]
    ].reset_index(drop=True)
    pd.testing.assert_frame_equal(left, right)
