#!/usr/bin/env python3
"""Multi-season no-hindsight validation for Apex player-rate shrinkage.

xG/xA equivalent-prior minutes are calibrated only on 2022/23 + 2023/24
vaastav event data, then evaluated independently on untouched 2024/25 and
2025/26 seasons. DEFCON remains a blocked temporal holdout within completed
2025/26 because equivalent older event history is not available.

The promotion criteria are intentionally unchanged: statistically clear
improvement in every available <900-minute bucket, no worse overall RMSE, and
no statistically clear harm to established >=1800-minute players.
"""
from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from apex_fpl.config import load_settings
from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.services.provenance import load_upstream_pins
from validate_shrinkage import (
    DEFAULT_GRID,
    _choose_k,
    _examples_for_metric,
    _metrics,
    _predict_examples,
    _promotion_gate,
    _season_frame,
)

TRAIN_SEASONS = ("2022-23", "2023-24")
HOLDOUT_SEASONS = ("2024-25", "2025-26")
ATTACKING_METRICS = ("xg90", "xa90")
POSITION_MAP = {1: "GK", 2: "DEF", 3: "MID", 4: "FWD"}


def _raw_url(ref: str, season: str, path: str) -> str:
    return (
        "https://raw.githubusercontent.com/vaastav/Fantasy-Premier-League/"
        f"{ref}/data/{season}/{path}"
    )


def _read_csv(url: str, *, timeout: int = 45) -> pd.DataFrame:
    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def _vaastav_season_frame(season: str, ref: str) -> pd.DataFrame:
    """Convert event-level vaastav data into cumulative per-player GW snapshots."""
    events = _read_csv(_raw_url(ref, season, "gws/merged_gw.csv"))
    players = _read_csv(_raw_url(ref, season, "players_raw.csv"))
    required_events = {"element", "round", "minutes", "expected_goals", "expected_assists"}
    missing = required_events - set(events.columns)
    if missing:
        raise ValueError(f"vaastav {season} merged_gw missing columns: {sorted(missing)}")
    if not {"id", "element_type"}.issubset(players.columns):
        raise ValueError(f"vaastav {season} players_raw lacks id/element_type")

    e = events[["element", "round", "minutes", "expected_goals", "expected_assists"]].copy()
    e["player_id"] = pd.to_numeric(e["element"], errors="coerce")
    e["gw"] = pd.to_numeric(e["round"], errors="coerce")
    for col in ("minutes", "expected_goals", "expected_assists"):
        e[col] = pd.to_numeric(e[col], errors="coerce").fillna(0.0)
    e = e.dropna(subset=["player_id", "gw"])
    e["player_id"] = e["player_id"].astype(int)
    e["gw"] = e["gw"].astype(int)

    # Double Gameweeks can contain multiple rows for one player/GW. Aggregate the
    # events first so each snapshot key is unique before constructing cumulative rates.
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
    e["expected_goals_per_90"] = np.where(
        e["minutes"] > 0, e["cum_xg"] * 90.0 / e["minutes"], np.nan
    )
    e["expected_assists_per_90"] = np.where(
        e["minutes"] > 0, e["cum_xa"] * 90.0 / e["minutes"], np.nan
    )

    identity = players[["id", "element_type"]].copy()
    identity["player_id"] = pd.to_numeric(identity["id"], errors="coerce")
    identity["position"] = pd.to_numeric(identity["element_type"], errors="coerce").map(POSITION_MAP)
    identity = identity.dropna(subset=["player_id"]).drop_duplicates("player_id")
    identity["player_id"] = identity["player_id"].astype(int)
    out = e.merge(
        identity[["player_id", "position"]],
        on="player_id",
        how="left",
        validate="many_to_one",
    )
    if out.duplicated(["player_id", "gw"]).any():
        raise ValueError(f"vaastav {season} contains duplicate player/GW snapshots after aggregation")
    if int(out["gw"].max()) < 38:
        raise ValueError(f"vaastav {season} is not a completed 38-GW season")
    return out[
        [
            "player_id",
            "gw",
            "minutes",
            "position",
            "expected_goals_per_90",
            "expected_assists_per_90",
        ]
    ].copy()


def _tag_cutoffs(examples: pd.DataFrame, season_index: int) -> pd.DataFrame:
    """Prevent priors from mixing players from different historical seasons."""
    if examples.empty:
        return examples
    out = examples.copy()
    out["source_gw"] = out["cutoff_gw"].astype(int)
    out["cutoff_gw"] = season_index * 100 + out["source_gw"]
    return out


