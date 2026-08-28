from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import spearmanr


@dataclass(frozen=True)
class ForecastMetrics:
    rows: int
    gameweeks: int
    rmse: float
    mae: float
    bias: float
    mean_spearman: float
    mean_ndcg10: float
    mean_ndcg25: float


def _ndcg(actual: np.ndarray, predicted: np.ndarray, k: int) -> float:
    if len(actual) == 0:
        return float("nan")
    k = min(int(k), len(actual))
    order = np.argsort(-predicted, kind="stable")[:k]
    ideal = np.argsort(-actual, kind="stable")[:k]
    denom = np.log2(np.arange(2, k + 2))
    dcg = float(np.sum(np.maximum(actual[order], 0.0) / denom))
    idcg = float(np.sum(np.maximum(actual[ideal], 0.0) / denom))
    return dcg / idcg if idcg > 0 else 0.0


def score_predictions(frame: pd.DataFrame) -> ForecastMetrics:
    required = {"gameweek", "element_id", "predicted_points", "actual_points"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing evaluation columns: {sorted(missing)}")
    d = frame.dropna(subset=list(required)).copy()
    if d.empty:
        raise ValueError("no paired forecast/outcome rows")
    error = d["predicted_points"].astype(float) - d["actual_points"].astype(float)
    spearman_values: list[float] = []
    ndcg10: list[float] = []
    ndcg25: list[float] = []
    for _, group in d.groupby("gameweek", sort=True):
        pred = group["predicted_points"].to_numpy(float)
        actual = group["actual_points"].to_numpy(float)
        rho = spearmanr(pred, actual).statistic
        spearman_values.append(float(rho) if np.isfinite(rho) else 0.0)
        ndcg10.append(_ndcg(actual, pred, 10))
        ndcg25.append(_ndcg(actual, pred, 25))
    return ForecastMetrics(
        rows=len(d),
        gameweeks=d["gameweek"].nunique(),
        rmse=float(np.sqrt(np.mean(np.square(error)))),
        mae=float(np.mean(np.abs(error))),
        bias=float(np.mean(error)),
        mean_spearman=float(np.mean(spearman_values)),
        mean_ndcg10=float(np.mean(ndcg10)),
        mean_ndcg25=float(np.mean(ndcg25)),
    )
