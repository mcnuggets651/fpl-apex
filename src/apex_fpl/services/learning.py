from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex_fpl.models.backtest import (
    calibrate_ensemble_weights,
    gameweek_block_bootstrap,
    interval_diagnostics,
    score_predictions,
)


EXPERT_COLUMNS = ["apex_xp", "official_xp", "airsenal_xp", "market_xp"]


@dataclass(frozen=True)
class LearningReport:
    completed_gameweeks: list[int]
    rows: int
    active_rows: int
    expert_metrics: dict[str, dict[str, float]]
    ensemble_metrics: dict[str, float]
    candidate_calibration: dict[str, Any] | None
    holdout_validation: dict[str, Any] | None
    cohort_metrics: dict[str, Any]
    uncertainty_diagnostics: dict[str, Any]
    source_ablation: dict[str, Any]
    promotion_gate: dict[str, Any]
    note: str

    def to_dict(self) -> dict:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "completed_gameweeks": self.completed_gameweeks,
            "rows": self.rows,
            "active_rows": self.active_rows,
            "expert_metrics": self.expert_metrics,
            "ensemble_metrics": self.ensemble_metrics,
            "candidate_calibration": self.candidate_calibration,
            "holdout_validation": self.holdout_validation,
            "cohort_metrics": self.cohort_metrics,
            "uncertainty_diagnostics": self.uncertainty_diagnostics,
            "source_ablation": self.source_ablation,
            "promotion_gate": self.promotion_gate,
            "auto_promoted": False,
            "note": self.note,
        }


def aggregate_deadline_forecast(
    projections: pd.DataFrame,
    players: pd.DataFrame,
    gw: int,
    *,
    generated_at: str,
    snapshot_id: str,
    deadline_time: str | None = None,
) -> pd.DataFrame:
    """Create one immutable-calibration row per official player for a deadline.

    The projection table may contain two rows in a Double Gameweek. By this stage
    full-Gameweek external experts have already been allocated across fixture rows,
    so summing here reconstructs each expert's intended Gameweek total exactly once.
    """
    d = projections[projections["gw"] == int(gw)].copy()
    if d.empty:
        raise ValueError(f"no projection rows found for GW{gw}")
    value_cols = [
        col
        for col in [
            *EXPERT_COLUMNS,
            "xp",
            "risk_adjusted_xp",
            "projection_sd",
        ]
        if col in d.columns
    ]
    numeric = d[["player_id", *value_cols]].copy()
    for col in value_cols:
        numeric[col] = pd.to_numeric(numeric[col], errors="coerce")
    agg_map = {col: "sum" for col in value_cols}
    # Standard deviation is not additive. Keep a root-sum-square approximation for
    # diagnostic calibration rather than summing it like expected points.
    if "projection_sd" in agg_map:
        del agg_map["projection_sd"]
    out = numeric.groupby("player_id", as_index=False).agg(agg_map)
    if "projection_sd" in numeric.columns:
        rss = numeric.groupby("player_id")["projection_sd"].apply(
            lambda s: float(np.sqrt(np.nansum(np.square(pd.to_numeric(s, errors="coerce")))))
        )
        out["projection_sd"] = out["player_id"].map(rss)

    keep = [
        col
        for col in [
            "player_id",
            "web_name",
            "team_name",
            "position",
            "price",
            "expected_minutes",
            "appearance_probability",
            "minutes_confidence",
            "role_confidence",
        ]
        if col in players.columns
    ]
    out = out.merge(
        players[keep].drop_duplicates("player_id"),
        on="player_id",
        how="left",
        validate="one_to_one",
    )
    out.insert(1, "gw", int(gw))
    out["forecast_generated_at"] = str(generated_at)
    out["deadline_time"] = str(deadline_time or "")
    out["official_snapshot_id"] = str(snapshot_id)
    out["event_points"] = np.nan
    out["actuals_retrieved_at"] = ""
    return out.sort_values("player_id").reset_index(drop=True)


