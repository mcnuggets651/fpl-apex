from __future__ import annotations

from datetime import timedelta

import pandas as pd

from apex_fpl.models.team_goals import build_team_goal_surface, build_team_ratings


def _history() -> pd.DataFrame:
    rows = []
    for index in range(30):
        strong_home = index % 2 == 0
        rows.append(
            {
                "date": pd.Timestamp("2025-01-01", tz="UTC")
                + timedelta(days=index * 4),
                "team_home": "Arsenal" if strong_home else "Everton",
                "team_away": "Everton" if strong_home else "Arsenal",
                "xg_home": 2.2 if strong_home else 0.8,
                "xg_away": 0.7 if strong_home else 1.8,
                "goals_home": 2 if strong_home else 1,
                "goals_away": 0 if strong_home else 2,
            }
        )
    return pd.DataFrame(rows)


def _teams() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"id": 1, "name": "Arsenal"},
            {"id": 2, "name": "Everton"},
            {"id": 3, "name": "Promoted FC"},
        ]
    )


def test_team_goal_ratings_shrink_history_and_give_promoted_team_safe_prior():
    ratings = build_team_ratings(
        _history(),
        _teams(),
        as_of=pd.Timestamp("2026-01-01", tz="UTC"),
    )
    arsenal = ratings[ratings.team == 1].iloc[0]
    promoted = ratings[ratings.team == 3].iloc[0]
    assert arsenal["attack_home"] > 1.0
    assert arsenal["defence_home"] < 1.0
    assert promoted["prior_type"] == "promoted_league_average"
    assert promoted["attack_home"] == 1.0
    assert promoted["evidence_confidence"] == 0.0


def test_team_goal_surface_covers_every_official_fixture_side():
    ratings = build_team_ratings(
        _history(),
        _teams(),
        as_of=pd.Timestamp("2026-01-01", tz="UTC"),
    )
    fixtures = pd.DataFrame(
        [
            {"event": 1, "team_h": 1, "team_a": 2},
            {"event": 1, "team_h": 3, "team_a": 1},
        ]
    )
    surface = build_team_goal_surface(fixtures, ratings, [1])
    assert len(surface) == 4
    assert surface[["expected_team_goals", "clean_sheet_prob"]].notna().all().all()
    arsenal_home = surface[(surface.team == 1) & (surface.is_home)].iloc[0]
    everton_away = surface[(surface.team == 2) & (~surface.is_home)].iloc[0]
    assert arsenal_home["expected_team_goals"] > everton_away["expected_team_goals"]
