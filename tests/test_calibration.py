from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apex_fpl.models.backtest import calibrate_ensemble_weights


def test_calibration_learns_more_weight_for_better_expert():
    rng = np.random.default_rng(7)
    actual = rng.normal(5.0, 2.0, 250)
    good = actual + rng.normal(0, 0.5, 250)
    weak = actual + rng.normal(0, 2.5, 250)
    df = pd.DataFrame({"good": good, "weak": weak, "event_points": actual})
    result = calibrate_ensemble_weights(
        df,
        ["good", "weak"],
        min_rows=100,
        ridge=0.002,
    )
    assert result.weights["good"] > result.weights["weak"]
    assert sum(result.weights.values()) == pytest.approx(1.0)
    assert result.rmse < result.equal_weight_rmse


def test_calibration_refuses_tiny_sample():
    df = pd.DataFrame(
        {
            "a": [1.0, 2.0],
            "b": [1.5, 1.5],
            "event_points": [1.0, 3.0],
        }
    )
    with pytest.raises(ValueError, match="not enough complete calibration rows"):
        calibrate_ensemble_weights(df, ["a", "b"], min_rows=10)
