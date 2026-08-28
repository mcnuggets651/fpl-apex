from __future__ import annotations
from dataclasses import dataclass
from itertools import product
import numpy as np, pandas as pd
from .evaluation import score_predictions

@dataclass(frozen=True)
class WeightCandidate:
    weights: dict[str, float]
    train_score: float
    test_score: float
    test_mae: float
    test_rmse: float

def _simplex_grid(n: int, step: float):
    units = round(1 / step)
    for counts in product(range(units + 1), repeat=n):
        if sum(counts) == units:
            yield (np.array(counts, dtype=float) / units)

def research_weight_tournament(paired: pd.DataFrame, providers: list[str], *, train_gameweeks: set[int], test_gameweeks: set[int], step: float=0.05) -> list[WeightCandidate]:
    """Research-only ensemble search. It cannot alter serving-provider governance.

    Weights are learned only on a chronological training window and ranked by a
    held-out decision score (mean of within-GW Spearman and NDCG@10). No weights
    should be promoted from this function without the separate governance process.
    """
    if len(providers) < 2:
        raise ValueError('weight tournament requires at least two providers')
    results = []
    for w in _simplex_grid(len(providers), step):
        d = paired.copy()
        d['predicted_points'] = sum((float(w[i]) * d[p] for i, p in enumerate(providers)))
        tr = d[d.gameweek.isin(train_gameweeks)][['gameweek', 'element_id', 'predicted_points', 'actual_points']]
        te = d[d.gameweek.isin(test_gameweeks)][['gameweek', 'element_id', 'predicted_points', 'actual_points']]
        if tr.empty or te.empty:
            continue
        tm = score_predictions(tr)
        em = score_predictions(te)
        ts = 0.5 * tm.mean_spearman + 0.5 * tm.mean_ndcg10
        es = 0.5 * em.mean_spearman + 0.5 * em.mean_ndcg10
        results.append(WeightCandidate({p: float(w[i]) for i, p in enumerate(providers)}, ts, es, em.mae, em.rmse))
    return sorted(results, key=lambda x: (-x.test_score, x.test_mae, x.test_rmse, tuple(x.weights.values())))
