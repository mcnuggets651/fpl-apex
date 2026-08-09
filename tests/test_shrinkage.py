from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.models.shrinkage import (
    RateShrinkageConfig,
    position_price_tier_groups,
    shrink_player_rates,
)


def _validation_module():
    path = Path(__file__).parents[1] / "scripts" / "validate_shrinkage_continuous.py"
    spec = importlib.util.spec_from_file_location("validate_shrinkage_continuous", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def test_position_specific_prior_minutes_change_reliability_without_changing_evidence() -> None:
    players = _players()
    defender = players.iloc[[0]].copy()
    defender["player_id"] = 999
    defender["position"] = "DEF"
    players = pd.concat([players, defender], ignore_index=True)
    cfg = RateShrinkageConfig(
        prior_minutes={
            "xg90": {"DEFAULT": 360.0, "MID": 720.0, "DEF": 180.0},
            "xa90": 360.0,
            "defcon90": 360.0,
        },
        min_group_players=99,
        min_group_minutes=1_000_000,
    )
    shrunk = shrink_player_rates(players, cfg)
    midfielder = shrunk.loc[players["player_id"].eq(1)].iloc[0]
    defender_row = shrunk.loc[players["player_id"].eq(999)].iloc[0]

    assert np.isclose(midfielder["xg90_prior_minutes"], 720.0)
    assert np.isclose(defender_row["xg90_prior_minutes"], 180.0)
    assert np.isclose(
        midfielder["xg90_combined_effective_evidence_minutes"],
        defender_row["xg90_combined_effective_evidence_minutes"],
    )
    assert defender_row["xg90_reliability"] > midfielder["xg90_reliability"]


def test_shrinkage_group_refines_prior_inside_position() -> None:
    players = _players()
    players["shrinkage_group"] = "MID|LOW"
    players.loc[players["player_id"].isin([100, 101]), "shrinkage_group"] = "MID|HIGH"
    cfg = RateShrinkageConfig(
        prior_minutes={"xg90": 720.0, "xa90": 720.0, "defcon90": 720.0},
        min_group_players=1,
        min_group_minutes=80.0,
    )
    shrunk = shrink_player_rates(players, cfg)
    low_sample_high_tier = shrunk.loc[players["player_id"].eq(100)].iloc[0]
    low_tier = shrunk.loc[players["player_id"].eq(1)].iloc[0]

    assert low_sample_high_tier["prior_xg90"] > low_tier["prior_xg90"]
    assert np.isclose(low_sample_high_tier["prior_xg90"], 0.60)


def test_sparse_tier_falls_back_to_position_and_excludes_target() -> None:
    players = _players().iloc[:6].copy()
    players["shrinkage_group"] = "MID|LOW"
    players.loc[players.index[0], "shrinkage_group"] = "MID|HIGH"
    cfg = RateShrinkageConfig(
        prior_minutes={"xg90": 720.0, "xa90": 720.0, "defcon90": 720.0},
        min_group_players=5,
        min_group_minutes=1000,
    )
    shrunk = shrink_player_rates(players, cfg)
    target = shrunk.iloc[0]
    expected = np.average(
        players.iloc[1:]["previous_expected_goals_per_90"],
        weights=players.iloc[1:]["previous_minutes"],
    )
    assert target["prior_xg90_level"] == "position"
    assert np.isclose(target["prior_xg90"], expected)


def test_league_fallback_is_leave_one_out() -> None:
    players = _players().iloc[[0]].copy()
    defenders = _players().iloc[1:7].copy()
    defenders["position"] = "DEF"
    defenders["shrinkage_group"] = "DEF|LOW"
    players["shrinkage_group"] = "MID|HIGH"
    combined = pd.concat([players, defenders], ignore_index=True)
    cfg = RateShrinkageConfig(
        prior_minutes={"xg90": 720.0, "xa90": 720.0, "defcon90": 720.0},
        min_group_players=5,
        min_group_minutes=1000,
    )
    shrunk = shrink_player_rates(combined, cfg)
    target = shrunk.iloc[0]
    expected = np.average(
        combined.iloc[1:]["previous_expected_goals_per_90"],
        weights=combined.iloc[1:]["previous_minutes"],
    )
    assert target["prior_xg90_level"] == "league"
    assert np.isclose(target["prior_xg90"], expected)


def test_validator_freezes_prediction_on_full_roster_before_future_filter() -> None:
    validator = _validation_module()
    rates = [1.5, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    cohort = pd.DataFrame(
        {
            "player_id": range(1, 8),
            "player_code": range(101, 108),
            "position": "MID",
            "minutes_before": 0.0,
            "previous_minutes": 1000.0,
            "rate_before": np.nan,
            "previous_expected_goals_per_90": rates,
            "cutoff_gw": 100,
            "cluster_id": [f"2024-25:{code}" for code in range(101, 108)],
            "score_eligible": [True, False, False, False, False, False, False],
            "actual_future_rate": [0.4] + [np.nan] * 6,
            "validation_stratum": "pre_gw1",
        }
    )
    scored = validator._predict(cohort, "xg90", 720.0)
    assert len(scored) == 1
    assert scored.iloc[0]["prediction_cohort_size"] == 7
    assert np.isclose(scored.iloc[0]["prior_prediction"], np.mean(rates[1:]))


def test_pre_gw1_examples_zero_current_outcomes_and_keep_full_roster() -> None:
    validator = _validation_module()
    rows = []
    for player_id, future_minutes in ((1, 180), (2, 0)):
        cumulative_minutes = 0
        cumulative_xg = 0.0
        for gw in (1, 2):
            event_minutes = future_minutes / 2
            cumulative_minutes += event_minutes
            cumulative_xg += 0.2 if event_minutes else 0.0
            rows.append(
                {
                    "player_id": player_id,
                    "player_code": 100 + player_id,
                    "position": "MID",
                    "gw": gw,
                    "minutes": cumulative_minutes,
                    "price_value": 60,
                    "expected_goals_per_90": (
                        cumulative_xg * 90 / cumulative_minutes
                        if cumulative_minutes
                        else np.nan
                    ),
                    "previous_minutes": 1000.0,
                    "previous_expected_goals_per_90": 0.3,
                }
            )
    examples = validator._examples(pd.DataFrame(rows), "xg90", window_gws=2)
    opening = examples[examples["cutoff_gw"].eq(0)].sort_values("player_id")
    assert len(opening) == 2
    assert opening["minutes_before"].eq(0).all()
    assert opening["rate_before"].isna().all()
    assert opening["score_eligible"].tolist() == [True, False]


def test_live_price_group_helper_is_shared_and_deterministic() -> None:
    players = pd.DataFrame(
        {
            "position": ["MID"] * 6,
            "price_value": [45, 50, 55, 60, 65, 70],
        }
    )
    groups = position_price_tier_groups(players, price_column="price_value")
    assert groups.tolist() == [
        "MID|LOW",
        "MID|LOW",
        "MID|MID",
        "MID|MID",
        "MID|HIGH",
        "MID|HIGH",
    ]


def test_default_candidate_uses_corrected_attack_k_and_leaves_defcon_raw() -> None:
    players = _players()
    shrunk = shrink_player_rates(players)
    assert shrunk["xg90_prior_minutes"].eq(180.0).all()
    assert shrunk["xa90_prior_minutes"].eq(360.0).all()
    assert shrunk["defcon90_prior_minutes"].eq(0.0).all()
    assert np.allclose(shrunk["shrunk_defcon90"], shrunk["raw_defcon90"])
