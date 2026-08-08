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
from apex_fpl.models.team_goals import TeamGoalConfig, build_team_goal_surface, build_team_ratings

CALIBRATION = (2022, 2023)
HOLDOUTS = (2024, 2025)
HALF_LIFE_GRID = (120.0, 180.0, 240.0, 360.0, 540.0)
PRIOR_MATCH_GRID = (5.0, 10.0, 20.0, 30.0)


def _season_teams(matches: pd.DataFrame, season: int) -> pd.DataFrame:
    d = matches[matches["season"] == season]
    names = sorted(set(d["team_home"]).union(set(d["team_away"])))
    return pd.DataFrame({"id": range(1, len(names) + 1), "name": names})


def _predict_season(matches: pd.DataFrame, season: int, cfg: TeamGoalConfig) -> pd.DataFrame:
    target = matches[matches["season"] == season].sort_values("date").copy()
    teams = _season_teams(matches, season)
    ids = dict(zip(teams["name"], teams["id"], strict=True))
    rows: list[dict] = []

    # Ratings are recomputed only when the match date changes; all matches on the
    # same date share exactly the same pre-kickoff information set.
    for date, group in target.groupby("date", sort=True):
        ratings = build_team_ratings(matches, teams, as_of=pd.Timestamp(date), config=cfg)
        fixtures = pd.DataFrame(
            {
                "event": 1,
                "team_h": [ids[name] for name in group["team_home"]],
                "team_a": [ids[name] for name in group["team_away"]],
            }
        )
        surface = build_team_goal_surface(fixtures, ratings, [1], config=cfg)
        home_surface = surface[surface["is_home"]][["team", "opponent", "expected_team_goals"]].copy()
        home_surface = home_surface.rename(columns={"expected_team_goals": "pred_home"})
        away_surface = surface[~surface["is_home"]][["team", "opponent", "expected_team_goals"]].copy()
        away_surface = away_surface.rename(columns={"expected_team_goals": "pred_away"})
        pred = home_surface.merge(
            away_surface,
            left_on=["team", "opponent"],
            right_on=["opponent", "team"],
            suffixes=("_home", "_away"),
            validate="one_to_one",
        )
        lookup = {
            (int(r.team_home), int(r.opponent_home)): (float(r.pred_home), float(r.pred_away))
            for r in pred.itertuples(index=False)
        }
        for match in group.itertuples(index=False):
            home_id, away_id = ids[match.team_home], ids[match.team_away]
            ph, pa = lookup[(home_id, away_id)]
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
    d["challenger_xg_sq"] = (d["pred_home"] - d["actual_xg_home"]) ** 2 + (d["pred_away"] - d["actual_xg_away"]) ** 2
    d["baseline_xg_sq"] = (HOME_GOALS_BASELINE - d["actual_xg_home"]) ** 2 + (AWAY_GOALS_BASELINE - d["actual_xg_away"]) ** 2

    challenger_home_cs = np.exp(-d["pred_away"])
    challenger_away_cs = np.exp(-d["pred_home"])
    baseline_home_cs = math.exp(-AWAY_GOALS_BASELINE)
    baseline_away_cs = math.exp(-HOME_GOALS_BASELINE)
    actual_home_cs = (d["goals_away"] == 0).astype(float)
    actual_away_cs = (d["goals_home"] == 0).astype(float)
    d["challenger_cs_brier"] = (challenger_home_cs - actual_home_cs) ** 2 + (challenger_away_cs - actual_away_cs) ** 2
    d["baseline_cs_brier"] = (baseline_home_cs - actual_home_cs) ** 2 + (baseline_away_cs - actual_away_cs) ** 2

    d["challenger_goal_nll"] = _poisson_nll(d["goals_home"].to_numpy(float), d["pred_home"].to_numpy(float)) + _poisson_nll(d["goals_away"].to_numpy(float), d["pred_away"].to_numpy(float))
    d["baseline_goal_nll"] = _poisson_nll(d["goals_home"].to_numpy(float), np.full(len(d), HOME_GOALS_BASELINE)) + _poisson_nll(d["goals_away"].to_numpy(float), np.full(len(d), AWAY_GOALS_BASELINE))
    return d


def _bootstrap_delta(d: pd.DataFrame, challenger: str, baseline: str, *, n: int = 4000, seed: int = 20260808) -> dict:
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
        "xg_squared_error_delta_bootstrap": _bootstrap_delta(d, "challenger_xg_sq", "baseline_xg_sq"),
        "clean_sheet_brier_delta_bootstrap": _bootstrap_delta(d, "challenger_cs_brier", "baseline_cs_brier"),
        "goal_nll_delta_bootstrap": _bootstrap_delta(d, "challenger_goal_nll", "baseline_goal_nll"),
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
            key = (score, metrics["challenger_clean_sheet_brier"], half_life + prior_matches / 1000.0)
            if best is None or key < best:
                best = key
                selected = (half_life, prior_matches)

    half_life, prior_matches = selected
    frozen = TeamGoalConfig(half_life_days=half_life, prior_matches=prior_matches)
    holdouts: dict[str, dict] = {}
    all_pass = True
    for season in HOLDOUTS:
        metrics = _metrics(_predict_season(matches, season, frozen))
        passed = _passes(metrics)
        holdouts[str(season)] = {"metrics": metrics, "pass_vs_neutral_fallback": passed}
        all_pass = all_pass and passed

    report = {
        "contract": "apex-team-strength-validation-v1",
        "production_changed": False,
        "calibration_seasons": list(CALIBRATION),
        "holdout_seasons": list(HOLDOUTS),
        "grid": {"half_life_days": list(HALF_LIFE_GRID), "prior_matches": list(PRIOR_MATCH_GRID)},
        "selected_config": {"half_life_days": half_life, "prior_matches": prior_matches},
        "grid_scores": grid_scores,
        "holdouts": holdouts,
        "challenger_validated_vs_neutral_fallback": bool(all_pass),
        "promotion_ready": False,
        "promotion_blocker": "Historical head-to-head against the production FPL Core Elo surface is still required before any production fixture-model change.",
        "understat_completed_seasons": list(history.completed_seasons),
        "understat_warnings": list(history.warnings),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"challenger_validated": all_pass, "selected_config": report["selected_config"], "output": str(path)}, indent=2))
    raise SystemExit(0 if all_pass else 2)


if __name__ == "__main__":
    main()
