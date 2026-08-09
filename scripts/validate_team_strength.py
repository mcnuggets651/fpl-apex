#!/usr/bin/env python3
"""No-hindsight validation for the Understat team-goal challenger.

The challenger is calibrated only on completed 2022/23 + 2023/24 Understat
history, then evaluated on untouched 2024/25 and 2025/26. It is first compared
with Apex's neutral pre-GW fallback and then, where historical source coverage
exists, with the exact Elo transform used by current production.

This script is diagnostic only and never changes the canonical fixture model.
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

CALIBRATION = (2022, 2023)
HOLDOUTS = (2024, 2025)
HALF_LIFE_GRID = (120.0, 180.0, 240.0, 360.0, 540.0)
PRIOR_MATCH_GRID = (5.0, 10.0, 20.0, 30.0)
CORE_ELO_SEASON = "2025-2026"


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
        ah = _weighted_ratio(float(h.home_xgf) if h is not None else 0.0, hw, league_home)
        dh = _weighted_ratio(float(h.home_xga) if h is not None else 0.0, hw, league_away)
        aa = _weighted_ratio(float(a.away_xgf) if a is not None else 0.0, aw, league_away)
        da = _weighted_ratio(float(a.away_xga) if a is not None else 0.0, aw, league_home)

        def shrunk(raw: float) -> float:
            return float(np.clip(1.0 + shrink * (raw - 1.0), 0.55, 1.65))

        rows.append(
            {
                "team": team,
                "attack_home": shrunk(ah),
                "defence_home": shrunk(dh),
                "attack_away": shrunk(aa),
                "defence_away": shrunk(da),
            }
        )
    return pd.DataFrame(rows).set_index("team"), league_home, league_away


def _predict_season(matches: pd.DataFrame, season: int, cfg: TeamGoalConfig) -> pd.DataFrame:
    target = matches[matches["season"] == season].sort_values("date").copy()
    teams = sorted(set(target["team_home"]).union(set(target["team_away"])))
    rows: list[dict] = []
    for date, group in target.groupby("date", sort=True):
        ratings, league_home, league_away = _ratings_at_cutoff(
            matches, teams, pd.Timestamp(date), cfg
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


def _loss_columns(
    d: pd.DataFrame,
    prefix: str,
    home_pred: pd.Series | np.ndarray,
    away_pred: pd.Series | np.ndarray,
) -> pd.DataFrame:
    ph = np.asarray(home_pred, dtype=float)
    pa = np.asarray(away_pred, dtype=float)
    out = d.copy()
    out[f"{prefix}_xg_sq"] = (
        (ph - out["actual_xg_home"].to_numpy(float)) ** 2
        + (pa - out["actual_xg_away"].to_numpy(float)) ** 2
    )
    actual_home_cs = (out["goals_away"] == 0).to_numpy(float)
    actual_away_cs = (out["goals_home"] == 0).to_numpy(float)
    out[f"{prefix}_cs_brier"] = (
        (np.exp(-pa) - actual_home_cs) ** 2
        + (np.exp(-ph) - actual_away_cs) ** 2
    )
    out[f"{prefix}_goal_nll"] = _poisson_nll(
        out["goals_home"].to_numpy(float), ph
    ) + _poisson_nll(out["goals_away"].to_numpy(float), pa)
    return out


def _loss_rows(pred: pd.DataFrame) -> pd.DataFrame:
    d = _loss_columns(pred, "challenger", pred["pred_home"], pred["pred_away"])
    return _loss_columns(
        d,
        "baseline",
        np.full(len(d), HOME_GOALS_BASELINE),
        np.full(len(d), AWAY_GOALS_BASELINE),
    )


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


def _raw_core_url(ref: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/olbauday/FPL-Core-Insights/{ref}/{path}"


def _read_csv(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def _load_core_elo_holdout(ref: str) -> pd.DataFrame:
    teams = _read_csv(_raw_core_url(ref, f"data/{CORE_ELO_SEASON}/teams.csv"))
    name_col = "fotmob_name" if "fotmob_name" in teams.columns else "name"
    mapping = {
        int(code): canonical_team(name)
        for code, name in zip(
            pd.to_numeric(teams["code"], errors="coerce"), teams[name_col], strict=False
        )
        if pd.notna(code) and pd.notna(name)
    }
    rows: list[pd.DataFrame] = []
    for gw in range(1, 39):
        url = _raw_core_url(ref, f"data/{CORE_ELO_SEASON}/By Gameweek/GW{gw}/fixtures.csv")
        try:
            frame = _read_csv(url)
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
        current["team_home"] = pd.to_numeric(current["home_team"], errors="coerce").map(mapping)
        current["team_away"] = pd.to_numeric(current["away_team"], errors="coerce").map(mapping)
        current["elo_home"] = pd.to_numeric(current["home_team_elo"], errors="coerce")
        current["elo_away"] = pd.to_numeric(current["away_team_elo"], errors="coerce")
        current["actual_xg_home"] = pd.to_numeric(
            current["home_expected_goals_xg"], errors="coerce"
        )
        current["actual_xg_away"] = pd.to_numeric(
            current["away_expected_goals_xg"], errors="coerce"
        )
        current["goals_home"] = pd.to_numeric(current["home_score"], errors="coerce")
        current["goals_away"] = pd.to_numeric(current["away_score"], errors="coerce")
        rows.append(
            current[
                [
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
        return pd.DataFrame()
    out = pd.concat(rows, ignore_index=True).dropna()
    return out.drop_duplicates(["team_home", "team_away"]).reset_index(drop=True)


def _production_elo_lambdas(frame: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    diff = frame["elo_home"].to_numpy(float) - frame["elo_away"].to_numpy(float)
    raw = np.clip(np.exp(diff / 1200.0), 0.72, 1.38)
    home_mult = raw**0.45
    away_mult = (1.0 / raw) ** 0.45
    home = np.clip(HOME_GOALS_BASELINE * home_mult, 0.40, 3.35)
    away = np.clip(AWAY_GOALS_BASELINE * away_mult, 0.30, 2.95)
    return home, away


def _elo_head_to_head(
    understat_prediction: pd.DataFrame,
    core: pd.DataFrame,
) -> dict:
    if core.empty:
        return {"status": "unavailable", "pass": False}
    u = understat_prediction[
        ["team_home", "team_away", "pred_home", "pred_away"]
    ].drop_duplicates(["team_home", "team_away"])
    d = core.merge(u, on=["team_home", "team_away"], how="inner", validate="one_to_one")
    if len(d) < 300:
        return {"status": "insufficient_coverage", "n_matches": int(len(d)), "pass": False}
    elo_home, elo_away = _production_elo_lambdas(d)
    d = _loss_columns(d, "understat", d["pred_home"], d["pred_away"])
    d = _loss_columns(d, "elo", elo_home, elo_away)

    understat_rmse = math.sqrt(float(d["understat_xg_sq"].mean() / 2.0))
    elo_rmse = math.sqrt(float(d["elo_xg_sq"].mean() / 2.0))
    xg_delta = _bootstrap_delta(d, "understat_xg_sq", "elo_xg_sq")
    cs_delta = _bootstrap_delta(d, "understat_cs_brier", "elo_cs_brier")
    nll_delta = _bootstrap_delta(d, "understat_goal_nll", "elo_goal_nll")
    passed = bool(
        xg_delta["ci95_high"] < 0
        and cs_delta["mean_delta"] <= 0
        and float(d["understat_goal_nll"].mean()) <= float(d["elo_goal_nll"].mean())
    )
    return {
        "status": "validated" if passed else "mixed_or_failed",
        "n_matches": int(len(d)),
        "understat_xg_rmse": understat_rmse,
        "production_elo_xg_rmse": elo_rmse,
        "xg_rmse_ratio": understat_rmse / elo_rmse,
        "understat_clean_sheet_brier": float(d["understat_cs_brier"].mean() / 2.0),
        "production_elo_clean_sheet_brier": float(d["elo_cs_brier"].mean() / 2.0),
        "understat_goal_poisson_nll": float(d["understat_goal_nll"].mean() / 2.0),
        "production_elo_goal_poisson_nll": float(d["elo_goal_nll"].mean() / 2.0),
        "xg_squared_error_delta_bootstrap": xg_delta,
        "clean_sheet_brier_delta_bootstrap": cs_delta,
        "goal_nll_delta_bootstrap": nll_delta,
        "pass": passed,
        "evidence_note": (
            "Pinned FPL Core provides comparable pre-match GW Elo snapshots for 2025/26. "
            "Equivalent 2024/25 GW Elo snapshots are unavailable at the pinned revision, so "
            "this is one independent Elo replication season rather than two."
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="reports/team_strength_validation.json")
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
    matches = history.matches.copy()

    grid_scores: list[dict] = []
    best: tuple[float, float, float] | None = None
    selected: tuple[float, float] | None = None
    for half_life in HALF_LIFE_GRID:
        for prior_matches in PRIOR_MATCH_GRID:
            cfg = TeamGoalConfig(half_life_days=half_life, prior_matches=prior_matches)
            parts = [_predict_season(matches, season, cfg) for season in CALIBRATION]
            metrics = _metrics(pd.concat(parts, ignore_index=True))
            row = {
                "half_life_days": half_life,
                "prior_matches": prior_matches,
                "calibration_xg_rmse": metrics["challenger_xg_rmse"],
                "calibration_cs_brier": metrics["challenger_clean_sheet_brier"],
                "calibration_goal_nll": metrics["challenger_goal_poisson_nll"],
            }
            grid_scores.append(row)
            key = (
                metrics["challenger_xg_rmse"],
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
    predictions: dict[int, pd.DataFrame] = {}
    all_fallback_pass = True
    for season in HOLDOUTS:
        prediction = _predict_season(matches, season, frozen)
        predictions[season] = prediction
        metrics = _metrics(prediction)
        passed = _passes(metrics)
        holdouts[str(season)] = {"metrics": metrics, "pass_vs_neutral_fallback": passed}
        all_fallback_pass = all_fallback_pass and passed

    core_holdout = _load_core_elo_holdout(core_ref)
    elo_h2h = _elo_head_to_head(predictions[2025], core_holdout)
    production_candidate_ready = bool(all_fallback_pass and elo_h2h.get("pass", False))

    report = {
        "contract": "apex-team-strength-validation-v2",
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
        "challenger_validated_vs_neutral_fallback": bool(all_fallback_pass),
        "fpl_core_ref": core_ref,
        "production_elo_head_to_head_2025_26": elo_h2h,
        "production_candidate_ready": production_candidate_ready,
        "promotion_ready": False,
        "promotion_blocker": (
            "Even a validated team-strength challenger must be integrated in a separate "
            "shadow production PR and pass canonical squad/epsilon stability checks before "
            "it can alter the live Apex fixture surface."
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
                "validated_vs_fallback": all_fallback_pass,
                "validated_vs_production_elo": bool(elo_h2h.get("pass", False)),
                "selected_config": report["selected_config"],
                "output": str(path),
            },
            indent=2,
        )
    )
    raise SystemExit(0 if production_candidate_ready else 2)


if __name__ == "__main__":
    main()
