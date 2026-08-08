#!/usr/bin/env python3
"""No-hindsight validation for the Understat team-goal challenger.

This does not promote or modify the production fixture model. It calibrates the
existing time-decayed Understat/xG rating hyperparameters on completed 2022/23
and 2023/24 seasons, then evaluates the frozen configuration independently on
2024/25 and 2025/26.

The challenger is compared with Apex's neutral pre-GW fallback (1.55 home goals,
1.25 away goals). A later step is still required to compare against historical
FPL Core Elo before any production promotion.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.understat import load_understat_history
from apex_fpl.models.fixtures import AWAY_GOALS_BASELINE, HOME_GOALS_BASELINE
from apex_fpl.models.team_goals import TeamGoalConfig

CALIBRATION = (2022, 2023)
HOLDOUTS = (2024, 2025)
HALF_LIFE_GRID = (120.0, 180.0, 240.0, 360.0, 540.0)
PRIOR_MATCH_GRID = (5.0, 10.0, 20.0, 30.0)


def _weighted_ratio(total: float, weight: float, baseline: float) -> float:
    if weight <= 0 or baseline <= 0:
        return 1.0
    return float(total / weight / baseline)


def _ratings_at_cutoff(
    matches: pd.DataFrame,
    teams: list[str],
    cutoff: pd.Timestamp,
    cfg: TeamGoalConfig,
) -> tuple[pd.DataFrame, float, float]:
    """Vectorized equivalent of build_team_ratings for one historical cutoff."""
    d = matches[matches["date"] < cutoff].copy()
    if d.empty:
        raise ValueError("no team-goal history before cutoff")
    age_days = (cutoff - d["date"]).dt.total_seconds() / 86400.0
    d["weight"] = np.exp(-math.log(2.0) * age_days / cfg.half_life_days)
    d["wxg_home"] = d["weight"] * d["xg_home"]
    d["wxg_away"] = d["weight"] * d["xg_away"]
    total_weight = float(d["weight"].sum())
    league_home = float(d["wxg_home"].sum() / total_weight)
    league_away = float(d["wxg_away"].sum() / total_weight)

    home = d.groupby("team_home", as_index=True).agg(
        home_weight=("weight", "sum"),
        home_xgf=("wxg_home", "sum"),
        home_xga=("wxg_away", "sum"),
    )
    away = d.groupby("team_away", as_index=True).agg(
        away_weight=("weight", "sum"),
        away_xgf=("wxg_away", "sum"),
        away_xga=("wxg_home", "sum"),
    )

    rows = []
    for team in teams:
        h = home.loc[team] if team in home.index else None
        a = away.loc[team] if team in away.index else None
        hw = float(h.home_weight) if h is not None else 0.0
        aw = float(a.away_weight) if a is not None else 0.0
        effective = hw + aw
        shrink = effective / (effective + cfg.prior_matches) if effective > 0 else 0.0

        ah_raw = _weighted_ratio(float(h.home_xgf) if h is not None else 0.0, hw, league_home)
        dh_raw = _weighted_ratio(float(h.home_xga) if h is not None else 0.0, hw, league_away)
        aa_raw = _weighted_ratio(float(a.away_xgf) if a is not None else 0.0, aw, league_away)
        da_raw = _weighted_ratio(float(a.away_xga) if a is not None else 0.0, aw, league_home)

        def shrunk(raw: float) -> float:
            return float(np.clip(1.0 + shrink * (raw - 1.0), 0.55, 1.65))

        rows.append(
            {
                "team": team,
                "attack_home": shrunk(ah_raw),
                "defence_home": shrunk(dh_raw),
                "attack_away": shrunk(aa_raw),
                "defence_away": shrunk(da_raw),
            }
        )
    return pd.DataFrame(rows).set_index("team"), league_home, league_away


def _predict_season(matches: pd.DataFrame, season: int, cfg: TeamGoalConfig) -> pd.DataFrame:
    target = matches[matches["season"] == season].sort_values("date").copy()
    teams = sorted(set(target["team_home"]).union(set(target["team_away"])))
    rows: list[dict] = []

    # All matches sharing a date use the same strictly pre-date information set.
    for date, group in target.groupby("date", sort=True):
        ratings, league_home, league_away = _ratings_at_cutoff(
            matches,
            teams,
            pd.Timestamp(date),
            cfg,
        )
        for match in group.itertuples(index=False):
            home = ratings.loc[match.team_home]
            away = ratings.loc[match.team_away]
            ph = float(
                np.clip(
                    league_home * float(home.attack_home) * float(away.defence_away),
                    cfg.min_expected_goals,
                    cfg.max_expected_goals,
                )
            )
            pa = float(
                np.clip(
                    league_away * float(away.attack_away) * float(home.defence_home),
                    cfg.min_expected_goals,
                    cfg.max_expected_goals,
                )
            )
            rows.append(
                {
                    "date": match.date,
                    "season": season,
                    "team_home": match.team_home,
                    "team_away": match.team_away,
                    "pred_home": ph,
                    "pred_away": pa,
                    "actual_xg_home": float(match.xg_home),
                    "actual_xg_away": float(match.xg_away),
                    "goals_home": float(match.goals_home),
                    "goals_away": float(match.goals_away),
                }
            )
    return pd.DataFrame(rows)


def _poisson_nll(goals: np.ndarray, lam: np.ndarray) -> np.ndarray:
    lam = np.clip(lam, 1e-9, None)
    return lam - goals * np.log(lam) + np.vectorize(math.lgamma)(goals + 1.0)


def _loss_rows(pred: pd.DataFrame) -> pd.DataFrame:
    d = pred.copy()
    d["challenger_xg_sq"] = (
        (d["pred_home"] - d["actual_xg_home"]) ** 2
        + (d["pred_away"] - d["actual_xg_away"]) ** 2
    )
    d["baseline_xg_sq"] = (
        (HOME_GOALS_BASELINE - d["actual_xg_home"]) ** 2
        + (AWAY_GOALS_BASELINE - d["actual_xg_away"]) ** 2
    )

    challenger_home_cs = np.exp(-d["pred_away"])
    challenger_away_cs = np.exp(-d["pred_home"])
    baseline_home_cs = math.exp(-AWAY_GOALS_BASELINE)
    baseline_away_cs = math.exp(-HOME_GOALS_BASELINE)
    actual_home_cs = (d["goals_away"] == 0).astype(float)
    actual_away_cs = (d["goals_home"] == 0).astype(float)
    d["challenger_cs_brier"] = (
        (challenger_home_cs - actual_home_cs) ** 2
        + (challenger_away_cs - actual_away_cs) ** 2
    )
    d["baseline_cs_brier"] = (
        (baseline_home_cs - actual_home_cs) ** 2
        + (baseline_away_cs - actual_away_cs) ** 2
    )

    d["challenger_goal_nll"] = _poisson_nll(
        d["goals_home"].to_numpy(float), d["pred_home"].to_numpy(float)
    ) + _poisson_nll(d["goals_away"].to_numpy(float), d["pred_away"].to_numpy(float))
    d["baseline_goal_nll"] = _poisson_nll(
        d["goals_home"].to_numpy(float), np.full(len(d), HOME_GOALS_BASELINE)
    ) + _poisson_nll(
        d["goals_away"].to_numpy(float), np.full(len(d), AWAY_GOALS_BASELINE)
    )
    return d


def _bootstrap_delta(
    d: pd.DataFrame,
    challenger: str,
    baseline: str,
    *,
    n: int = 4000,
    seed: int = 20260808,
) -> dict:
    delta = (d[challenger] - d[baseline]).to_numpy(float)
    rng = np.random.default_rng(seed)
    means = np.empty(n, dtype=float)
    for idx in range(n):
        sample = rng.integers(0, len(delta), len(delta))
        means[idx] = float(np.mean(delta[sample]))
    return {
        "n_matches": int(len(d)),
        "mean_delta": float(np.mean(delta)),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
    }


def _metrics(pred: pd.DataFrame) -> dict:
    d = _loss_rows(pred)
    challenger_rmse = math.sqrt(float(d["challenger_xg_sq"].mean() / 2.0))
    baseline_rmse = math.sqrt(float(d["baseline_xg_sq"].mean() / 2.0))
    return {
        "n_matches": int(len(d)),
        "challenger_xg_rmse": challenger_rmse,
        "baseline_xg_rmse": baseline_rmse,
        "xg_rmse_ratio": challenger_rmse / baseline_rmse,
        "challenger_clean_sheet_brier": float(d["challenger_cs_brier"].mean() / 2.0),
        "baseline_clean_sheet_brier": float(d["baseline_cs_brier"].mean() / 2.0),
        "challenger_goal_poisson_nll": float(d["challenger_goal_nll"].mean() / 2.0),
        "baseline_goal_poisson_nll": float(d["baseline_goal_nll"].mean() / 2.0),
        "xg_squared_error_delta_bootstrap": _bootstrap_delta(
            d, "challenger_xg_sq", "baseline_xg_sq"
        ),
        "clean_sheet_brier_delta_bootstrap": _bootstrap_delta(
            d, "challenger_cs_brier", "baseline_cs_brier"
        ),
        "goal_nll_delta_bootstrap": _bootstrap_delta(
            d, "challenger_goal_nll", "baseline_goal_nll"
        ),
    }


def _passes(metrics: dict) -> bool:
    return bool(
        metrics["xg_squared_error_delta_bootstrap"]["ci95_high"] < 0
        and metrics["clean_sheet_brier_delta_bootstrap"]["ci95_high"] < 0
        and metrics["challenger_goal_poisson_nll"] <= metrics["baseline_goal_poisson_nll"]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/team_strength_validation.json")
    args = parser.parse_args()

    settings = load_settings()
    history = load_understat_history(
        range(2018, 2027),
        active_season=2026,
        cache_dir=settings.cache_dir / "understat",
        refresh_active=False,
    )
    matches = history.matches.copy()

    grid_scores: list[dict] = []
    best: tuple[float, float, float] | None = None
    selected: tuple[float, float] | None = None
    for half_life in HALF_LIFE_GRID:
        for prior_matches in PRIOR_MATCH_GRID:
            cfg = TeamGoalConfig(half_life_days=half_life, prior_matches=prior_matches)
            parts = [_predict_season(matches, season, cfg) for season in CALIBRATION]
            metrics = _metrics(pd.concat(parts, ignore_index=True))
            score = metrics["challenger_xg_rmse"]
            row = {
                "half_life_days": half_life,
                "prior_matches": prior_matches,
                "calibration_xg_rmse": score,
                "calibration_cs_brier": metrics["challenger_clean_sheet_brier"],
                "calibration_goal_nll": metrics["challenger_goal_poisson_nll"],
            }
            grid_scores.append(row)
            key = (
                score,
                metrics["challenger_clean_sheet_brier"],
                half_life + prior_matches / 1000.0,
            )
            if best is None or key < best:
                best = key
                selected = (half_life, prior_matches)

    if selected is None:
        raise RuntimeError("team-strength calibration produced no valid configuration")
    half_life, prior_matches = selected
    frozen = TeamGoalConfig(half_life_days=half_life, prior_matches=prior_matches)
    holdouts: dict[str, dict] = {}
    all_pass = True
    for season in HOLDOUTS:
        metrics = _metrics(_predict_season(matches, season, frozen))
        passed = _passes(metrics)
        holdouts[str(season)] = {
            "metrics": metrics,
            "pass_vs_neutral_fallback": passed,
        }
        all_pass = all_pass and passed

    report = {
        "contract": "apex-team-strength-validation-v1",
        "production_changed": False,
        "calibration_seasons": list(CALIBRATION),
        "holdout_seasons": list(HOLDOUTS),
        "grid": {
            "half_life_days": list(HALF_LIFE_GRID),
            "prior_matches": list(PRIOR_MATCH_GRID),
        },
        "selected_config": {
            "half_life_days": half_life,
            "prior_matches": prior_matches,
        },
        "grid_scores": grid_scores,
        "holdouts": holdouts,
        "challenger_validated_vs_neutral_fallback": bool(all_pass),
        "promotion_ready": False,
        "promotion_blocker": (
            "Historical head-to-head against the production FPL Core Elo surface is still "
            "required before any production fixture-model change."
        ),
        "understat_completed_seasons": list(history.completed_seasons),
        "understat_warnings": list(history.warnings),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "challenger_validated": all_pass,
                "selected_config": report["selected_config"],
                "output": str(path),
            },
            indent=2,
        )
    )
    raise SystemExit(0 if all_pass else 2)


if __name__ == "__main__":
    main()