def _metric_examples(
    frames: dict[str, pd.DataFrame],
    seasons: tuple[str, ...],
    metric: str,
    window_gws: int,
) -> pd.DataFrame:
    rows: list[pd.DataFrame] = []
    for idx, season in enumerate(seasons, start=1):
        examples = _examples_for_metric(frames[season], metric, window_gws=window_gws)
        examples = _tag_cutoffs(examples, idx)
        if not examples.empty:
            examples["season"] = season
            rows.append(examples)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def _defcon_validation(settings, ref: str, force: bool, window_gws: int) -> dict:
    stats = _season_frame(FPLCoreClient(CachedHttp(settings.cache_dir), "2025-2026", ref=ref), force)
    examples = _examples_for_metric(stats, "defcon90", window_gws=window_gws)
    cutoffs = sorted(examples["cutoff_gw"].unique()) if not examples.empty else []
    if len(cutoffs) < 4:
        return {
            "status": "insufficient_history",
            "evidence_design": "blocked_within_completed_2025_26",
            "promotion_gate": {"pass": False},
        }
    split = max(2, int(len(cutoffs) * 0.6))
    split = min(split, len(cutoffs) - 2)
    train_cutoffs = cutoffs[:split]
    test_cutoffs = cutoffs[split:]
    train = examples[examples["cutoff_gw"].isin(train_cutoffs)].copy()
    test = examples[examples["cutoff_gw"].isin(test_cutoffs)].copy()
    chosen_k, grid_scores = _choose_k(train, "defcon90", DEFAULT_GRID)
    scored = _predict_examples(test, "defcon90", chosen_k)
    validation = _metrics(scored)
    gate = _promotion_gate(validation)
    return {
        "status": "validated" if gate["pass"] else "validation_failed",
        "evidence_design": "blocked_within_completed_2025_26",
        "chosen_prior_minutes": chosen_k,
        "train_cutoffs": train_cutoffs,
        "test_cutoffs": test_cutoffs,
        "train_n": int(len(train)),
        "test_n": int(len(test)),
        "grid_scores": grid_scores,
        "test": validation,
        "promotion_gate": gate,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-gws", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--output", default="reports/shrinkage_validation.json")
    args = parser.parse_args()

    settings = load_settings()
    pins = load_upstream_pins(settings.upstreams_lock_path)
    vaastav_ref = str(pins.get("vaastav", {}).get("commit", ""))
    core_ref = str(pins.get("fpl_core_insights", {}).get("commit", "")) or "main"
    if not vaastav_ref:
        raise RuntimeError("pinned vaastav revision is required for multi-season shrinkage validation")

    seasons = (*TRAIN_SEASONS, *HOLDOUT_SEASONS)
    frames = {season: _vaastav_season_frame(season, vaastav_ref) for season in seasons}
    report: dict = {
        "contract": "apex-shrinkage-validation-v2",
        "evidence_design": "multi_season_calibration_plus_two_untouched_holdouts",
        "vaastav_ref": vaastav_ref,
        "fpl_core_ref": core_ref,
        "calibration_seasons": list(TRAIN_SEASONS),
        "holdout_seasons": list(HOLDOUT_SEASONS),
        "window_gws": args.window_gws,
        "grid_prior_minutes": DEFAULT_GRID,
        "metrics": {},
    }

    all_pass = True
    for metric in ATTACKING_METRICS:
        train = _metric_examples(frames, TRAIN_SEASONS, metric, args.window_gws)
        if train.empty:
            report["metrics"][metric] = {
                "status": "insufficient_history",
                "promotion_gate": {"pass": False},
            }
            all_pass = False
            continue
        chosen_k, grid_scores = _choose_k(train, metric, DEFAULT_GRID)
        holdouts: dict[str, dict] = {}
        metric_pass = True
        for idx, season in enumerate(HOLDOUT_SEASONS, start=10):
            examples = _examples_for_metric(frames[season], metric, window_gws=args.window_gws)
            examples = _tag_cutoffs(examples, idx)
            scored = _predict_examples(examples, metric, chosen_k)
            validation = _metrics(scored)
            gate = _promotion_gate(validation)
            holdouts[season] = {
                "n": int(len(scored)),
                "test": validation,
                "promotion_gate": gate,
            }
            metric_pass = metric_pass and bool(gate["pass"])
        report["metrics"][metric] = {
            "status": "validated" if metric_pass else "validation_failed",
            "evidence_design": "calibrate_2022_23_2023_24_validate_2024_25_and_2025_26",
            "chosen_prior_minutes": chosen_k,
            "train_n": int(len(train)),
            "grid_scores": grid_scores,
            "holdouts": holdouts,
            "promotion_gate": {
                "pass": bool(metric_pass),
                "requires_every_holdout_to_pass_unchanged_gate": True,
            },
        }
        all_pass = all_pass and bool(metric_pass)

    defcon = _defcon_validation(settings, core_ref, args.force, args.window_gws)
    report["metrics"]["defcon90"] = defcon
    all_pass = all_pass and bool(defcon.get("promotion_gate", {}).get("pass"))

    report["promotion_ready"] = bool(all_pass)
    report["promotion_rule"] = (
        "Unchanged gate: each metric needs statistically clear improvement in every available "
        "<900-minute bucket, no increase in overall held-out RMSE, and no statistically clear "
        "harm in the >=1800-minute bucket. xG/xA must pass independently in both untouched "
        "2024/25 and 2025/26 holdouts."
    )
    report["evidence_note"] = (
        "Historical xG/xA evidence comes from the repository-pinned vaastav revision. "
        "Hyperparameters never see either holdout season. DEFCON remains a later-season "
        "blocked temporal test because equivalent older event history is unavailable."
    )

    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({"promotion_ready": report["promotion_ready"], "output": str(path)}, indent=2))
    raise SystemExit(0 if report["promotion_ready"] else 2)


if __name__ == "__main__":
    main()
