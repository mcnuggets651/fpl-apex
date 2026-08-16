import pandas as pd
import pytest

from apex_fpl.models.minutes import minutes_profile
from apex_fpl.models.projection import _blend_rate, _preseason_rate_weight


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

    assert out["preseason_role_weight_raw"] > 0.30
    assert out["preseason_downside_reliability"] < 0.06
    assert out["preseason_role_weight"] < 0.03
    assert out["start_probability"] > 0.90
    assert out["expected_minutes"] > 77.0
