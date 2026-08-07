from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import minimize


@dataclass
class BacktestMetrics:
    mae: float
    rmse: float
    bias: float
    rank_correlation: float


@dataclass
class WeightCalibration:
    weights: dict[str, float]
    rows: int
    rmse: float
    equal_weight_rmse: float
    improvement: float


def score_predictions(
    df: pd.DataFrame,
    prediction_col: str = "xp",
    actual_col: str = "event_points",
) -> BacktestMetrics:
    d = df[[prediction_col, actual_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if d.empty:
        return BacktestMetrics(float("nan"), float("nan"), float("nan"), float("nan"))
    err = d[prediction_col] - d[actual_col]
    return BacktestMetrics(
        mae=float(np.mean(np.abs(err))),
        rmse=float(np.sqrt(np.mean(err**2))),
        bias=float(np.mean(err)),
        rank_correlation=float(d[prediction_col].rank().corr(d[actual_col].rank())),
    )


def calibrate_ensemble_weights(
    df: pd.DataFrame,
    expert_columns: list[str],
    actual_col: str = "event_points",
    *,
    min_rows: int = 50,
    ridge: float = 0.015,
) -> WeightCalibration:
    """Fit non-negative, sum-to-one expert weights on historical deadline data.

    This should only be run on walk-forward rows containing information that was
    genuinely available before each historical FPL deadline. It is not safe to
    calibrate against hindsight features or post-match scraped expected points.

    A small ridge penalty towards equal weights reduces overfitting when one
    expert happens to dominate a short sample.
    """
    if not expert_columns:
        raise ValueError("at least one expert column is required")
    required = [*expert_columns, actual_col]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"calibration file missing columns: {missing}")

    data = df[required].apply(pd.to_numeric, errors="coerce").dropna()
    if len(data) < min_rows:
        raise ValueError(
            f"not enough complete calibration rows: {len(data)} < required {min_rows}"
        )

    x = data[expert_columns].to_numpy(float)
    y = data[actual_col].to_numpy(float)
    n = len(expert_columns)
    equal = np.full(n, 1.0 / n)

    def objective(weights: np.ndarray) -> float:
        residual = x @ weights - y
        mse = float(np.mean(residual**2))
        regularisation = ridge * float(np.sum((weights - equal) ** 2))
        return mse + regularisation

    result = minimize(
        objective,
        x0=equal,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n,
        constraints=[{"type": "eq", "fun": lambda w: float(np.sum(w) - 1.0)}],
        options={"maxiter": 1000, "ftol": 1e-10},
    )
    if not result.success:
        raise RuntimeError(f"ensemble weight calibration failed: {result.message}")

    weights = np.clip(result.x, 0, 1)
    weights = weights / weights.sum()
    calibrated_rmse = float(np.sqrt(np.mean((x @ weights - y) ** 2)))
    equal_rmse = float(np.sqrt(np.mean((x @ equal - y) ** 2)))
    return WeightCalibration(
        weights={col: float(weight) for col, weight in zip(expert_columns, weights)},
        rows=len(data),
        rmse=calibrated_rmse,
        equal_weight_rmse=equal_rmse,
        improvement=equal_rmse - calibrated_rmse,
    )
