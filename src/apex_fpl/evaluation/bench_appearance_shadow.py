from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.evaluation.historical_minutes_preseason import (
    GitCoreReader,
    audit_historical_season,
    load_source_manifest,
)


def _brier(probability: pd.Series, outcome: pd.Series) -> float:
    p = pd.to_numeric(probability, errors="coerce")
    y = pd.to_numeric(outcome, errors="coerce")
    mask = p.notna() & y.notna()
    return float(np.mean(np.square(p[mask] - y[mask]))) if mask.any() else float("nan")


def _ece(probability: pd.Series, outcome: pd.Series, bins: int = 10) -> float:
    p = pd.to_numeric(probability, errors="coerce")
    y = pd.to_numeric(outcome, errors="coerce")
    mask = p.notna() & y.notna()
    p = p[mask].clip(0, 1)
    y = y[mask]
    if p.empty:
        return float("nan")
    edges = np.linspace(0, 1, bins + 1)
    labels = np.minimum(np.digitize(p.to_numpy(), edges[1:-1]), bins - 1)
    error = 0.0
    for idx in range(bins):
        use = labels == idx
        if not np.any(use):
            continue
        error += (np.sum(use) / len(p)) * abs(
            float(p.iloc[use].mean()) - float(y.iloc[use].mean())
        )
    return float(error)


def score_bench_appearance_shadow(scored: pd.DataFrame) -> dict:
    """Evaluate only substitute propensity; incumbent start/xMins remain fixed."""

    frame = scored.copy()
    availability = pd.to_numeric(
        frame["availability_probability"], errors="coerce"
    ).fillna(1).clip(0, 1)
    incumbent_start = pd.to_numeric(
        frame["incumbent_start_probability"], errors="coerce"
    ).fillna(0).clip(0, 1)
    role_start = pd.Series(
        np.where(availability > 0, incumbent_start / availability, 0.0),
        index=frame.index,
    ).clip(0, 1)
    role_bench = pd.to_numeric(
        frame["challenger_role_bench_probability"], errors="coerce"
    ).fillna(0.35).clip(0, 1)

    frame["bench_only_appearance_probability"] = (
        (role_start + (1 - role_start) * role_bench) * availability
    ).clip(0, 1)
    frame["bench_only_bench_appearance_probability"] = (
        role_bench * availability
    ).clip(0, 1)

    nonstarters = frame["actual_start"].eq(0)
    incumbent = {
        "appearance_brier": _brier(
            frame["incumbent_appearance_probability"], frame["actual_appearance"]
        ),
        "appearance_calibration_ece": _ece(
            frame["incumbent_appearance_probability"], frame["actual_appearance"]
        ),
        "bench_appearance_brier": _brier(
            frame.loc[nonstarters, "incumbent_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
        "bench_appearance_calibration_ece": _ece(
            frame.loc[nonstarters, "incumbent_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
    }
    shadow = {
        "appearance_brier": _brier(
            frame["bench_only_appearance_probability"], frame["actual_appearance"]
        ),
        "appearance_calibration_ece": _ece(
            frame["bench_only_appearance_probability"], frame["actual_appearance"]
        ),
        "bench_appearance_brier": _brier(
            frame.loc[nonstarters, "bench_only_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
        "bench_appearance_calibration_ece": _ece(
            frame.loc[nonstarters, "bench_only_bench_appearance_probability"],
            frame.loc[nonstarters, "actual_bench_appearance"],
        ),
    }
    return {
        "rows": int(len(frame)),
        "players": int(frame["player_id"].nunique()),
        "incumbent": incumbent,
        "bench_only_shadow": shadow,
        "delta_shadow_minus_incumbent": {
            key: float(shadow[key] - incumbent[key]) for key in incumbent
        },
        "start_probability_changed": False,
        "expected_minutes_changed": False,
    }


def run_bench_appearance_shadow(core_root: Path, manifest_path: Path) -> dict:
    sources, minimum = load_source_manifest(manifest_path)
    reader = GitCoreReader(core_root)
    frames = []
    seasons = []
    for source in sources:
        _, scored = audit_historical_season(reader, source)
        scored["season"] = source.season
        frames.append(scored)
        season_result = {
            "season": source.season,
            "metrics": score_bench_appearance_shadow(scored),
            "cohorts": {},
        }
        for cohort in [
            "established_returning_starter",
            "rotation_prior",
            "repeated_preseason_starter",
            "cameo_only",
            "no_prior_role",
        ]:
            subset = scored[scored[cohort].fillna(False)]
            if not subset.empty:
                season_result["cohorts"][cohort] = score_bench_appearance_shadow(subset)
        seasons.append(season_result)

    combined = (
        score_bench_appearance_shadow(pd.concat(frames, ignore_index=True))
        if frames
        else {}
    )
    deltas = combined.get("delta_shadow_minus_incumbent", {})
    improves_all = bool(deltas) and all(value < 0 for value in deltas.values())
    blockers = []
    if len(seasons) < minimum:
        blockers.append(
            f"only {len(seasons)} independent preseason season(s) available; "
            f"{minimum} required for production promotion"
        )
    return {
        "contract": "apex-bench-appearance-shadow-v1",
        "shadow_result": (
            "bench_only_improves_all_appearance_metrics"
            if improves_all
            else "bench_only_mixed_or_worse"
        ),
        "promotion_allowed": False,
        "blockers": blockers
        + [
            "shadow audit only; production start probability and expected minutes are unchanged"
        ],
        "combined_metrics": combined,
        "seasons": seasons,
    }
