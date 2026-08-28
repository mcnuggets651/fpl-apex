from __future__ import annotations

from dataclasses import asdict, dataclass

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

    def to_dict(self):
        return asdict(self)


def _ndcg(actual, predicted, k):
    if len(actual) == 0:
        return float("nan")
    k = min(k, len(actual))
    order = np.argsort(-predicted, kind="stable")[:k]
    ideal = np.argsort(-actual, kind="stable")[:k]
    denom = np.log2(np.arange(2, k + 2))
    dcg = float(np.sum(np.maximum(actual[order], 0) / denom))
    idcg = float(np.sum(np.maximum(actual[ideal], 0) / denom))
    return dcg / idcg if idcg > 0 else 0.0


def score_predictions(frame: pd.DataFrame) -> ForecastMetrics:
    required = {"gameweek", "element_id", "predicted_points", "actual_points"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing evaluation columns: {sorted(missing)}")
    data = frame.dropna(subset=list(required)).copy()
    if data.empty:
        raise ValueError("no paired forecast/outcome rows")
    error = data.predicted_points.astype(float) - data.actual_points.astype(float)
    spearman_values = []
    ndcg10_values = []
    ndcg25_values = []
    for _, group in data.groupby("gameweek", sort=True):
        predicted = group.predicted_points.to_numpy(float)
        actual = group.actual_points.to_numpy(float)
        rho = spearmanr(predicted, actual).statistic
        spearman_values.append(float(rho) if np.isfinite(rho) else 0)
        ndcg10_values.append(_ndcg(actual, predicted, 10))
        ndcg25_values.append(_ndcg(actual, predicted, 25))
    return ForecastMetrics(
        len(data),
        int(data.gameweek.nunique()),
        float(np.sqrt(np.mean(error * error))),
        float(np.mean(abs(error))),
        float(np.mean(error)),
        float(np.mean(spearman_values)),
        float(np.mean(ndcg10_values)),
        float(np.mean(ndcg25_values)),
    )


def paired_provider_frame(
    predictions: pd.DataFrame,
    outcomes: pd.DataFrame,
    providers: list[str],
) -> pd.DataFrame:
    key = ["season", "gameweek", "element_id"]
    base = outcomes[key + ["actual_points"]].drop_duplicates(key)
    for provider in providers:
        provider_rows = (
            predictions[predictions.provider_id.eq(provider)][
                key + ["predicted_points"]
            ]
            .drop_duplicates(key)
            .rename(columns={"predicted_points": provider})
        )
        base = base.merge(provider_rows, on=key, how="inner")
    return base