def parse_event_live_points(payload: dict[str, Any]) -> dict[int, float]:
    points: dict[int, float] = {}
    for row in payload.get("elements", []) if isinstance(payload, dict) else []:
        try:
            pid = int(row["id"])
            stats = row.get("stats") or {}
            points[pid] = float(stats.get("total_points", 0) or 0)
        except Exception:
            continue
    return points


def attach_actual_points(
    forecast: pd.DataFrame,
    points: dict[int, float],
    *,
    retrieved_at: str | None = None,
) -> pd.DataFrame:
    out = forecast.copy()
    out["event_points"] = out["player_id"].map(points)
    out["actuals_retrieved_at"] = retrieved_at or datetime.now(timezone.utc).isoformat()
    return out


def load_completed_archive(root: Path) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if not root.exists():
        return pd.DataFrame()
    for path in sorted(root.glob("gw*_forecast.csv")):
        try:
            frame = pd.read_csv(path)
        except Exception:
            continue
        if "event_points" not in frame.columns:
            continue
        if {"forecast_generated_at", "deadline_time"}.issubset(frame.columns):
            forecast_at = pd.to_datetime(frame["forecast_generated_at"], utc=True, errors="coerce")
            deadline_at = pd.to_datetime(frame["deadline_time"], utc=True, errors="coerce")
            if forecast_at.isna().any() or deadline_at.isna().any() or (forecast_at >= deadline_at).any():
                continue
        points = pd.to_numeric(frame["event_points"], errors="coerce")
        if points.notna().sum() == 0:
            continue
        frame["event_points"] = points
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _metric_dict(df: pd.DataFrame, prediction_col: str) -> dict[str, float]:
    metric = score_predictions(df, prediction_col=prediction_col, actual_col="event_points")
    return {key: float(value) for key, value in metric.__dict__.items()}


def _weighted_prediction(
    frame: pd.DataFrame,
    columns: list[str],
    weights: dict[str, float],
) -> pd.Series:
    x = frame[columns].apply(pd.to_numeric, errors="coerce")
    w = np.asarray([float(weights[col]) for col in columns], dtype=float)
    mask = x.notna().to_numpy(float)
    values = x.fillna(0.0).to_numpy(float)
    denom = mask @ w
    num = values @ w
    return pd.Series(
        np.where(denom > 1e-12, num / np.maximum(denom, 1e-12), np.nan),
        index=frame.index,
    )


def _cohort_metrics(frame: pd.DataFrame) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for cohort in ["position", "minutes_cohort"]:
        data = frame.copy()
        if cohort == "minutes_cohort":
            if "expected_minutes" not in data.columns:
                continue
            minutes = pd.to_numeric(data["expected_minutes"], errors="coerce")
            data[cohort] = pd.cut(
                minutes,
                bins=[-np.inf, 29.999, 59.999, 74.999, np.inf],
                labels=["under_30", "30_to_59", "60_to_74", "75_plus"],
            )
        if cohort not in data.columns:
            continue
        groups: dict[str, Any] = {}
        for value, group in data.groupby(cohort, observed=True):
            if len(group) < 10 or "xp" not in group.columns:
                continue
            groups[str(value)] = {"rows": int(len(group)), **_metric_dict(group, "xp")}
        if groups:
            output[cohort] = groups
    return output


