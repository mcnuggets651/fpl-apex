#!/usr/bin/env python3
"""No-hindsight validation for continuous cross-season rate shrinkage.

The resolver under test combines previous-season and current-season competitive
samples before shrinking toward a leave-one-out position prior. Hyperparameters
are refit from scratch; values from the old OR-based resolver are not reused.

xG/xA calibration: 2022/23 + 2023/24.
Untouched attacking holdouts: 2024/25 and 2025/26 independently.
DEFCON: blocked 2025/26 validation because equivalent older event history is
not available; this weaker evidence class is explicitly reported.
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
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.models.shrinkage import RateShrinkageConfig, shrink_player_rates
from apex_fpl.services.provenance import load_upstream_pins

RATE_FIELDS = {
    "xg90": "expected_goals_per_90",
    "xa90": "expected_assists_per_90",
    "defcon90": "defensive_contribution_per_90",
}
PREVIOUS_RATE_FIELDS = {
    "xg90": "previous_expected_goals_per_90",
    "xa90": "previous_expected_assists_per_90",
    "defcon90": "previous_defensive_contribution_per_90",
}
GRID = [90, 180, 360, 540, 720, 900, 1200, 1800, 2400]
BUCKETS = [
    ("lt270", 0.0, 270.0),
    ("270_900", 270.0, 900.0),
    ("900_1800", 900.0, 1800.0),
    ("gte1800", 1800.0, math.inf),
]
CALIBRATION_SEASONS = ("2022-23", "2023-24")
HOLDOUT_SEASONS = ("2024-25", "2025-26")
ALL_ATTACKING_SEASONS = (*CALIBRATION_SEASONS, *HOLDOUT_SEASONS)
POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _raw_url(ref: str, season: str, path: str) -> str:
    return f"https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/{ref}/data/{season}/{path}"


def _read_csv(url: str) -> pd.DataFrame:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def _vaastav_frame(season: str, ref: str) -> pd.DataFrame:
    events = _read_csv(_raw_url(ref, season, "gws/merged_gw.csv"))
    players = _read_csv(_raw_url(ref, season, "players_raw.csv"))
    required = {"element", "round", "minutes", "expected_goals", "expected_assists"}
    missing = required - set(events.columns)
    if missing:
        raise ValueError(f"vaastav {season} missing attacking fields: {sorted(missing)}")
    if not {"id", "code", "element_type"}.issubset(players.columns):
        raise ValueError(f"vaastav {season} players_raw lacks id/code/element_type")

    e = events[["element", "round", "minutes", "expected_goals", "expected_assists"]].copy()
    e["player_id"] = pd.to_numeric(e["element"], errors="coerce")
    e["gw"] = pd.to_numeric(e["round"], errors="coerce")
    for col in ("minutes", "expected_goals", "expected_assists"):
        e[col] = pd.to_numeric(e[col], errors="coerce").fillna(0.0)
    e = e.dropna(subset=["player_id", "gw"])
    e["player_id"] = e["player_id"].astype(int)
    e["gw"] = e["gw"].astype(int)
    e = (
        e.groupby(["player_id", "gw"], as_index=False)
        .agg(
            minutes_event=("minutes", "sum"),
            xg_event=("expected_goals", "sum"),
            xa_event=("expected_assists", "sum"),
        )
        .sort_values(["player_id", "gw"])
    )
    e["minutes"] = e.groupby("player_id")["minutes_event"].cumsum()
    e["cum_xg"] = e.groupby("player_id")["xg_event"].cumsum()
    e["cum_xa"] = e.groupby("player_id")["xa_event"].cumsum()
    e["expected_goals_per_90"] = np.where(e["minutes"] > 0, e["cum_xg"] * 90 / e["minutes"], np.nan)
    e["expected_assists_per_90"] = np.where(e["minutes"] > 0, e["cum_xa"] * 90 / e["minutes"], np.nan)

    identity = players[["id", "code", "element_type"]].copy()
    identity["player_id"] = pd.to_numeric(identity["id"], errors="coerce")
    identity["player_code"] = pd.to_numeric(identity["code"], errors="coerce")
    identity["position"] = pd.to_numeric(identity["element_type"], errors="coerce").map(POSITION_MAP)
    identity = identity.dropna(subset=["player_id", "player_code"]).drop_duplicates("player_id")
    identity[["player_id", "player_code"]] = identity[["player_id", "player_code"]].astype(int)
    out = e.merge(identity[["player_id", "player_code", "position"]], on="player_id", how="left", validate="many_to_one")
    if out.duplicated(["player_id", "gw"]).any():
        raise ValueError(f"duplicate player/GW after aggregation in {season}")
    if int(out["gw"].max()) < 38:
        raise ValueError(f"{season} is not a completed 38-GW season")
    out["season"] = season
    return out[[
        "season", "player_id", "player_code", "position", "gw", "minutes",
        "expected_goals_per_90", "expected_assists_per_90",
    ]].copy()


def _final_lookup(frame: pd.DataFrame) -> pd.DataFrame:
    final = frame.sort_values(["player_code", "gw"]).drop_duplicates("player_code", keep="last")
    return final[["player_code", "minutes", "expected_goals_per_90", "expected_assists_per_90"]].rename(
        columns={
            "minutes": "previous_minutes",
            "expected_goals_per_90": "previous_expected_goals_per_90",
            "expected_assists_per_90": "previous_expected_assists_per_90",
        }
    )


def _attach_previous(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    order = list(ALL_ATTACKING_SEASONS)
    result: dict[str, pd.DataFrame] = {}
    for idx, season in enumerate(order):
        current = frames[season].copy()
        if idx == 0:
            current["previous_minutes"] = 0.0
            current["previous_expected_goals_per_90"] = np.nan
            current["previous_expected_assists_per_90"] = np.nan
        else:
            previous = _final_lookup(frames[order[idx - 1]])
            current = current.merge(previous, on="player_code", how="left", validate="many_to_one")
            current["previous_minutes"] = pd.to_numeric(current["previous_minutes"], errors="coerce").fillna(0.0)
        result[season] = current
    return result


def _snapshot(frame: pd.DataFrame, gw: int) -> pd.DataFrame:
    return frame[frame["gw"] <= gw].sort_values(["player_id", "gw"]).drop_duplicates("player_id", keep="last")


def _examples(frame: pd.DataFrame, metric: str, window_gws: int = 4) -> pd.DataFrame:
    current_col = RATE_FIELDS[metric]
    previous_col = PREVIOUS_RATE_FIELDS[metric]
    if current_col not in frame.columns:
        return pd.DataFrame()
    max_gw = int(frame["gw"].max())
    rows: list[pd.DataFrame] = []
    for cutoff in range(6, max_gw - window_gws + 1, 4):
        before = _snapshot(frame, cutoff)
        after = _snapshot(frame, cutoff + window_gws)
        keep = ["player_id", "player_code", "position", "minutes", current_col]
        if "previous_minutes" in before.columns:
            keep.extend(["previous_minutes", previous_col])
        b = before[keep].rename(columns={"minutes": "minutes_before", current_col: "rate_before"})
        a = after[["player_id", "minutes", current_col]].rename(columns={"minutes": "minutes_after", current_col: "rate_after"})
        d = b.merge(a, on="player_id", how="inner", validate="one_to_one")
        if "previous_minutes" not in d.columns:
            d["previous_minutes"] = 0.0
            d[previous_col] = np.nan
        for col in ("minutes_before", "minutes_after", "rate_before", "rate_after", "previous_minutes", previous_col):
            d[col] = pd.to_numeric(d[col], errors="coerce")
        d["future_minutes"] = d["minutes_after"] - d["minutes_before"]
        before_total = d["rate_before"].fillna(0) * d["minutes_before"] / 90.0
        after_total = d["rate_after"].fillna(0) * d["minutes_after"] / 90.0
        d["actual_future_rate"] = np.where(
            d["future_minutes"] > 0,
            (after_total - before_total) * 90.0 / d["future_minutes"],
            np.nan,
        )
        prior_valid = (d["previous_minutes"] > 0) & d[previous_col].notna()
        current_valid = (d["minutes_before"] > 0) & d["rate_before"].notna()
        d["effective_minutes_before"] = d["previous_minutes"].where(prior_valid, 0.0) + d["minutes_before"].where(current_valid, 0.0)
        d["cutoff_gw"] = cutoff
        d["cluster_id"] = d["player_code"].astype("Int64").astype(str)
        d = d[
            (d["effective_minutes_before"] > 0)
            & (d["future_minutes"] >= 90)
            & d["actual_future_rate"].notna()
            & (d["actual_future_rate"] >= 0)
        ].copy()
        rows.append(d)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _tag(examples: pd.DataFrame, season: str, season_index: int) -> pd.DataFrame:
    if examples.empty:
        return examples
    out = examples.copy()
    out["season"] = season
    out["cutoff_gw"] = season_index * 100 + out["cutoff_gw"].astype(int)
    out["cluster_id"] = season + ":" + out["cluster_id"].astype(str)
    return out


def _predict(
    examples: pd.DataFrame,
    metric: str,
    k: float | dict[str, float],
) -> pd.DataFrame:
    if examples.empty:
        return examples
    current_col = RATE_FIELDS[metric]
    previous_col = PREVIOUS_RATE_FIELDS[metric]
    rows: list[pd.DataFrame] = []
    for _, group in examples.groupby("cutoff_gw", sort=True):
        players = pd.DataFrame({
            "player_id": group["player_id"].astype(int).to_numpy(),
            "position": group["position"].fillna("UNKNOWN").to_numpy(),
            "minutes": group["minutes_before"].to_numpy(float),
            "previous_minutes": group["previous_minutes"].fillna(0).to_numpy(float),
            "expected_goals_per_90": np.nan,
            "expected_assists_per_90": np.nan,
            "defensive_contribution_per_90": np.nan,
            "previous_expected_goals_per_90": np.nan,
            "previous_expected_assists_per_90": np.nan,
            "previous_defensive_contribution_per_90": np.nan,
        })
        players[current_col] = group["rate_before"].to_numpy(float)
        players[previous_col] = group[previous_col].to_numpy(float)
        cfg = RateShrinkageConfig(
            prior_minutes={
                "xg90": k if metric == "xg90" else 720.0,
                "xa90": k if metric == "xa90" else 720.0,
                "defcon90": k if metric == "defcon90" else 720.0,
            },
            min_group_players=5,
            min_group_minutes=900.0,
        )
        shrunk = shrink_player_rates(players, cfg)
        scored = group.copy()
        scored["raw_prediction"] = shrunk[f"raw_{metric}"].to_numpy(float)
        scored["shrunk_prediction"] = shrunk[f"shrunk_{metric}"].to_numpy(float)
        scored["effective_minutes_before"] = shrunk[f"{metric}_combined_effective_evidence_minutes"].to_numpy(float)
        scored["reliability"] = shrunk[f"{metric}_reliability"].to_numpy(float)
        rows.append(scored)
    return pd.concat(rows, ignore_index=True)


def _mse(frame: pd.DataFrame, pred: str) -> float:
    err = frame[pred].to_numpy(float) - frame["actual_future_rate"].to_numpy(float)
    return float(np.mean(err**2)) if len(err) else float("nan")


def _cluster_bootstrap(frame: pd.DataFrame, n: int = 3000, seed: int = 20260808) -> dict:
    if frame.empty:
        return {"n": 0, "clusters": 0, "mean_delta": None, "ci95_low": None, "ci95_high": None}
    f = frame.copy()
    f["delta"] = (f["shrunk_prediction"] - f["actual_future_rate"]) ** 2 - (f["raw_prediction"] - f["actual_future_rate"]) ** 2
    cluster_means = f.groupby("cluster_id")["delta"].mean().to_numpy(float)
    if len(cluster_means) < 8:
        return {"n": int(len(f)), "clusters": int(len(cluster_means)), "mean_delta": float(np.mean(cluster_means)) if len(cluster_means) else None, "ci95_low": None, "ci95_high": None}
    rng = np.random.default_rng(seed)
    means = np.empty(n, dtype=float)
    for i in range(n):
        sample = rng.integers(0, len(cluster_means), len(cluster_means))
        means[i] = float(np.mean(cluster_means[sample]))
    return {
        "n": int(len(f)),
        "clusters": int(len(cluster_means)),
        "mean_delta": float(np.mean(cluster_means)),
        "ci95_low": float(np.quantile(means, 0.025)),
        "ci95_high": float(np.quantile(means, 0.975)),
    }


def _metrics(frame: pd.DataFrame) -> dict:
    if frame.empty:
        return {"n": 0, "clusters": 0}
    raw = _mse(frame, "raw_prediction")
    shrunk = _mse(frame, "shrunk_prediction")
    result = {
        "n": int(len(frame)),
        "clusters": int(frame["cluster_id"].nunique()),
        "raw_rmse": math.sqrt(raw),
        "shrunk_rmse": math.sqrt(shrunk),
        "rmse_ratio": math.sqrt(shrunk) / math.sqrt(raw) if raw > 0 else None,
        "paired_cluster_mse_delta_bootstrap": _cluster_bootstrap(frame),
        "buckets": {},
    }
    for label, lo, hi in BUCKETS:
        b = frame[(frame["effective_minutes_before"] >= lo) & (frame["effective_minutes_before"] < hi)]
        if b.empty:
            result["buckets"][label] = {"n": 0, "clusters": 0}
            continue
        br = _mse(b, "raw_prediction")
        bs = _mse(b, "shrunk_prediction")
        result["buckets"][label] = {
            "n": int(len(b)),
            "clusters": int(b["cluster_id"].nunique()),
            "raw_rmse": math.sqrt(br),
            "shrunk_rmse": math.sqrt(bs),
            "rmse_ratio": math.sqrt(bs) / math.sqrt(br) if br > 0 else None,
            "paired_cluster_mse_delta_bootstrap": _cluster_bootstrap(b),
        }
    return result


def _gate(metrics: dict) -> dict:
    low = [metrics.get("buckets", {}).get("lt270", {}), metrics.get("buckets", {}).get("270_900", {})]
    available = [b for b in low if b.get("clusters", 0) >= 8]
    low_pass = bool(available) and all(
        b["paired_cluster_mse_delta_bootstrap"].get("ci95_high") is not None
        and b["paired_cluster_mse_delta_bootstrap"]["ci95_high"] < 0
        for b in available
    )
    overall_pass = metrics.get("shrunk_rmse", math.inf) <= metrics.get("raw_rmse", -math.inf)
    established = metrics.get("buckets", {}).get("gte1800", {})
    harm = False
    if established.get("clusters", 0) >= 8:
        ci = established["paired_cluster_mse_delta_bootstrap"]
        harm = ci.get("ci95_low") is not None and ci["ci95_low"] > 0
    return {
        "pass": bool(low_pass and overall_pass and not harm),
        "low_effective_evidence_bootstrap_improvement": low_pass,
        "overall_rmse_not_worse": overall_pass,
        "no_statistically_clear_established_player_harm": not harm,
    }


def _choose_k(train: pd.DataFrame, metric: str) -> tuple[int, list[dict]]:
    scores = []
    for k in GRID:
        scored = _predict(train, metric, float(k))
        scores.append({"prior_minutes": k, "train_mse": _mse(scored, "shrunk_prediction"), "train_n": int(len(scored))})
    valid = [s for s in scores if np.isfinite(s["train_mse"])]
    best = min(valid, key=lambda s: (s["train_mse"], s["prior_minutes"]))
    return int(best["prior_minutes"]), scores


def _choose_position_k(
    train: pd.DataFrame,
    metric: str,
    *,
    min_examples: int = 250,
    min_clusters: int = 40,
) -> tuple[dict[str, int], dict]:
    """Fit heterogeneous prior strength using calibration data only.

    Position groups already have different leave-one-out prior means. Allowing
    their prior variance (equivalent minutes) to differ avoids forcing the much
    noisier forward and midfielder attacking rates to share defender/GK
    reliability. Sparse groups retain the global calibration-only fallback.
    """
    global_k, global_scores = _choose_k(train, metric)
    selected: dict[str, int] = {"DEFAULT": global_k}
    by_position: dict[str, dict] = {}
    positions = sorted(
        str(position)
        for position in train["position"].dropna().astype(str).unique()
    )
    for position in positions:
        subset = train[train["position"].astype(str) == position].copy()
        clusters = int(subset["cluster_id"].nunique())
        if len(subset) < min_examples or clusters < min_clusters:
            selected[position] = global_k
            by_position[position] = {
                "selected_prior_minutes": global_k,
                "used_global_fallback": True,
                "train_n": int(len(subset)),
                "clusters": clusters,
                "grid_scores": [],
            }
            continue
        position_k, position_scores = _choose_k(subset, metric)
        selected[position] = position_k
        by_position[position] = {
            "selected_prior_minutes": position_k,
            "used_global_fallback": False,
            "train_n": int(len(subset)),
            "clusters": clusters,
            "grid_scores": position_scores,
        }
    return selected, {
        "global_fallback": {
            "selected_prior_minutes": global_k,
            "grid_scores": global_scores,
        },
        "by_position": by_position,
        "selection_data": "calibration seasons only",
        "min_examples": min_examples,
        "min_clusters": min_clusters,
    }


def _core_season_frame(client: FPLCoreClient, force: bool) -> pd.DataFrame:
    stats = client.playerstats(force=force).copy()
    players = client.players(force=force).copy()
    if "player_id" not in stats and "id" in stats:
        stats["player_id"] = pd.to_numeric(stats["id"], errors="coerce")
    if "player_id" not in players and "id" in players:
        players["player_id"] = pd.to_numeric(players["id"], errors="coerce")
    identity = players[["player_id", "position"]].drop_duplicates("player_id")
    stats["player_id"] = pd.to_numeric(stats["player_id"], errors="coerce")
    stats["gw"] = pd.to_numeric(stats["gw"], errors="coerce")
    stats["minutes"] = pd.to_numeric(stats["minutes"], errors="coerce").fillna(0)
    stats = stats.dropna(subset=["player_id", "gw"])
    stats[["player_id", "gw"]] = stats[["player_id", "gw"]].astype(int)
    out = stats.merge(identity, on="player_id", how="left", validate="many_to_one")
    out["player_code"] = out["player_id"]
    out["previous_minutes"] = 0.0
    out["previous_defensive_contribution_per_90"] = np.nan
    return out


def _defcon_examples(frame: pd.DataFrame, window_gws: int) -> pd.DataFrame:
    metric = "defcon90"
    current_col = RATE_FIELDS[metric]
    if current_col not in frame:
        return pd.DataFrame()
    max_gw = int(frame["gw"].max())
    rows = []
    for cutoff in range(6, max_gw - window_gws + 1, 4):
        before = frame[frame["gw"] <= cutoff].sort_values(["player_id", "gw"]).drop_duplicates("player_id", keep="last")
        after = frame[frame["gw"] <= cutoff + window_gws].sort_values(["player_id", "gw"]).drop_duplicates("player_id", keep="last")
        b = before[["player_id", "player_code", "position", "minutes", current_col, "previous_minutes", "previous_defensive_contribution_per_90"]].rename(columns={"minutes": "minutes_before", current_col: "rate_before"})
        a = after[["player_id", "minutes", current_col]].rename(columns={"minutes": "minutes_after", current_col: "rate_after"})
        d = b.merge(a, on="player_id", how="inner", validate="one_to_one")
        for col in ("minutes_before", "minutes_after", "rate_before", "rate_after"):
            d[col] = pd.to_numeric(d[col], errors="coerce")
        d["future_minutes"] = d["minutes_after"] - d["minutes_before"]
        before_total = d["rate_before"] * d["minutes_before"] / 90
        after_total = d["rate_after"] * d["minutes_after"] / 90
        d["actual_future_rate"] = np.where(d["future_minutes"] > 0, (after_total - before_total) * 90 / d["future_minutes"], np.nan)
        d["effective_minutes_before"] = d["minutes_before"]
        d["cutoff_gw"] = cutoff
        d["cluster_id"] = "2025-26:" + d["player_code"].astype(str)
        d = d[(d["effective_minutes_before"] > 0) & (d["future_minutes"] >= 90) & d["actual_future_rate"].notna() & (d["actual_future_rate"] >= 0)].copy()
        rows.append(d)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-gws", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", default="reports/shrinkage_validation.json")
    args = parser.parse_args()

    settings = load_settings()
    pins = load_upstream_pins(settings.upstreams_lock_path)
    vaastav_ref = str(pins.get("vaastav_history", {}).get("commit", ""))
    core_ref = str(pins.get("fpl_core_insights", {}).get("commit", "")) or "main"
    if not vaastav_ref:
        raise RuntimeError("pinned vaastav_history revision is required")

    raw_frames = {season: _vaastav_frame(season, vaastav_ref) for season in ALL_ATTACKING_SEASONS}
    frames = _attach_previous(raw_frames)
    report = {
        "contract": "apex-shrinkage-continuous-validation-v1",
        "resolver": "previous_plus_current_competitive_evidence_no_decay",
        "preseason_in_competitive_evidence": False,
        "bucket_basis": "combined_effective_evidence_minutes",
        "bootstrap_unit": "player_season_cluster",
        "grid_prior_minutes": GRID,
        "vaastav_ref": vaastav_ref,
        "fpl_core_ref": core_ref,
        "metrics": {},
    }
    all_pass = True

    for metric in ("xg90", "xa90"):
        training_parts = []
        for idx, season in enumerate(CALIBRATION_SEASONS, start=1):
            training_parts.append(_tag(_examples(frames[season], metric, args.window_gws), season, idx))
        train = pd.concat(training_parts, ignore_index=True)
        chosen_k, grid_scores = _choose_position_k(train, metric)
        holdouts = {}
        metric_pass = True
        for idx, season in enumerate(HOLDOUT_SEASONS, start=10):
            examples = _tag(_examples(frames[season], metric, args.window_gws), season, idx)
            scored = _predict(examples, metric, chosen_k)
            validation = _metrics(scored)
            gate = _gate(validation)
            holdouts[season] = {"test": validation, "promotion_gate": gate}
            metric_pass = metric_pass and bool(gate["pass"])
        report["metrics"][metric] = {
            "status": "validated" if metric_pass else "validation_failed",
            "chosen_prior_minutes": chosen_k["DEFAULT"],
            "chosen_prior_minutes_by_position": chosen_k,
            "train_n": int(len(train)),
            "grid_scores": grid_scores,
            "holdouts": holdouts,
            "promotion_gate": {"pass": bool(metric_pass), "requires_both_untouched_holdouts": True},
        }
        all_pass = all_pass and metric_pass

    core = _core_season_frame(FPLCoreClient(CachedHttp(settings.cache_dir), "2025-2026", ref=core_ref), args.force)
    de = _defcon_examples(core, args.window_gws)
    cutoffs = sorted(de["cutoff_gw"].unique()) if not de.empty else []
    if len(cutoffs) >= 4:
        split = max(2, int(len(cutoffs) * 0.6))
        split = min(split, len(cutoffs) - 2)
        train = de[de["cutoff_gw"].isin(cutoffs[:split])].copy()
        test = de[de["cutoff_gw"].isin(cutoffs[split:])].copy()
        chosen_k, grid_scores = _choose_position_k(train, "defcon90")
        scored = _predict(test, "defcon90", chosen_k)
        validation = _metrics(scored)
        gate = _gate(validation)
        report["metrics"]["defcon90"] = {
            "status": "validated" if gate["pass"] else "validation_failed",
            "evidence_design": "blocked_2025_26_no_previous_defcon_history_available",
            "chosen_prior_minutes": chosen_k["DEFAULT"],
            "chosen_prior_minutes_by_position": chosen_k,
            "train_cutoffs": cutoffs[:split],
            "test_cutoffs": cutoffs[split:],
            "grid_scores": grid_scores,
            "test": validation,
            "promotion_gate": gate,
            "limitation": "Previous-season DEFCON carry-forward cannot be independently validated from available equivalent historical fields.",
        }
        all_pass = all_pass and bool(gate["pass"])
    else:
        report["metrics"]["defcon90"] = {"status": "insufficient_history", "promotion_gate": {"pass": False}}
        all_pass = False

    report["promotion_ready"] = bool(all_pass)
    report["promotion_rule"] = (
        "Refit from scratch. xG/xA must pass both untouched holdouts using effective-evidence buckets, "
        "with statistically clear improvement in every available <900-minute bucket, no worse overall "
        "RMSE, and no statistically clear harm for >=1800 effective-minute players. DEFCON uses the "
        "same gate on a weaker blocked 2025/26 evidence class."
    )
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"promotion_ready": report["promotion_ready"], "output": str(path)}, indent=2))
    raise SystemExit(0 if report["promotion_ready"] else 2)


if __name__ == "__main__":
    main()
