from __future__ import annotations

from dataclasses import dataclass
import numpy as np
import pandas as pd


@dataclass
class BacktestMetrics:
    mae: float
    rmse: float
    bias: float
    rank_correlation: float


def score_predictions(df: pd.DataFrame, prediction_col: str = "xp", actual_col: str = "event_points") -> BacktestMetrics:
    d = df[[prediction_col, actual_col]].apply(pd.to_numeric, errors="coerce").dropna()
    if d.empty:
        return BacktestMetrics(float("nan"), float("nan"), float("nan"), float("nan"))
    err = d[prediction_col] - d[actual_col]
    return BacktestMetrics(
        mae=float(np.mean(np.abs(err))),
        rmse=float(np.sqrt(np.mean(err ** 2))),
        bias=float(np.mean(err)),
        rank_correlation=float(d[prediction_col].rank().corr(d[actual_col].rank())),
    )
