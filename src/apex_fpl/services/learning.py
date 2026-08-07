from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from apex_fpl.models.backtest import calibrate_ensemble_weights, score_predictions


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


def build_learning_report(
    archive: pd.DataFrame,
    *,
    min_completed_gameweeks: int = 4,
    min_rows: int = 200,
) -> LearningReport:
    if archive.empty:
        return LearningReport(
            [], 0, 0, {}, {}, None, None,
            "No completed deadline forecasts exist yet. Learning starts only from genuine pre-deadline forecasts and official outcomes.",
        )

    data = archive.copy()
    data["gw"] = pd.to_numeric(data["gw"], errors="coerce")
    data["event_points"] = pd.to_numeric(data["event_points"], errors="coerce")
    completed = sorted(data.loc[data["event_points"].notna(), "gw"].dropna().astype(int).unique())
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
            except Exception as exc:
                candidate = {"status": "not_fit", "reason": str(exc)}

            # One-step walk-forward holdout: train without the latest GW, evaluate
            # the latest genuine deadline. This is deliberately stricter than
            # reporting only in-sample improvement.
            latest_gw = completed[-1]
            train = active[active["gw"] < latest_gw].copy()
            test = active[active["gw"] == latest_gw].copy()
            if len(train) >= min_rows and len(test) >= 20:
                usable = [
                    col
                    for col in expert_cols
                    if pd.to_numeric(train[col], errors="coerce").notna().mean() >= 0.80
                    and pd.to_numeric(test[col], errors="coerce").notna().mean() >= 0.80
                ]
                if len(usable) >= 2:
                    try:
                        fit = calibrate_ensemble_weights(
                            train,
                            usable,
                            actual_col="event_points",
                            min_rows=min_rows,
                        )
                        test["_calibrated"] = _weighted_prediction(test, usable, fit.weights)
                        calibrated = _metric_dict(test, "_calibrated")
                        baseline = _metric_dict(test, "xp") if "xp" in test.columns else {}
                        holdout = {
                            "gameweek": latest_gw,
                            "train_rows": len(train),
                            "test_rows": len(test),
                            "weights": fit.weights,
                            "calibrated_metrics": calibrated,
                            "current_ensemble_metrics": baseline,
                            "rmse_improvement_vs_current": (
                                float(baseline.get("rmse", np.nan) - calibrated["rmse"])
                                if baseline
                                else None
                            ),
                        }
                    except Exception as exc:
                        holdout = {"status": "not_fit", "reason": str(exc)}

    return LearningReport(
        completed_gameweeks=completed,
        rows=len(data),
        active_rows=len(active),
        expert_metrics=metrics,
        ensemble_metrics=ensemble_metrics,
        candidate_calibration=candidate,
        holdout_validation=holdout,
        note=(
            "Calibration is advisory until repeated walk-forward holdouts show stable out-of-sample improvement. "
            "Apex never fits against a post-deadline feature snapshot and never auto-promotes weights from one lucky Gameweek."
        ),
    )


def write_learning_report(report: LearningReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, default=str) + "\n", encoding="utf-8")
