from __future__ import annotations
from dataclasses import dataclass, asdict
import numpy as np, pandas as pd
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
        return float('nan')
    k = min(k, len(actual))
    order = np.argsort(-predicted, kind='stable')[:k]
    ideal = np.argsort(-actual, kind='stable')[:k]
    denom = np.log2(np.arange(2, k + 2))
    dcg = float(np.sum(np.maximum(actual[order], 0) / denom))
    idcg = float(np.sum(np.maximum(actual[ideal], 0) / denom))
    return dcg / idcg if idcg > 0 else 0.0

def score_predictions(frame: pd.DataFrame) -> ForecastMetrics:
    required = {'gameweek', 'element_id', 'predicted_points', 'actual_points'}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f'missing evaluation columns: {sorted(missing)}')
    d = frame.dropna(subset=list(required)).copy()
    if d.empty:
        raise ValueError('no paired forecast/outcome rows')
    e = d.predicted_points.astype(float) - d.actual_points.astype(float)
    spears = []
    n10 = []
    n25 = []
    for _, g in d.groupby('gameweek', sort=True):
        pred = g.predicted_points.to_numpy(float)
        act = g.actual_points.to_numpy(float)
        rho = spearmanr(pred, act).statistic
        spears.append(float(rho) if np.isfinite(rho) else 0)
        n10.append(_ndcg(act, pred, 10))
        n25.append(_ndcg(act, pred, 25))
    return ForecastMetrics(len(d), int(d.gameweek.nunique()), float(np.sqrt(np.mean(e * e))), float(np.mean(abs(e))), float(np.mean(e)), float(np.mean(spears)), float(np.mean(n10)), float(np.mean(n25)))

def paired_provider_frame(predictions: pd.DataFrame, outcomes: pd.DataFrame, providers: list[str]) -> pd.DataFrame:
    key = ['season', 'gameweek', 'element_id']
    base = outcomes[key + ['actual_points']].drop_duplicates(key)
    for provider in providers:
        p = predictions[predictions.provider_id.eq(provider)][key + ['predicted_points']].drop_duplicates(key).rename(columns={'predicted_points': provider})
        base = base.merge(p, on=key, how='inner')
    return base
