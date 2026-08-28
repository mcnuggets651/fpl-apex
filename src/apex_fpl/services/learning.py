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
    score_predictions_by_gameweek,
)
from apex_fpl.services.projection_registry import PROJECTION_PROVIDERS, normalise_provider_key


PROVIDER_COLUMNS = {
    "airsenal": "airsenal_xp",
    "dastan": "dastan_xp",
    "openfpl": "openfpl_xp",
    "apex": "apex_shadow_xp",
}
BENCHMARK_COLUMNS = {"official_ep": "official_xp"}
MIN_PROVIDER_REVIEW_GAMEWEEKS = 8
MIN_ENSEMBLE_GAMEWEEKS = 16


@dataclass(frozen=True)
class LearningReport:
    completed_gameweeks: list[int]
    rows: int
    active_rows: int
    expert_metrics: dict[str, dict[str, Any]]
    provider_comparisons: dict[str, Any]
    ensemble_metrics: dict[str, Any]
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
            "provider_comparisons": self.provider_comparisons,
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
    """Create one immutable row per Official player for a pre-deadline Gameweek.

    Full-Gameweek provider xP values have already been allocated across DGW fixture
    rows by the projection layer, so summing reconstructs the intended provider total.
    Provider minutes/probability metadata is not additive and is retained once per GW.
    """
    d = projections[projections["gw"] == int(gw)].copy()
    if d.empty:
        raise ValueError(f"no projection rows found for GW{gw}")

    additive_cols = [
        col
        for col in [
            "apex_xp",
            "apex_shadow_xp",
            "official_xp",
            "airsenal_xp",
            "dastan_xp",
            "openfpl_xp",
            "market_xp",
            "production_xp",
            "xp",
            "risk_adjusted_xp",
            "provider_disagreement_sd",
            "provider_disagreement_spread",
        ]
        if col in d.columns
    ]
    numeric = d[["player_id", *additive_cols]].copy()
    for col in additive_cols:
        numeric[col] = pd.to_numeric(numeric[col], errors="coerce")
    out = numeric.groupby("player_id", as_index=False).agg(
        {col: "sum" for col in additive_cols}
    )

    if "projection_sd" in d.columns:
        sd = pd.to_numeric(d["projection_sd"], errors="coerce")
        temp = pd.DataFrame({"player_id": d["player_id"], "projection_sd": sd})
        rss = temp.groupby("player_id")["projection_sd"].apply(
            lambda values: (
                float(np.sqrt(np.nansum(np.square(values))))
                if pd.to_numeric(values, errors="coerce").notna().any()
                else np.nan
            )
        )
        out["projection_sd"] = out["player_id"].map(rss)

    provider_metadata = [
        column
        for prefix in ("airsenal", "dastan", "openfpl")
        for column in (
            f"{prefix}_xmins",
            f"{prefix}_p_start",
            f"{prefix}_p_any",
            f"{prefix}_p60",
            f"{prefix}_confidence",
            f"{prefix}_sd",
        )
        if column in d.columns
    ]
    if provider_metadata:
        meta = d[["player_id", *provider_metadata]].copy()
        for column in provider_metadata:
            meta[column] = pd.to_numeric(meta[column], errors="coerce")
        meta = meta.groupby("player_id", as_index=False).agg(
            {column: "max" for column in provider_metadata}
        )
        out = out.merge(meta, on="player_id", how="left", validate="one_to_one")

    keep = [
        col
        for col in [
            "player_id",
            "web_name",
            "team_name",
            "position",
            "price",
            "expected_minutes",
            "start_probability",
            "appearance_probability",
            "minutes_60_plus_probability",
            "minutes_confidence",
            "role_confidence",
            "projection_provider",
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
    out["actual_minutes"] = np.nan
    out["actual_started"] = np.nan
    out["actual_60_plus"] = np.nan
    out["actuals_retrieved_at"] = ""
    return out.sort_values("player_id").reset_index(drop=True)


def parse_event_live_outcomes(payload: dict[str, Any]) -> dict[int, dict[str, float]]:
    outcomes: dict[int, dict[str, float]] = {}
    for row in payload.get("elements", []) if isinstance(payload, dict) else []:
        try:
            player_id = int(row["id"])
            stats = row.get("stats") or {}
            minutes = float(stats.get("minutes", 0) or 0)
            outcomes[player_id] = {
                "event_points": float(stats.get("total_points", 0) or 0),
                "actual_minutes": minutes,
                # FPL event-live does not expose XI starter identity directly. We keep
                # a conservative realised participation label and use 60+ separately.
                "actual_started": float(minutes > 0),
                "actual_60_plus": float(minutes >= 60),
            }
        except Exception:
            continue
    return outcomes


def parse_event_live_points(payload: dict[str, Any]) -> dict[int, float]:
    """Backward-compatible points-only helper."""
    return {
        player_id: values["event_points"]
        for player_id, values in parse_event_live_outcomes(payload).items()
    }


def attach_actual_outcomes(
    forecast: pd.DataFrame,
    outcomes: dict[int, dict[str, float]],
    *,
    retrieved_at: str | None = None,
) -> pd.DataFrame:
    out = forecast.copy()
    for column in ("event_points", "actual_minutes", "actual_started", "actual_60_plus"):
        out[column] = out["player_id"].map(
            {player_id: values.get(column) for player_id, values in outcomes.items()}
        )
    out["actuals_retrieved_at"] = retrieved_at or datetime.now(timezone.utc).isoformat()
    return out


def attach_actual_points(
    forecast: pd.DataFrame,
    points: dict[int, float],
    *,
    retrieved_at: str | None = None,
) -> pd.DataFrame:
    """Backward-compatible helper for tests/tools that only supply points."""
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


def _metric_dict(df: pd.DataFrame, prediction_col: str) -> dict[str, Any]:
    return score_predictions_by_gameweek(
        df,
        prediction_col=prediction_col,
        actual_col="event_points",
        block_col="gw",
    )


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
    """Use realised, post-event minutes for outcome cohorts; never predicted minutes."""
    output: dict[str, Any] = {}
    data = frame.copy()
    if "actual_minutes" in data.columns:
        actual_minutes = pd.to_numeric(data["actual_minutes"], errors="coerce")
        data["actual_minutes_cohort"] = pd.cut(
            actual_minutes,
            bins=[-0.001, 0.001, 59.999, np.inf],
            labels=["zero_minutes", "1_to_59", "60_plus"],
        )
    for cohort in ("position", "actual_minutes_cohort"):
        if cohort not in data.columns:
            continue
        groups: dict[str, Any] = {}
        for value, group in data.groupby(cohort, observed=True):
            if len(group) < 10:
                continue
            provider_metrics: dict[str, Any] = {}
            for column in [*PROVIDER_COLUMNS.values(), "xp"]:
                if column in group.columns and pd.to_numeric(group[column], errors="coerce").notna().sum() >= 10:
                    provider_metrics[column] = _metric_dict(group, column)
            if provider_metrics:
                groups[str(value)] = {"rows": int(len(group)), "providers": provider_metrics}
        if groups:
            output[cohort] = groups
    return output


def _provider_comparisons(
    frame: pd.DataFrame,
    incumbent_col: str,
) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    if incumbent_col not in frame.columns:
        return comparisons
    for provider_key, candidate_col in PROVIDER_COLUMNS.items():
        if candidate_col == incumbent_col or candidate_col not in frame.columns:
            continue
        paired = frame[["gw", "event_points", incumbent_col, candidate_col]].copy()
        for column in ("event_points", incumbent_col, candidate_col):
            paired[column] = pd.to_numeric(paired[column], errors="coerce")
        paired = paired.dropna()
        if len(paired) < 20:
            continue
        item: dict[str, Any] = {
            "candidate": candidate_col,
            "incumbent": incumbent_col,
            "paired_rows": int(len(paired)),
            "gameweeks": int(paired["gw"].nunique()),
            "candidate_metrics": _metric_dict(paired, candidate_col),
            "incumbent_metrics": _metric_dict(paired, incumbent_col),
        }
        if paired["gw"].nunique() >= 2:
            for metric in ("rmse", "mae"):
                bootstrap = gameweek_block_bootstrap(
                    paired,
                    candidate_col=candidate_col,
                    baseline_col=incumbent_col,
                    metric=metric,
                    samples=2000,
                )
                item[f"{metric}_gameweek_block_bootstrap"] = bootstrap.__dict__
        comparisons[provider_key] = item
    return comparisons


def _ablation_report(
    frame: pd.DataFrame,
    expert_cols: list[str],
    weights: dict[str, float],
    *,
    min_rows: int,
    prior_weights: dict[str, float],
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
                frame,
                kept,
                actual_col="event_points",
                min_rows=min_rows,
                ridge=0.10,
                block_col="gw",
                prior_weights={column: prior_weights.get(column, 0.0) for column in kept},
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
    champion_provider: str = "airsenal",
    min_completed_gameweeks: int = MIN_PROVIDER_REVIEW_GAMEWEEKS,
    min_ensemble_gameweeks: int = MIN_ENSEMBLE_GAMEWEEKS,
    min_rows: int = 200,
) -> LearningReport:
    champion = normalise_provider_key(champion_provider)
    incumbent_col = PROVIDER_COLUMNS.get(champion)
    if archive.empty:
        return LearningReport(
            [], 0, 0, {}, {}, {}, None, None, {}, {}, {},
            {
                "status": "blocked_insufficient_history",
                "promote": False,
                "reasons": ["no completed genuine pre-deadline Gameweeks"],
                "incumbent_provider": champion,
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
    # Provider competition uses the complete realised Official-player population.
    # Never filter by predicted expected minutes, start probabilities, or any provider
    # feature before scoring; those forecasts are part of what the contest must judge.
    active = data[data["event_points"].notna()].copy()

    metrics: dict[str, dict[str, Any]] = {}
    for col in [*PROVIDER_COLUMNS.values(), *BENCHMARK_COLUMNS.values(), "xp", "risk_adjusted_xp"]:
        if col in active.columns and pd.to_numeric(active[col], errors="coerce").notna().sum() >= 20:
            metrics[col] = _metric_dict(active, col)
    ensemble_metrics = metrics.get("xp", {})
    comparisons = _provider_comparisons(active, incumbent_col) if incumbent_col else {}

    candidate = None
    holdout = None
    ablation: dict[str, Any] = {}
    if len(completed) >= min_ensemble_gameweeks and len(active) >= min_rows and incumbent_col:
        expert_cols = [
            col
            for col in PROVIDER_COLUMNS.values()
            if col in active.columns
            and pd.to_numeric(active[col], errors="coerce").notna().mean() >= 0.80
        ]
        if incumbent_col in expert_cols and len(expert_cols) >= 2:
            prior = {column: float(column == incumbent_col) for column in expert_cols}
            try:
                calibration = calibrate_ensemble_weights(
                    active,
                    expert_cols,
                    actual_col="event_points",
                    min_rows=min_rows,
                    ridge=0.10,
                    block_col="gw",
                    prior_weights=prior,
                )
                candidate = {
                    "experts": expert_cols,
                    "weights": calibration.weights,
                    "rows": calibration.rows,
                    "rmse": calibration.rmse,
                    "equal_weight_rmse": calibration.equal_weight_rmse,
                    "improvement_vs_equal": calibration.improvement,
                    "regularisation_prior": "incumbent_champion",
                    "incumbent_column": incumbent_col,
                }
                ablation = _ablation_report(
                    active,
                    expert_cols,
                    calibration.weights,
                    min_rows=min_rows,
                    prior_weights=prior,
                )
            except Exception as exc:
                candidate = {"status": "not_fit", "reason": str(exc)}

            # Expanding-window holdouts begin only after the training side already has
            # the minimum independent Gameweek count required for ensemble learning.
            folds: list[pd.DataFrame] = []
            fold_meta: list[dict[str, Any]] = []
            for test_gw in completed:
                train = active[active["gw"] < test_gw].copy()
                test = active[active["gw"] == test_gw].copy()
                if train["gw"].nunique() < min_ensemble_gameweeks or len(train) < min_rows or len(test) < 20:
                    continue
                usable = [
                    col
                    for col in expert_cols
                    if pd.to_numeric(train[col], errors="coerce").notna().mean() >= 0.80
                    and pd.to_numeric(test[col], errors="coerce").notna().mean() >= 0.80
                ]
                if incumbent_col not in usable or len(usable) < 2:
                    continue
                prior_fold = {column: float(column == incumbent_col) for column in usable}
                try:
                    fit = calibrate_ensemble_weights(
                        train,
                        usable,
                        actual_col="event_points",
                        min_rows=min_rows,
                        ridge=0.10,
                        block_col="gw",
                        prior_weights=prior_fold,
                    )
                except Exception:
                    continue
                test["_calibrated"] = _weighted_prediction(test, usable, fit.weights)
                folds.append(test)
                fold_meta.append(
                    {
                        "gameweek": int(test_gw),
                        "train_gameweeks": int(train["gw"].nunique()),
                        "train_rows": len(train),
                        "test_rows": len(test),
                        "weights": fit.weights,
                    }
                )
            if folds:
                walked = pd.concat(folds, ignore_index=True)
                calibrated = _metric_dict(walked, "_calibrated")
                baseline = _metric_dict(walked, incumbent_col)
                holdout = {
                    "method": "expanding_window_gameweek_holdouts",
                    "folds": fold_meta,
                    "holdout_gameweeks": [row["gameweek"] for row in fold_meta],
                    "test_rows": len(walked),
                    "calibrated_metrics": calibrated,
                    "incumbent_metrics": baseline,
                    "rmse_improvement_vs_incumbent": float(
                        baseline["rmse"] - calibrated["rmse"]
                    ),
                }
                try:
                    bootstrap = gameweek_block_bootstrap(
                        walked,
                        candidate_col="_calibrated",
                        baseline_col=incumbent_col,
                        samples=2000,
                    )
                    holdout["gameweek_block_bootstrap"] = bootstrap.__dict__
                except ValueError as exc:
                    holdout["gameweek_block_bootstrap"] = {
                        "status": "insufficient_blocks",
                        "reason": str(exc),
                    }

    uncertainty: dict[str, Any] = {}
    if {"xp", "projection_sd", "event_points"}.issubset(active.columns):
        try:
            uncertainty = interval_diagnostics(active)
        except ValueError:
            uncertainty = {}

    cohort = _cohort_metrics(active)
    reasons: list[str] = []
    if len(completed) < min_completed_gameweeks:
        reasons.append(
            f"completed Gameweeks {len(completed)} < provider-review minimum {min_completed_gameweeks}"
        )
    if not comparisons:
        reasons.append("no paired challenger-versus-incumbent evaluation available")
    ensemble_reasons: list[str] = []
    if len(completed) < min_ensemble_gameweeks:
        ensemble_reasons.append(
            f"completed Gameweeks {len(completed)} < ensemble-learning minimum {min_ensemble_gameweeks}"
        )
    if len(active) < min_rows:
        ensemble_reasons.append(f"rows {len(active)} < minimum {min_rows}")
    if not holdout:
        ensemble_reasons.append("no valid chronological ensemble holdout")
    else:
        improvement = holdout.get("rmse_improvement_vs_incumbent")
        if improvement is None or not np.isfinite(improvement) or improvement <= 0:
            ensemble_reasons.append("candidate ensemble does not improve incumbent holdout RMSE")
        bootstrap = holdout.get("gameweek_block_bootstrap", {})
        if float(bootstrap.get("probability_improves", 0.0) or 0.0) < 0.90:
            ensemble_reasons.append("Gameweek-block bootstrap confidence below 90%")
        calibrated = holdout.get("calibrated_metrics", {})
        incumbent = holdout.get("incumbent_metrics", {})
        for metric in ("rank_correlation", "ndcg_at_10"):
            candidate_value = calibrated.get(metric)
            incumbent_value = incumbent.get(metric)
            if (
                candidate_value is not None
                and incumbent_value is not None
                and np.isfinite(candidate_value)
                and np.isfinite(incumbent_value)
                and candidate_value + 1e-12 < incumbent_value
            ):
                ensemble_reasons.append(
                    f"candidate ensemble degrades holdout {metric} versus incumbent"
                )

    promotion_gate = {
        "status": "review_eligible" if not reasons else "blocked",
        "promote": False,
        "weights_changed": False,
        "incumbent_provider": champion,
        "provider_review": {
            "eligible": not reasons,
            "minimum_completed_gameweeks": int(min_completed_gameweeks),
            "reasons": reasons or ["paired evidence available; any champion change requires reviewed promotion"],
        },
        "ensemble_review": {
            "eligible": not ensemble_reasons,
            "minimum_completed_gameweeks": int(min_ensemble_gameweeks),
            "minimum_rows": int(min_rows),
            "reasons": ensemble_reasons or ["ensemble evidence complete; production change requires a separate reviewed promotion"],
        },
    }

    return LearningReport(
        completed_gameweeks=completed,
        rows=len(data),
        active_rows=len(active),
        expert_metrics=metrics,
        provider_comparisons=comparisons,
        ensemble_metrics=ensemble_metrics,
        candidate_calibration=candidate,
        holdout_validation=holdout,
        cohort_metrics=cohort,
        uncertainty_diagnostics=uncertainty,
        source_ablation=ablation,
        promotion_gate=promotion_gate,
        note=(
            "Provider scoring uses the complete realised Official-player population; predicted minutes never filter the contest. "
            "Ranks are scored inside each Gameweek, challenger comparisons use identical paired rows, and uncertainty is block-resampled by Gameweek. "
            "Champion promotion and ensemble promotion are reviewed operations; Apex never auto-promotes from one lucky Gameweek."
        ),
    )


def write_learning_report(report: LearningReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2, default=str) + "\n", encoding="utf-8")
