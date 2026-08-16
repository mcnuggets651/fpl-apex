import pandas as pd
import pytest

from apex_fpl.services.enrichment import (
    LOW_SAMPLE_ATTACK_MINUTES,
    coalesce_context,
    stabilise_low_sample_attack_context,
)


def _base_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": range(1, 9),
            "position": ["MID"] * 8,
            "minutes": [0.0] * 8,
            "previous_minutes": [900.0, 1200.0, 1500.0, 1800.0, 2400.0, 21.0, 21.0, 0.0],
            "expected_goals_per_90": [0.10, 0.20, 0.30, 0.40, 0.50, 1.59, 0.25, 1.40],
            "expected_assists_per_90": [0.10, 0.15, 0.20, 0.25, 0.30, 0.90, 0.18, 0.80],
        }
    )


def test_extreme_tiny_sample_rate_is_shrunk_toward_mature_position_prior():
    frame = _base_frame()
    out = stabilise_low_sample_attack_context(frame)
    target = out.loc[out.player_id == 6].iloc[0]

    mature = frame.iloc[:5]
    prior = (
        mature["expected_goals_per_90"] * mature["previous_minutes"]
    ).sum() / mature["previous_minutes"].sum()
    reliability = 21.0 / LOW_SAMPLE_ATTACK_MINUTES
    expected = prior + reliability * (1.59 - prior)

    assert bool(target["xg90_low_sample_adjusted"]) is True
    assert target["xg90_context_reliability"] == pytest.approx(reliability)
    assert target["expected_goals_per_90"] == pytest.approx(expected)
    assert target["expected_goals_per_90"] < 0.45


def test_mature_ordinary_and_no_prior_rows_are_exact_noops():
    frame = _base_frame()
    out = stabilise_low_sample_attack_context(frame)

    mature = out.loc[out.player_id == 5].iloc[0]
    ordinary_tiny = out.loc[out.player_id == 7].iloc[0]
    no_prior_sample = out.loc[out.player_id == 8].iloc[0]

    assert mature["expected_goals_per_90"] == pytest.approx(0.50)
    assert bool(mature["xg90_low_sample_adjusted"]) is False
    assert ordinary_tiny["expected_goals_per_90"] == pytest.approx(0.25)
    assert bool(ordinary_tiny["xg90_low_sample_adjusted"]) is False
    assert no_prior_sample["expected_goals_per_90"] == pytest.approx(1.40)
    assert bool(no_prior_sample["xg90_low_sample_adjusted"]) is False


def test_coalesce_applies_same_rule_to_core_context_and_xa():
    frame = _base_frame().copy()
    frame["expected_goals_per_90_core"] = frame["expected_goals_per_90"]
    frame["expected_assists_per_90_core"] = frame["expected_assists_per_90"]
    frame["expected_goals_per_90"] = 0.0
    frame["expected_assists_per_90"] = 0.0

    out = coalesce_context(frame)
    target = out.loc[out.player_id == 6].iloc[0]

    assert bool(target["xg90_low_sample_adjusted"]) is True
    assert bool(target["xa90_low_sample_adjusted"]) is True
    assert target["expected_goals_per_90"] < 0.45
    assert target["expected_assists_per_90"] < 0.35


def test_core_minutes_fallback_cannot_bypass_pre_gw1_reliability_gate():
    """Regression for the production integration defect exposed by Nyoni.

    Official FPL has zero current-season minutes before GW1, while Core can supply
    non-zero historical context in its generic minutes column.  Coalescing that
    context must not make the attacking-rate gate believe the new season has begun.
    """
    frame = _base_frame().copy()
    frame["expected_goals_per_90_core"] = frame["expected_goals_per_90"]
    frame["expected_assists_per_90_core"] = frame["expected_assists_per_90"]
    frame["minutes_core"] = frame["previous_minutes"]
    frame["expected_goals_per_90"] = 0.0
    frame["expected_assists_per_90"] = 0.0
    frame["minutes"] = 0.0

    out = coalesce_context(frame)
    target = out.loc[out.player_id == 6].iloc[0]

    assert target["minutes"] == pytest.approx(21.0)
    assert bool(target["xg90_low_sample_adjusted"]) is True
    assert target["expected_goals_per_90"] < 0.45
    assert "_official_current_minutes_for_attack_reliability" not in out.columns


def test_mature_rate_remains_exact_when_core_minutes_are_coalesced():
    frame = _base_frame().copy()
    frame["expected_goals_per_90_core"] = frame["expected_goals_per_90"]
    frame["expected_assists_per_90_core"] = frame["expected_assists_per_90"]
    frame["minutes_core"] = frame["previous_minutes"]
    frame["expected_goals_per_90"] = 0.0
    frame["expected_assists_per_90"] = 0.0
    frame["minutes"] = 0.0

    out = coalesce_context(frame)
    mature = out.loc[out.player_id == 5].iloc[0]

    assert mature["expected_goals_per_90"] == pytest.approx(0.50)
    assert bool(mature["xg90_low_sample_adjusted"]) is False
