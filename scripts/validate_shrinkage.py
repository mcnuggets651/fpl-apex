#!/usr/bin/env python3
"""Calibrate and validate empirical-Bayes player-rate shrinkage without hindsight.

Hyperparameters are learned on an earlier completed season and evaluated on a
later held-out season. If a metric is unavailable in the training season (for
example a newly introduced DEFCON field), the script uses a blocked temporal
split within the held-out completed season and labels that weaker evidence
explicitly.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.config import load_settings
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.models.shrinkage import RateShrinkageConfig, shrink_player_rates
from apex_fpl.services.provenance import load_upstream_pins


RATE_FIELDS = {
    "xg90": "expected_goals_per_90",
    "xa90": "expected_assists_per_90",
    "defcon90": "defensive_contribution_per_90",
}
MINUTE_BUCKETS = [
    ("lt270", 0.0, 270.0),
    ("270_900", 270.0, 900.0),
    ("900_1800", 900.0, 1800.0),
    ("gte1800", 1800.0, math.inf),
]
DEFAULT_GRID = [90, 180, 360, 540, 720, 900, 1200, 1800]


def _season_frame(client: FPLCoreClient, force: bool) -> pd.DataFrame:
    stats = client.playerstats(force=force).copy()
    players = client.players(force=force).copy()
    if "player_id" not in stats.columns and "id" in stats.columns:
        stats["player_id"] = pd.to_numeric(stats["id"], errors="coerce")
    if "player_id" not in players.columns and "id" in players.columns:
        players["player_id"] = pd.to_numeric(players["id"], errors="coerce")
    if "position" not in players.columns:
        raise ValueError(f"{client.season} players.csv lacks position")
    identity = players[["player_id", "position"]].copy()
    identity["player_id"] = pd.to_numeric(identity["player_id"], errors="coerce")
    identity = identity.dropna(subset=["player_id"]).drop_duplicates("player_id")
    identity["player_id"] = identity["player_id"].astype(int)
    stats["player_id"] = pd.to_numeric(stats["player_id"], errors="coerce")
    stats["gw"] = pd.to_numeric(stats.get("gw"), errors="coerce")
    stats["minutes"] = pd.to_numeric(stats.get("minutes"), errors="coerce").fillna(0)
    stats = stats.dropna(subset=["player_id", "gw"])
    stats["player_id"] = stats["player_id"].astype(int)
    stats["gw"] = stats["gw"].astype(int)
    if stats.duplicated(["player_id", "gw"]).any():
        raise ValueError(f"{client.season} contains duplicate player/GW snapshots")
    return stats.merge(identity, on="player_id", how="left", validate="many_to_one")


def _snapshot(stats: pd.DataFrame, gw: int) -> pd.DataFrame:
    d = stats[stats["gw"] <= int(gw)].sort_values(["player_id", "gw"])
    return d.drop_duplicates("player_id", keep="last")


def _examples_for_metric(
    stats: pd.DataFrame,
    metric: str,
    *,
    window_gws: int = 4,
    cutoff_min: int = 6,
    cutoff_step: int = 4,
) -> pd.DataFrame:
    col = RATE_FIELDS[metric]
    if col not in stats.columns:
        return pd.DataFrame()
    max_gw = int(stats["gw"].max())
    rows: list[pd.DataFrame] = []
    for cutoff in range(cutoff_min, max_gw - window_gws + 1, cutoff_step):
        before = _snapshot(stats, cutoff)
        after = _snapshot(stats, cutoff + window_gws)
        keep = ["player_id", "position", "minutes", col]
        b = before[keep].rename(
            columns={"minutes": "minutes_before", col: "rate_before"}
        )
        a = after[["player_id", "minutes", col]].rename(
            columns={"minutes": "minutes_after", col: "rate_after"}
        )
        d = b.merge(a, on="player_id", how="inner", validate="one_to_one")
        for name in ["minutes_before", "minutes_after", "rate_before", "rate_after"]:
            d[name] = pd.to_numeric(d[name], errors="coerce")
        d["future_minutes"] = d["minutes_after"] - d["minutes_before"]
        before_total = d["rate_before"] * d["minutes_before"] / 90.0
        after_total = d["rate_after"] * d["minutes_after"] / 90.0
        d["actual_future_rate"] = np.where(
            d["future_minutes"] > 0,
            (after_total - before_total) * 90.0 / d["future_minutes"],
            np.nan,
        )
        d["cutoff_gw"] = cutoff
        d = d[
            (d["minutes_before"] > 0)
            & (d["future_minutes"] >= 90)
            & d["rate_before"].notna()
            & d["actual_future_rate"].notna()
            & (d["actual_future_rate"] >= 0)
        ].copy()
        rows.append(d)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _predict_examples(examples: pd.DataFrame, metric: str, prior_minutes: float) -> pd.DataFrame:
    if examples.empty:
        return examples
    predictions: list[pd.DataFrame] = []
    current_col = RATE_FIELDS[metric]
    for cutoff, group in examples.groupby("cutoff_gw", sort=True):
        players = pd.DataFrame(
            {
                "player_id": group["player_id"].astype(int).to_numpy(),
                "position": group["position"].fillna("UNKNOWN").to_numpy(),
                "minutes": group["minutes_before"].to_numpy(float),
                current_col: group["rate_before"].to_numpy(float),
                # Populate the other current metrics with NaN; only the requested
                # metric is scored in this calibration pass.
                "expected_goals_per_90": np.nan,
                "expected_assists_per_90": np.nan,
                "defensive_contribution_per_90": np.nan,
            }
        )
        players[current_col] = group["rate_before"].to_numpy(float)
        cfg = RateShrinkageConfig(
            prior_minutes={
                "xg90": prior_minutes if metric == "xg90" else 720.0,
                "xa90": prior_minutes if metric == "xa90" else 720.0,
                "defcon90": prior_minutes if metric == "defcon90" else 720.0,
            },
            min_group_players=5,
            min_group_minutes=900.0,
        )
        shrunk = shrink_player_rates(players, cfg)
        scored = group.copy()
        scored["raw_prediction"] = group["rate_before"].to_numpy(float)
        scored["shrunk_prediction"] = shrunk[f"shrunk_{metric}"].to_numpy(float)
        scored["prior_rate"] = shrunk[f"prior_{metric}"].to_numpy(float)
        scored["reliability"] = shrunk[f"{metric}_reliability"].to_numpy(float)
        predictions.append(scored)
    return pd.concat(predictions, ignore_index=True)


def _mse(frame: pd.DataFrame, prediction: str) -> float:
    err = frame[prediction].to_numpy(float) - frame["actual_future_rate"].to_numpy(float)
    return float(np.mean(err**2)) if len(err) else float("nan")


def _bootstrap_mse_delta(frame: pd.DataFrame, n: int = 2000, seed: int = 20260808) -> dict:
    if len(frame) < 8:
        return {"n": int(len(frame)), "mean_delta": None, "ci95_low": None, "ci95_high": None}
    raw_err = (frame["raw_prediction"] - frame["actual_future_rate"]).to_numpy(float) ** 2
    shrunk_err = (frame["shrunk_prediction"] - frame["actual_future_rate"]).to_numpy(float) ** 2
    delta = shrunk_err - raw_err
    rng = np.random.default_rng(seed)
    means = np.empty(n, dtype=float)
    for i in range(n):
        sample = rng.integers(0, len(delta), len(delta))
        means[i] = float(np.mean(delta[sample]))
    return {
        "n": int(len(frame)),
        "mean_delta": float(np.mean(delta)),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
    }


def _metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"n": 0}
    raw_mse = _mse(frame, "raw_prediction")
    shrunk_mse = _mse(frame, "shrunk_prediction")
    result = {
        "n": int(len(frame)),
        "raw_rmse": float(math.sqrt(raw_mse)),
        "shrunk_rmse": float(math.sqrt(shrunk_mse)),
        "rmse_ratio": float(math.sqrt(shrunk_mse) / math.sqrt(raw_mse)) if raw_mse > 0 else None,
        "paired_mse_delta_bootstrap": _bootstrap_mse_delta(frame),
        "buckets": {},
    }
    for label, lower, upper in MINUTE_BUCKETS:
        bucket = frame[(frame["minutes_before"] >= lower) & (frame["minutes_before"] < upper)]
        if bucket.empty:
            result["buckets"][label] = {"n": 0}
            continue
        b_raw = _mse(bucket, "raw_prediction")
        b_shrunk = _mse(bucket, "shrunk_prediction")
        result["buckets"][label] = {
            "n": int(len(bucket)),
            "raw_rmse": float(math.sqrt(b_raw)),
            "shrunk_rmse": float(math.sqrt(b_shrunk)),
            "rmse_ratio": float(math.sqrt(b_shrunk) / math.sqrt(b_raw)) if b_raw > 0 else None,
            "paired_mse_delta_bootstrap": _bootstrap_mse_delta(bucket),
        }
    return result


def _choose_k(train: pd.DataFrame, metric: str, grid: list[int]) -> tuple[int, list[dict]]:
    scores: list[dict] = []
    for k in grid:
        pred = _predict_examples(train, metric, float(k))
        mse = _mse(pred, "shrunk_prediction")
        scores.append({"prior_minutes": int(k), "train_mse": mse, "train_n": int(len(pred))})
    valid = [row for row in scores if np.isfinite(row["train_mse"])]
    if not valid:
        raise ValueError(f"no calibration examples available for {metric}")
    best = min(valid, key=lambda row: (row["train_mse"], row["prior_minutes"]))
    return int(best["prior_minutes"]), scores


def _promotion_gate(metrics: dict) -> dict:
    overall = metrics
    low_frames = [overall.get("buckets", {}).get("lt270", {}), overall.get("buckets", {}).get("270_900", {})]
    low_valid = [row for row in low_frames if row.get("n", 0) >= 8]
    low_improves = bool(low_valid) and all(
        row["paired_mse_delta_bootstrap"].get("ci95_high") is not None
        and row["paired_mse_delta_bootstrap"]["ci95_high"] < 0
        for row in low_valid
    )
    overall_not_worse = (
        overall.get("raw_rmse") is not None
        and overall.get("shrunk_rmse") is not None
        and overall["shrunk_rmse"] <= overall["raw_rmse"]
    )
    established = overall.get("buckets", {}).get("gte1800", {})
    established_harm = False
    if established.get("n", 0) >= 8:
        ci = established["paired_mse_delta_bootstrap"]
        established_harm = ci.get("ci95_low") is not None and ci["ci95_low"] > 0
    return {
        "pass": bool(low_improves and overall_not_worse and not established_harm),
        "low_minute_bootstrap_improvement": low_improves,
        "overall_rmse_not_worse": overall_not_worse,
        "no_statistically_clear_established_player_harm": not established_harm,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-season", default="2024-2025")
    parser.add_argument("--test-season", default="2025-2026")
    parser.add_argument("--window-gws", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", default="reports/shrinkage_validation.json")
    args = parser.parse_args()

    settings = load_settings()
    http = CachedHttp(settings.cache_dir)
    pins = load_upstream_pins(settings.upstreams_lock_path)
    ref = str(pins.get("fpl_core_insights", {}).get("commit", "")) or "main"
    train_stats = _season_frame(FPLCoreClient(http, args.train_season, ref=ref), args.force)
    test_stats = _season_frame(FPLCoreClient(http, args.test_season, ref=ref), args.force)

    report = {
        "contract": "apex-shrinkage-validation-v1",
        "train_season": args.train_season,
        "test_season": args.test_season,
        "window_gws": args.window_gws,
        "grid_prior_minutes": DEFAULT_GRID,
        "metrics": {},
    }
    all_pass = True
    for metric in RATE_FIELDS:
        train = _examples_for_metric(train_stats, metric, window_gws=args.window_gws)
        test = _examples_for_metric(test_stats, metric, window_gws=args.window_gws)
        evidence_design = "cross_season_holdout"
        if train.empty and not test.empty:
            # DEFCON or another newly introduced metric: use a blocked temporal
            # split inside the completed test season rather than pretending older
            # history exists. The later cutoffs remain untouched until evaluation.
            cutoffs = sorted(test["cutoff_gw"].unique())
            split = max(1, int(len(cutoffs) * 0.6))
            train_cutoffs = set(cutoffs[:split])
            test_cutoffs = set(cutoffs[split:])
            train = test[test["cutoff_gw"].isin(train_cutoffs)].copy()
            test = test[test["cutoff_gw"].isin(test_cutoffs)].copy()
            evidence_design = "blocked_within_season_holdout"
        if train.empty or test.empty:
            report["metrics"][metric] = {
                "status": "insufficient_history",
                "evidence_design": evidence_design,
                "train_n": int(len(train)),
                "test_n": int(len(test)),
                "promotion_gate": {"pass": False},
            }
            all_pass = False
            continue
        chosen_k, grid_scores = _choose_k(train, metric, DEFAULT_GRID)
        scored = _predict_examples(test, metric, chosen_k)
        validation = _metrics(scored)
        gate = _promotion_gate(validation)
        report["metrics"][metric] = {
            "status": "validated" if gate["pass"] else "validation_failed",
            "evidence_design": evidence_design,
            "chosen_prior_minutes": chosen_k,
            "grid_scores": grid_scores,
            "test": validation,
            "promotion_gate": gate,
        }
        all_pass = all_pass and bool(gate["pass"])

    report["promotion_ready"] = bool(all_pass)
    report["promotion_rule"] = (
        "Each metric needs statistically clear low-minute improvement, no increase in overall "
        "held-out RMSE, and no statistically clear harm in the >=1800-minute bucket."
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"promotion_ready": report["promotion_ready"], "output": str(path)}, indent=2))
    raise SystemExit(0 if report["promotion_ready"] else 2)


if __name__ == "__main__":
    main()