def _ablation_report(
    frame: pd.DataFrame,
    expert_cols: list[str],
    weights: dict[str, float],
    *,
    min_rows: int,
) -> dict[str, Any]:
    if len(expert_cols) < 2:
        return {}
    full = frame.copy()
    full["_candidate"] = _weighted_prediction(full, expert_cols, weights)
    result: dict[str, Any] = {"all_sources": _metric_dict(full, "_candidate")}
    for removed in expert_cols:
        kept = [col for col in expert_cols if col != removed]
        try:
            refit = calibrate_ensemble_weights(
                frame, kept, actual_col="event_points", min_rows=min_rows
            )
        except (ValueError, RuntimeError):
            continue
        full["_ablated"] = _weighted_prediction(full, kept, refit.weights)
        metrics = _metric_dict(full, "_ablated")
        result[f"without_{removed}"] = {
            **metrics,
            "refit_weights": refit.weights,
            "rmse_change_vs_all": float(metrics["rmse"] - result["all_sources"]["rmse"]),
        }
    return result


def build_learning_report(
    archive: pd.DataFrame,
    *,
    min_completed_gameweeks: int = 4,
    min_rows: int = 200,
) -> LearningReport:
    if archive.empty:
        return LearningReport(
            [], 0, 0, {}, {}, None, None, {}, {}, {},
            {
                "status": "blocked_insufficient_history",
                "promote": False,
                "reasons": ["no completed genuine pre-deadline Gameweeks"],
            },
            "No completed deadline forecasts exist yet. Learning starts only from genuine pre-deadline forecasts and official outcomes.",
        )

    data = archive.copy()
    data["gw"] = pd.to_numeric(data["gw"], errors="coerce")
    data["event_points"] = pd.to_numeric(data["event_points"], errors="coerce")
    completed = [
        int(gw)
        for gw in sorted(
            data.loc[data["event_points"].notna(), "gw"].dropna().astype(int).unique()
        )
    ]
    active = data[data["event_points"].notna()].copy()
    if "expected_minutes" in active.columns:
        active = active[
            pd.to_numeric(active["expected_minutes"], errors="coerce").fillna(0) >= 15
        ].copy()

    metrics: dict[str, dict[str, float]] = {}
    for col in [*EXPERT_COLUMNS, "xp", "risk_adjusted_xp"]:
        if col in active.columns and pd.to_numeric(active[col], errors="coerce").notna().sum() >= 20:
            metrics[col] = _metric_dict(active, col)
    ensemble_metrics = metrics.get("xp", {})

    candidate = None
    holdout = None
    ablation: dict[str, Any] = {}
    if len(completed) >= min_completed_gameweeks and len(active) >= min_rows:
        expert_cols = [
            col
            for col in EXPERT_COLUMNS
            if col in active.columns
            and pd.to_numeric(active[col], errors="coerce").notna().mean() >= 0.80
        ]
        if len(expert_cols) >= 2:
            try:
                calibration = calibrate_ensemble_weights(
                    active,
                    expert_cols,
                    actual_col="event_points",
                    min_rows=min_rows,
                )
                candidate = {
                    "experts": expert_cols,
                    "weights": calibration.weights,
                    "rows": calibration.rows,
                    "rmse": calibration.rmse,
                    "equal_weight_rmse": calibration.equal_weight_rmse,
                    "improvement_vs_equal": calibration.improvement,
                }
                ablation = _ablation_report(
                    active, expert_cols, calibration.weights, min_rows=min_rows
                )
            except Exception as exc:
                candidate = {"status": "not_fit", "reason": str(exc)}

            # Expanding-window walk-forward: each test Gameweek is predicted only
            # by weights fitted on strictly earlier deadlines. Combining several
            # holdouts also permits a valid Gameweek-block uncertainty estimate.
            folds: list[pd.DataFrame] = []
            fold_meta: list[dict[str, Any]] = []
            for test_gw in completed:
                train = active[active["gw"] < test_gw].copy()
                test = active[active["gw"] == test_gw].copy()
                if len(train) < min_rows or len(test) < 20:
                    continue
                usable = [
                    col
                    for col in expert_cols
                    if pd.to_numeric(train[col], errors="coerce").notna().mean() >= 0.80
                    and pd.to_numeric(test[col], errors="coerce").notna().mean() >= 0.80
                ]
                if len(usable) < 2:
                    continue
                try:
                    fit = calibrate_ensemble_weights(
                        train,
                        usable,
                        actual_col="event_points",
                        min_rows=min_rows,
                    )
                except Exception:
                    continue
                test["_calibrated"] = _weighted_prediction(test, usable, fit.weights)
                folds.append(test)
                fold_meta.append(
                    {"gameweek": int(test_gw), "train_rows": len(train),
                     "test_rows": len(test), "weights": fit.weights}
                )
            if folds:
                walked = pd.concat(folds, ignore_index=True)
                calibrated = _metric_dict(walked, "_calibrated")
                baseline = _metric_dict(walked, "xp") if "xp" in walked.columns else {}
                holdout = {
                    "method": "expanding_window_gameweek_holdouts",
                    "folds": fold_meta,
                    "holdout_gameweeks": [row["gameweek"] for row in fold_meta],
                    "test_rows": len(walked),
                    "calibrated_metrics": calibrated,
                    "current_ensemble_metrics": baseline,
                    "rmse_improvement_vs_current": (
                        float(baseline.get("rmse", np.nan) - calibrated["rmse"])
                        if baseline else None
                    ),
                }
                try:
                    bootstrap = gameweek_block_bootstrap(
                        walked,
                        candidate_col="_calibrated",
                        baseline_col="xp",
                        samples=1000,
                    )
                    holdout["gameweek_block_bootstrap"] = bootstrap.__dict__
                except ValueError as exc:
                    holdout["gameweek_block_bootstrap"] = {
                        "status": "insufficient_blocks", "reason": str(exc)
                    }

    uncertainty: dict[str, Any] = {}
    if {"xp", "projection_sd", "event_points"}.issubset(active.columns):
        uncertainty = interval_diagnostics(active)

    cohort = _cohort_metrics(active)
    reasons: list[str] = []
    if len(completed) < 8:
        reasons.append(f"completed Gameweeks {len(completed)} < required 8")
    if len(active) < min_rows:
        reasons.append(f"active rows {len(active)} < required {min_rows}")
    if not holdout or holdout.get("status") == "not_fit":
        reasons.append("no valid chronological holdout")
    else:
        improvement = holdout.get("rmse_improvement_vs_current")
        if improvement is None or not np.isfinite(improvement) or improvement <= 0:
            reasons.append("candidate does not improve holdout RMSE")
        bootstrap = holdout.get("gameweek_block_bootstrap", {})
        if float(bootstrap.get("probability_improves", 0.0) or 0.0) < 0.80:
            reasons.append("Gameweek-block bootstrap confidence below 80%")
    if not ablation:
        reasons.append("leave-one-source-out ablation unavailable")
    if not cohort:
        reasons.append("position/minutes cohort diagnostics unavailable")
    if not uncertainty:
        reasons.append("predictive uncertainty diagnostics unavailable")
    promotion_gate = {
        "status": "eligible_for_separate_promotion_review" if not reasons else "blocked",
        "promote": False,
        "weights_changed": False,
        "reasons": reasons or ["evidence complete; production change requires a separate PR"],
        "minimum_completed_gameweeks": 8,
        "minimum_active_rows": int(min_rows),
    }

    return LearningReport(
        completed_gameweeks=completed,
        rows=len(data),
        active_rows=len(active),
        expert_metrics=metrics,
        ensemble_metrics=ensemble_metrics,
        candidate_calibration=candidate,
        holdout_validation=holdout,
        cohort_metrics=cohort,
        uncertainty_diagnostics=uncertainty,
        source_ablation=ablation,
        promotion_gate=promotion_gate,
        note=(
            "Calibration is advisory until repeated walk-forward holdouts show stable out-of-sample improvement. "
            "Apex never fits against a post-deadline feature snapshot and never auto-promotes weights from one lucky Gameweek."
        ),
    )


def write_learning_report(report: LearningReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, default=str) + "\n", encoding="utf-8")
