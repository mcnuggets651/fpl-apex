import pandas as pd
import pytest

from apex_fpl.models.minutes import minutes_profile
from apex_fpl.models.projection import _blend_rate, _preseason_rate_weight
from apex_fpl.services.enrichment import add_preseason_features


def test_single_advanced_stat_friendly_cannot_take_quarter_of_attacking_prior():
    minutes = pd.Series([71.0])
    starts = pd.Series([1.0])
    appearances = pd.Series([1.0])

    weight = _preseason_rate_weight(minutes, starts, appearances).iloc[0]
    blended = _blend_rate(
        pd.Series([0.40]),
        pd.Series([1.40]),
        minutes,
        starts,
        appearances,
    ).iloc[0]

    assert 0.0 < weight < 0.15
    assert blended == pytest.approx(0.40 * (1 - weight) + 1.40 * weight)
    assert blended < 0.55


def test_repeated_preseason_starts_can_still_build_material_rate_weight():
    single = _preseason_rate_weight(
        pd.Series([71.0]),
        pd.Series([1.0]),
        pd.Series([1.0]),
    ).iloc[0]
    repeated = _preseason_rate_weight(
        pd.Series([270.0]),
        pd.Series([3.0]),
        pd.Series([3.0]),
    ).iloc[0]

    assert repeated > 0.25
    assert repeated > 2 * single
    assert repeated <= 0.35


def test_ambiguous_preseason_downside_cannot_erase_established_starting_role():
    df = pd.DataFrame(
        [
            {
                "minutes": 2421,
                "starts": 30,
                "starts_per_90": 1.0,
                "previous_starts": 30,
                "previous_minutes_per_match": 80.7,
                "previous_start_probability": 0.92,
                "preseason_minutes": 146,
                "preseason_starts": 1,
                "preseason_appearances": 3,
                "status": "a",
            }
        ]
    )

    out = minutes_profile(df).iloc[0]

    assert bool(out["preseason_downside_protection_applied"]) is True
    assert out["preseason_role_weight_raw"] > 0.30
    assert out["preseason_downside_reliability"] < 0.06
    assert out["preseason_role_weight"] < 0.03
    assert out["start_probability"] > 0.90
    assert out["expected_minutes"] > 77.0


def test_rotation_prior_keeps_incumbent_preseason_weighting():
    df = pd.DataFrame(
        [
            {
                "minutes": 0,
                "starts": 0,
                "starts_per_90": 0.0,
                "previous_starts": 15,
                "previous_minutes_per_match": 42.0,
                "previous_start_probability": 0.50,
                "preseason_minutes": 146,
                "preseason_starts": 1,
                "preseason_appearances": 3,
                "status": "a",
            }
        ]
    )

    out = minutes_profile(df).iloc[0]

    assert bool(out["preseason_downside_protection_applied"]) is False
    assert out["preseason_downside_reliability"] == pytest.approx(1.0)
    assert out["preseason_role_weight"] == pytest.approx(
        out["preseason_role_weight_raw"]
    )


def test_cameo_only_established_player_keeps_incumbent_preseason_weighting():
    df = pd.DataFrame(
        [
            {
                "minutes": 0,
                "starts": 0,
                "starts_per_90": 0.0,
                "previous_starts": 30,
                "previous_minutes_per_match": 75.0,
                "previous_start_probability": 0.82,
                "preseason_minutes": 25,
                "preseason_starts": 0,
                "preseason_appearances": 1,
                "status": "a",
            }
        ]
    )

    out = minutes_profile(df).iloc[0]

    assert bool(out["preseason_downside_protection_applied"]) is False
    assert out["preseason_downside_reliability"] == pytest.approx(1.0)
    assert out["preseason_role_weight"] == pytest.approx(
        out["preseason_role_weight_raw"]
    )
    assert out["preseason_role_weight"] <= 0.12


def test_final_rehearsal_outweighs_early_tour_start_for_role_evidence():
    players = pd.DataFrame([{"player_id": 1}])
    friendlies = pd.DataFrame(
        [
            {
                "player_id": 1,
                "match_id": "friendly-club-a-2026-07-10",
                "minutes_played": 90.0,
                "start_min": 0,
            },
            {
                "player_id": 1,
                "match_id": "friendly-club-b-2026-08-15",
                "minutes_played": 20.0,
                "start_min": 70,
            },
        ]
    )

    enriched = add_preseason_features(players, friendlies).iloc[0]

    assert enriched["preseason_starts"] == 1
    assert enriched["preseason_appearances"] == 2
    assert enriched["preseason_recent_start_probability"] < 0.15
    assert enriched["preseason_recent_average_minutes"] < 30.0


def test_transferred_goalkeeper_cannot_inherit_old_club_incumbency_without_current_evidence():
    df = pd.DataFrame(
        [
            {
                "position": "GK",
                "minutes": 0,
                "starts": 0,
                "starts_per_90": 0.0,
                "previous_starts": 36,
                "previous_minutes_per_match": 85.0,
                "previous_start_probability": 0.95,
                "preseason_minutes": 0,
                "preseason_starts": 0,
                "preseason_appearances": 0,
                "club_changed": True,
                "status": "a",
            }
        ]
    )

    out = minutes_profile(df).iloc[0]

    assert bool(out["club_changed"]) is True
    assert out["transfer_role_retention"] == pytest.approx(0.20)
    assert out["historical_start_probability"] < 0.45
    assert out["start_probability"] < 0.45
    assert out["expected_minutes"] < 40.0


def test_current_verified_override_can_establish_transferred_goalkeeper_role():
    df = pd.DataFrame(
        [
            {
                "position": "GK",
                "minutes": 0,
                "starts": 0,
                "starts_per_90": 0.0,
                "previous_starts": 36,
                "previous_minutes_per_match": 85.0,
                "previous_start_probability": 0.95,
                "preseason_minutes": 0,
                "preseason_starts": 0,
                "preseason_appearances": 0,
                "club_changed": True,
                "expected_minutes_override": 82.0,
                "start_probability_override": 0.93,
                "status": "a",
            }
        ]
    )

    out = minutes_profile(df).iloc[0]

    assert out["start_probability"] == pytest.approx(0.93)
    assert out["expected_minutes"] == pytest.approx(82.0)
