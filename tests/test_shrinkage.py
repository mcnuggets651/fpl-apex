from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.shrinkage import RateShrinkageConfig, shrink_player_rates


def _players() -> pd.DataFrame:
    rows = []
    for idx, rate in enumerate([0.24, 0.28, 0.30, 0.32, 0.34, 0.36], start=1):
        rows.append(
            {
                "player_id": idx,
                "position": "MID",
                "minutes": 0,
                "previous_minutes": 2400,
                "expected_goals_per_90": rate,
                "previous_expected_goals_per_90": rate,
                "expected_assists_per_90": 0.20,
                "previous_expected_assists_per_90": 0.20,
                "defensive_contribution_per_90": 4.0,
                "previous_defensive_contribution_per_90": 4.0,
            }
        )
    rows.extend(
        [
            {
                "player_id": 100,
                "position": "MID",
                "minutes": 0,
                "previous_minutes": 90,
                "expected_goals_per_90": 1.20,
                "previous_expected_goals_per_90": 1.20,
                "expected_assists_per_90": 0.80,
                "previous_expected_assists_per_90": 0.80,
                "defensive_contribution_per_90": 16.0,
                "previous_defensive_contribution_per_90": 16.0,
            },
            {
                "player_id": 101,
                "position": "MID",
                "minutes": 0,
                "previous_minutes": 3000,
                "expected_goals_per_90": 0.60,
                "previous_expected_goals_per_90": 0.60,
                "expected_assists_per_90": 0.35,
                "previous_expected_assists_per_90": 0.35,
                "defensive_contribution_per_90": 5.0,
                "previous_defensive_contribution_per_90": 5.0,
            },
        ]
    )
    return pd.DataFrame(rows)


def test_low_minute_outlier_is_shrunk_more_than_established_player() -> None:
    players = _players()
    cfg = RateShrinkageConfig(
        prior_minutes={"xg90": 720.0, "xa90": 720.0, "defcon90": 720.0},
        min_group_players=5,
        min_group_minutes=1000,
    )
    shrunk = shrink_player_rates(players, cfg)
    low = shrunk.loc[players["player_id"].eq(100)].iloc[0]
    established = shrunk.loc[players["player_id"].eq(101)].iloc[0]
    assert low["xg90_reliability"] < established["xg90_reliability"]
    assert abs(low["shrunk_xg90"] - low["prior_xg90"]) < abs(
        low["raw_xg90"] - low["prior_xg90"]
    )
    assert abs(established["shrunk_xg90"] - established["raw_xg90"]) < 0.15


def test_pre_gw1_uses_previous_competitive_evidence() -> None:
    players = _players()
    mask = players["player_id"].eq(100)
    players.loc[mask, "expected_goals_per_90"] = 2.5
    players.loc[mask, "previous_expected_goals_per_90"] = 0.9
    shrunk = shrink_player_rates(players)
    row = shrunk.loc[mask].iloc[0]
    assert row["xg90_evidence_source"] == "previous_season"
    assert np.isclose(row["raw_xg90"], 0.9)
    assert np.isclose(row["xg90_previous_evidence_minutes"], 90)
    assert np.isclose(row["xg90_current_evidence_minutes"], 0)
    assert np.isclose(row["xg90_combined_effective_evidence_minutes"], 90)


def test_current_minutes_are_combined_with_previous_season_not_replaced() -> None:
    players = _players()
    mask = players["player_id"].eq(101)
    players.loc[mask, "minutes"] = 450
    players.loc[mask, "expected_goals_per_90"] = 0.75
    shrunk = shrink_player_rates(players)
    row = shrunk.loc[mask].iloc[0]
    expected_rate = (3000 * 0.60 + 450 * 0.75) / 3450
    assert row["xg90_evidence_source"] == "previous_plus_current"
    assert np.isclose(row["combined_competitive_xg90"], expected_rate)
    assert np.isclose(row["raw_xg90"], expected_rate)
    assert np.isclose(row["xg90_previous_evidence_minutes"], 3000)
    assert np.isclose(row["xg90_current_evidence_minutes"], 450)
    assert np.isclose(row["xg90_combined_effective_evidence_minutes"], 3450)


def test_gw1_to_gw2_small_sample_does_not_reset_established_player() -> None:
    players = _players()
    mask = players["player_id"].eq(101)
    cfg = RateShrinkageConfig(
        prior_minutes={"xg90": 720.0, "xa90": 720.0, "defcon90": 720.0},
        min_group_players=5,
        min_group_minutes=1000,
    )
    gw1 = shrink_player_rates(players, cfg).loc[mask].iloc[0]

    players.loc[mask, "minutes"] = 34
    players.loc[mask, "expected_goals_per_90"] = 2.0
    gw2 = shrink_player_rates(players, cfg).loc[mask].iloc[0]

    expected_combined = (3000 * 0.60 + 34 * 2.0) / 3034
    assert np.isclose(gw2["combined_competitive_xg90"], expected_combined)
    assert np.isclose(gw2["xg90_combined_effective_evidence_minutes"], 3034)
    assert gw2["xg90_reliability"] > 0.75
    assert abs(gw2["shrunk_xg90"] - gw1["shrunk_xg90"]) < 0.03


def test_preseason_is_not_counted_as_competitive_shrinkage_evidence() -> None:
    players = _players()
    mask = players["player_id"].eq(100)
    baseline = shrink_player_rates(players).loc[mask].iloc[0]
    players["preseason_minutes"] = 0
    players["preseason_xg90"] = np.nan
    players.loc[mask, "preseason_minutes"] = 900
    players.loc[mask, "preseason_xg90"] = 4.0
    with_preseason = shrink_player_rates(players).loc[mask].iloc[0]
    assert np.isclose(
        with_preseason["xg90_combined_effective_evidence_minutes"],
        baseline["xg90_combined_effective_evidence_minutes"],
    )
    assert np.isclose(with_preseason["shrunk_xg90"], baseline["shrunk_xg90"])


def test_leave_one_out_prior_does_not_let_outlier_define_its_own_prior() -> None:
    players = _players()
    shrunk = shrink_player_rates(
        players,
        RateShrinkageConfig(min_group_players=5, min_group_minutes=1000),
    )
    low = shrunk.loc[players["player_id"].eq(100)].iloc[0]
    assert low["prior_xg90"] < 0.5
