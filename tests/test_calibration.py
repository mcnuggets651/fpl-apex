from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from apex_fpl.models.backtest import (
    calibrate_ensemble_weights,
    gameweek_block_bootstrap,
    interval_diagnostics,
)


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


def test_gameweek_bootstrap_preserves_blocks_and_detects_better_candidate():
    rows = []
    for gw in range(1, 7):
        for actual in [0.0, 2.0, 5.0, 9.0]:
            rows.append(
                {"gw": gw, "event_points": actual, "candidate": actual + 0.1,
                 "baseline": actual + 2.0}
            )
    result = gameweek_block_bootstrap(
        pd.DataFrame(rows), candidate_col="candidate", baseline_col="baseline", samples=200
    )
    assert result.blocks == 6
    assert result.mean_difference < 0
    assert result.probability_improves == 1.0
    assert result.upper_95 < 0


def test_interval_diagnostics_scores_declared_scale():
    frame = pd.DataFrame(
        {"xp": [2.0, 2.0, 2.0, 2.0], "projection_sd": [1.0] * 4,
         "event_points": [2.0, 2.5, 3.0, 5.0]}
    )
    result = interval_diagnostics(frame)
    assert result["rows"] == 4
    assert result["coverage_50"] == 0.5
    assert result["coverage_95"] == 0.75
