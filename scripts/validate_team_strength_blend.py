#!/usr/bin/env python3
"""Temporal validation of Understat/Elo combination choices.

Understat hyperparameters are frozen from the independent 2022/23+2023/24
calibration. FPL Core Elo is available for 2025/26. GW1-19 select only the
convex blend weight; GW20-38 remain untouched for evaluation.

The script also scores the naive multiplicative Understat×Elo behavior that the
current fixture function would produce if a team-goal surface were enabled
without changing Elo handling.
"""
from __future__ import annotations

import argparse
import io
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from apex_fpl.config import load_settings
from apex_fpl.data.team_mapping import canonical_team
from apex_fpl.data.understat import load_understat_history
from apex_fpl.models.fixtures import AWAY_GOALS_BASELINE, HOME_GOALS_BASELINE
from apex_fpl.models.team_goals import TeamGoalConfig
from apex_fpl.services.provenance import load_upstream_pins
from validate_team_strength import _bootstrap_delta, _loss_columns, _predict_season

CORE_SEASON = "2025-2026"
BLEND_GRID = (0.0, 0.25, 0.50, 0.75, 1.0)  # weight on Understat
FROZEN_CFG = TeamGoalConfig(half_life_days=180.0, prior_matches=5.0)


def _raw_url(ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/{ref}/{path}"


def _read_csv(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def _core_rows(ref: str) -> pd.DataFrame:
    teams = _read_csv(_raw_url(ref, f"data/{CORE_SEASON}/teams.csv"))
    label = "fotmob_name" if "fotmob_name" in teams.columns else "name"
    mapping = {
        int(code): canonical_team(name)
        for code, name in zip(
            pd.to_numeric(teams["code"], errors="coerce"), teams[label], strict=False
        )
        if pd.notna(code) and pd.notna(name)
    }
    rows: list[pd.DataFrame] = []
    for gw in range(1, 39):
        try:
            frame = _read_csv(
                _raw_url(ref, f"data/{CORE_SEASON}/By Gameweek/GW{gw}/fixtures.csv")
            )
        except requests.HTTPError:
            continue
        current = frame[pd.to_numeric(frame.get("gameweek"), errors="coerce") == gw].copy()
        required = {
            "home_team",
            "away_team",
            "home_team_elo",
            "away_team_elo",
            "home_expected_goals_xg",
            "away_expected_goals_xg",
            "home_score",
            "away_score",
        }
        if current.empty or not required.issubset(current.columns):
            continue
        current["gw"] = gw
        current["team_home"] = pd.to_numeric(current["home_team"], errors="coerce").map(mapping)
        current["team_away"] = pd.to_numeric(current["away_team"], errors="coerce").map(mapping)
        for src, dst in [
            ("home_team_elo", "elo_home"),
            ("away_team_elo", "elo_away"),
            ("home_expected_goals_xg", "actual_xg_home"),
            ("away_expected_goals_xg", "actual_xg_away"),
            ("home_score", "goals_home"),
            ("away_score", "goals_away"),
        ]:
            current[dst] = pd.to_numeric(current[src], errors="coerce")
        rows.append(
            current[
                [
                    "gw",
                    "team_home",
                    "team_away",
                    "elo_home",
                    "elo_away",
                    "actual_xg_home",
                    "actual_xg_away",
                    "goals_home",
                    "goals_away",
                ]
            ]
        )
    if not rows:
        raise RuntimeError("no FPL Core Elo holdout rows available")
    out = pd.concat(rows, ignore_index=True).dropna()
    return out.drop_duplicates(["gw", "team_home", "team_away"]).reset_index(drop=True)


def _elo_lambdas(d: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    diff = d["elo_home"].to_numpy(float) - d["elo_away"].to_numpy(float)
    raw = np.clip(np.exp(diff / 1200.0), 0.72, 1.38)
    home_mult = raw**0.45
    away_mult = (1.0 / raw) ** 0.45
    home = np.clip(HOME_GOALS_BASELINE * home_mult, 0.40, 3.35)
    away = np.clip(AWAY_GOALS_BASELINE * away_mult, 0.30, 2.95)
    return home, away, home_mult, away_mult


def _model_metrics(d: pd.DataFrame, prefix: str) -> dict:
    return {
        "xg_rmse": math.sqrt(float(d[f"{prefix}_xg_sq"].mean() / 2.0)),
        "clean_sheet_brier": float(d[f"{prefix}_cs_brier"].mean() / 2.0),
        "goal_poisson_nll": float(d[f"{prefix}_goal_nll"].mean() / 2.0),
    }


def _add_models(d: pd.DataFrame, alpha: float) -> pd.DataFrame:
    elo_home, elo_away, home_mult, away_mult = _elo_lambdas(d)
    u_home = d["pred_home"].to_numpy(float)
    u_away = d["pred_away"].to_numpy(float)
    blend_home = alpha * u_home + (1.0 - alpha) * elo_home
    blend_away = alpha * u_away + (1.0 - alpha) * elo_away
    multiply_home = np.clip(u_home * home_mult, 0.40, 3.35)
    multiply_away = np.clip(u_away * away_mult, 0.30, 2.95)
    out = _loss_columns(d, "understat", u_home, u_away)
    out = _loss_columns(out, "elo", elo_home, elo_away)
    out = _loss_columns(out, "blend", blend_home, blend_away)
    return _loss_columns(out, "multiplicative", multiply_home, multiply_away)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/team_strength_blend_validation.json")
    args = parser.parse_args()

    settings = load_settings()
    pins = load_upstream_pins(settings.upstreams_lock_path)
    core_ref = str(pins.get("fpl_core_insights", {}).get("commit", "")) or "main"
    history = load_understat_history(
        range(2018, 2027),
        active_season=2026,
        cache_dir=settings.cache_dir / "understat",
        refresh_active=False,
    )
    understat = _predict_season(history.matches, 2025, FROZEN_CFG)[
        ["team_home", "team_away", "pred_home", "pred_away"]
    ].drop_duplicates(["team_home", "team_away"])
    core = _core_rows(core_ref)
    d = core.merge(understat, on=["team_home", "team_away"], how="inner", validate="many_to_one")
    if len(d) < 300:
        raise RuntimeError(f"insufficient Elo/Understat overlap: {len(d)} matches")

    train = d[d["gw"] <= 19].copy()
    test = d[d["gw"] >= 20].copy()
    grid: list[dict] = []
    selected: float | None = None
    best: tuple[float, float, float] | None = None
    for alpha in BLEND_GRID:
        scored = _add_models(train, alpha)
        metric = _model_metrics(scored, "blend")
        grid.append({"understat_weight": alpha, **metric})
        key = (metric["xg_rmse"], metric["clean_sheet_brier"], alpha)
        if best is None or key < best:
            best = key
            selected = alpha
    if selected is None:
        raise RuntimeError("blend calibration failed")

    scored = _add_models(test, selected)
    metrics = {
        name: _model_metrics(scored, name)
        for name in ("understat", "elo", "blend", "multiplicative")
    }
    comparisons = {}
    for rival in ("understat", "elo", "multiplicative"):
        comparisons[f"blend_vs_{rival}"] = {
            "xg_squared_error_delta_bootstrap": _bootstrap_delta(
                scored, "blend_xg_sq", f"{rival}_xg_sq"
            ),
            "clean_sheet_brier_delta_bootstrap": _bootstrap_delta(
                scored, "blend_cs_brier", f"{rival}_cs_brier"
            ),
            "goal_nll_delta_bootstrap": _bootstrap_delta(
                scored, "blend_goal_nll", f"{rival}_goal_nll"
            ),
        }

    blend_best_xg = metrics["blend"]["xg_rmse"] <= min(
        metrics["understat"]["xg_rmse"], metrics["elo"]["xg_rmse"]
    )
    blend_best_cs = metrics["blend"]["clean_sheet_brier"] <= min(
        metrics["understat"]["clean_sheet_brier"], metrics["elo"]["clean_sheet_brier"]
    )
    multiplicative_safe = (
        metrics["multiplicative"]["xg_rmse"]
        <= max(metrics["understat"]["xg_rmse"], metrics["elo"]["xg_rmse"])
    )
    candidate = bool(blend_best_xg and blend_best_cs)

    report = {
        "contract": "apex-team-strength-blend-validation-v1",
        "production_changed": False,
        "understat_config_frozen_before_elo_blend_test": {
            "half_life_days": FROZEN_CFG.half_life_days,
            "prior_matches": FROZEN_CFG.prior_matches,
        },
        "blend_calibration_gws": "1-19",
        "blend_holdout_gws": "20-38",
        "blend_grid": list(BLEND_GRID),
        "selected_understat_weight": selected,
        "calibration_scores": grid,
        "holdout_n_matches": int(len(test)),
        "holdout_metrics": metrics,
        "holdout_comparisons": comparisons,
        "blend_candidate_ready_for_shadow_integration": candidate,
        "naive_multiplicative_combination_safe": bool(multiplicative_safe),
        "note": (
            "The selected convex blend weight sees only GW1-19. GW20-38 are untouched. "
            "The multiplicative surface mirrors the current fixture code behavior if an "
            "Understat team-goal surface is enabled while Elo multiplication remains active."
        ),
    }
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"blend_candidate": candidate, "selected_weight": selected, "output": str(path)}, indent=2))


if __name__ == "__main__":
    main()
