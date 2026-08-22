from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from apex_fpl.models.team_goals import (
    TeamGoalConfig,
    build_team_goal_surface,
    build_team_ratings,
)


@dataclass(frozen=True)
class TeamGoalBacktest:
    predictions: pd.DataFrame
    summary: pd.DataFrame
    ablation: pd.DataFrame


def _poisson_loss(actual: np.ndarray, expected: np.ndarray) -> float:
    lam = np.clip(np.asarray(expected, dtype=float), 1e-9, None)
    y = np.asarray(actual, dtype=float)
    lgamma = np.vectorize(math.lgamma)
    return float(np.mean(lam - y * np.log(lam) + lgamma(y + 1.0)))


def _metrics(frame: pd.DataFrame, prefix: str) -> dict[str, float]:
    actual = np.concatenate(
        [frame["goals_home"].to_numpy(float), frame["goals_away"].to_numpy(float)]
    )
    expected = np.concatenate(
        [frame[f"{prefix}_home"].to_numpy(float), frame[f"{prefix}_away"].to_numpy(float)]
    )
    actual_cs = np.concatenate(
        [
            (frame["goals_away"] == 0).to_numpy(float),
            (frame["goals_home"] == 0).to_numpy(float),
        ]
    )
    expected_cs = np.concatenate(
        [
            np.exp(-frame[f"{prefix}_away"].to_numpy(float)),
            np.exp(-frame[f"{prefix}_home"].to_numpy(float)),
        ]
    )
    return {
        "goal_mae": float(np.mean(np.abs(expected - actual))),
        "poisson_loss": _poisson_loss(actual, expected),
        "clean_sheet_brier": float(np.mean((expected_cs - actual_cs) ** 2)),
    }


def _predict_fold(
    prior: pd.DataFrame,
    test: pd.DataFrame,
    config: TeamGoalConfig,
) -> pd.DataFrame:
    names = sorted(set(test["team_home"]) | set(test["team_away"]))
    teams = pd.DataFrame({"id": range(1, len(names) + 1), "name": names})
    team_ids = dict(zip(teams["name"], teams["id"]))
    ratings = build_team_ratings(
        prior,
        teams,
        as_of=pd.to_datetime(test["date"], utc=True).min(),
        config=config,
    )
    # These are synthetic holdout fixtures rather than live Official FPL rows, but
    # the downstream model contract is intentionally identical: every fixture has
    # one stable immutable identity. The fold-local IDs are deterministic because
    # the test rows are chronologically ordered before this function is called.
    fixture_ids = np.arange(1, len(test) + 1)
    fixtures = pd.DataFrame(
        {
            "id": fixture_ids,
            "event": fixture_ids,
            "team_h": test["team_home"].map(team_ids),
            "team_a": test["team_away"].map(team_ids),
        }
    )
    surface = build_team_goal_surface(
        fixtures,
        ratings,
        fixtures["event"].tolist(),
        config=config,
    )
    home = surface[surface["is_home"]].set_index("gw")["expected_team_goals"]
    away = surface[~surface["is_home"]].set_index("gw")["expected_team_goals"]
    out = test.reset_index(drop=True).copy()
    out["model_home"] = out.index.to_series().add(1).map(home)
    out["model_away"] = out.index.to_series().add(1).map(away)
    out["baseline_home"] = float(pd.to_numeric(prior["goals_home"], errors="coerce").mean())
    out["baseline_away"] = float(pd.to_numeric(prior["goals_away"], errors="coerce").mean())
    return out


def run_team_goal_walk_forward(
    matches: pd.DataFrame,
    *,
    minimum_prior_seasons: int = 2,
) -> TeamGoalBacktest:
    """Evaluate each season using only matches completed before that season."""
    required = {
        "date",
        "season",
        "team_home",
        "team_away",
        "goals_home",
        "goals_away",
        "xg_home",
        "xg_away",
    }
    missing = sorted(required - set(matches.columns))
    if missing:
        raise ValueError(f"team-goal backtest missing columns: {missing}")
    d = matches.copy()
    d["date"] = pd.to_datetime(d["date"], utc=True, errors="coerce")
    d = d.dropna(subset=list(required)).sort_values("date").reset_index(drop=True)
    seasons = list(dict.fromkeys(d["season"].astype(str)))
    predictions: list[pd.DataFrame] = []
    summaries: list[dict] = []
    ablations: list[dict] = []
    configs = {
        "time_decay_shrinkage": TeamGoalConfig(),
        "no_time_decay": TeamGoalConfig(half_life_days=100000.0),
        "no_shrinkage": TeamGoalConfig(prior_matches=0.0),
    }

    for season in seasons:
        test = d[d["season"].astype(str) == season].copy()
        if test.empty:
            continue
        prior = d[d["date"] < test["date"].min()].copy()
        if prior["season"].astype(str).nunique() < minimum_prior_seasons:
            continue
        fold = _predict_fold(prior, test, configs["time_decay_shrinkage"])
        fold["test_season"] = season
        predictions.append(fold)
        for model in ("model", "baseline"):
            summaries.append(
                {"season": season, "model": model, "rows": len(fold), **_metrics(fold, model)}
            )
        for name, config in configs.items():
            variant = _predict_fold(prior, test, config)
            ablations.append(
                {"season": season, "variant": name, "rows": len(variant), **_metrics(variant, "model")}
            )

    return TeamGoalBacktest(
        pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame(),
        pd.DataFrame(summaries),
        pd.DataFrame(ablations),
    )
