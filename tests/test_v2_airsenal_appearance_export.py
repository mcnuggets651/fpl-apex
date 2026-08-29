from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apex_export_airsenal",
    ROOT / "scripts" / "export_airsenal.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_minute_marginals_match_airsenal_model_sample() -> None:
    expected_minutes, p_appearance, p_60 = MODULE.minute_marginals([90, 70, 0, 20])
    assert expected_minutes == pytest.approx(45.0)
    assert p_appearance == pytest.approx(0.75)
    assert p_60 == pytest.approx(0.50)


def test_minute_marginals_preserve_single_previous_season_average() -> None:
    expected_minutes, p_appearance, p_60 = MODULE.minute_marginals([67.5])
    assert expected_minutes == pytest.approx(67.5)
    assert p_appearance == pytest.approx(1.0)
    assert p_60 == pytest.approx(1.0)


def test_minute_marginals_zero_history_is_explicit_no_show() -> None:
    assert MODULE.minute_marginals([0.0]) == (0.0, 0.0, 0.0)


@pytest.mark.parametrize(
    "sample",
    [[], [-1.0], [90.1], [float("nan")], [float("inf")]],
)
def test_minute_marginals_reject_invalid_model_samples(sample) -> None:
    with pytest.raises(ValueError):
        MODULE.minute_marginals(sample)


def test_optional_csv_value_leaves_unmodelled_probability_blank() -> None:
    assert MODULE._csv_optional(None) == ""
    assert MODULE._csv_optional(0.75) == pytest.approx(0.75)
