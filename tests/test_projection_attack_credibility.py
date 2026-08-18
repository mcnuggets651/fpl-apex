import pandas as pd
import pytest

from apex_fpl.models.projection import _credible_attack_rate


def _rate_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": list(range(1, 8)),
            "position": ["MID"] * 7,
            "previous_minutes": [2800.0, 2400.0, 2000.0, 1600.0, 1200.0, 21.0, 21.0],
            "minutes": [2800.0, 2400.0, 2000.0, 1600.0, 1200.0, 21.0, 21.0],
            "current_team_matches": [0.0] * 7,
        }
    )


def test_21_minute_extreme_rate_is_shrunk_before_it_becomes_xp() -> None:
    frame = _rate_frame()
    rate = pd.Series([0.12, 0.18, 0.24, 0.30, 0.42, 1.59, 0.25])
    no_evidence = pd.Series([float("nan")] * len(frame))

    adjusted, reliability, changed = _credible_attack_rate(
        frame,
        rate,
        "xg90",
        no_evidence,
        no_evidence,
    )

    target = 5
    assert bool(changed.iloc[target]) is True
    assert reliability.iloc[target] == pytest.approx(21.0 / 270.0)
    assert adjusted.iloc[target] < 0.50
    # Ordinary tiny-sample rates are not suppressed merely because the sample is small.
    assert bool(changed.iloc[6]) is False
    assert adjusted.iloc[6] == pytest.approx(0.25)


def test_independent_advanced_stat_support_can_preserve_high_rate() -> None:
    frame = _rate_frame()
    rate = pd.Series([0.12, 0.18, 0.24, 0.30, 0.42, 1.20, 0.25])
    understat = pd.Series([float("nan")] * 5 + [1.15, float("nan")])
    no_preseason = pd.Series([float("nan")] * len(frame))

    adjusted, reliability, changed = _credible_attack_rate(
        frame,
        rate,
        "xg90",
        understat,
        no_preseason,
    )

    assert bool(changed.iloc[5]) is True
    assert reliability.iloc[5] == pytest.approx(0.90)
    assert adjusted.iloc[5] > 1.0


def test_observed_preseason_rate_not_team_sheet_minutes_rebuilds_credibility() -> None:
    frame = _rate_frame()
    rate = pd.Series([0.12, 0.18, 0.24, 0.30, 0.42, 1.20, 0.25])
    no_understat = pd.Series([float("nan")] * len(frame))
    preseason = pd.Series([float("nan")] * 5 + [1.10, float("nan")])

    adjusted, reliability, changed = _credible_attack_rate(
        frame,
        rate,
        "xg90",
        no_understat,
        preseason,
    )

    assert bool(changed.iloc[5]) is True
    assert reliability.iloc[5] == pytest.approx(0.80)
    assert adjusted.iloc[5] > 0.90


def test_mature_high_rate_is_never_shrunk_by_sample_credibility_rule() -> None:
    frame = _rate_frame()
    frame.loc[5, "previous_minutes"] = 900.0
    rate = pd.Series([0.12, 0.18, 0.24, 0.30, 0.42, 0.90, 0.25])
    no_evidence = pd.Series([float("nan")] * len(frame))

    adjusted, reliability, changed = _credible_attack_rate(
        frame,
        rate,
        "xg90",
        no_evidence,
        no_evidence,
    )

    assert bool(changed.iloc[5]) is False
    assert reliability.iloc[5] == pytest.approx(1.0)
    assert adjusted.iloc[5] == pytest.approx(0.90)
