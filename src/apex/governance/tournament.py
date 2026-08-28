from __future__ import annotations

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

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
            yield np.array(counts, dtype=float) / units


def research_weight_tournament(
    paired: pd.DataFrame,
    providers: list[str],
    *,
    train_gameweeks: set[int],
    test_gameweeks: set[int],
    step: float = 0.05,
) -> list[WeightCandidate]:
    """Research-only ensemble search. It cannot alter serving-provider governance."""
    if len(providers) < 2:
        raise ValueError("weight tournament requires at least two providers")
    results = []
    for weights in _simplex_grid(len(providers), step):
        data = paired.copy()
        data["predicted_points"] = sum(
            float(weights[index]) * data[provider]
            for index, provider in enumerate(providers)
        )
        train = data[data.gameweek.isin(train_gameweeks)][
            ["gameweek", "element_id", "predicted_points", "actual_points"]
        ]
        test = data[data.gameweek.isin(test_gameweeks)][
            ["gameweek", "element_id", "predicted_points", "actual_points"]
        ]
        if train.empty or test.empty:
            continue
        train_metrics = score_predictions(train)
        test_metrics = score_predictions(test)
        train_score = (
            0.5 * train_metrics.mean_spearman + 0.5 * train_metrics.mean_ndcg10
        )
        test_score = (
            0.5 * test_metrics.mean_spearman + 0.5 * test_metrics.mean_ndcg10
        )
        results.append(
            WeightCandidate(
                {
                    provider: float(weights[index])
                    for index, provider in enumerate(providers)
                },
                train_score,
                test_score,
                test_metrics.mae,
                test_metrics.rmse,
            )
        )
    return sorted(
        results,
        key=lambda item: (
            -item.test_score,
            item.test_mae,
            item.test_rmse,
            tuple(item.weights.values()),
        ),
    )
