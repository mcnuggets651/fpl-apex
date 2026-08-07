from __future__ import annotations

import numpy as np
import pandas as pd


def availability_probability(row: pd.Series) -> float:
    status = str(row.get("status", "a"))
    chance = row.get("chance_of_playing_next_round")
    if pd.notna(chance):
        return float(np.clip(float(chance) / 100.0, 0.0, 1.0))
    return {"a": 1.0, "d": 0.75, "i": 0.05, "s": 0.0, "u": 0.1}.get(status, 0.85)


def _series(df: pd.DataFrame, col: str, default: float) -> pd.Series:
    src = df[col] if col in df.columns else pd.Series(default, index=df.index)
    return pd.to_numeric(src, errors="coerce").fillna(default)


def expected_minutes(df: pd.DataFrame) -> pd.Series:
    mins = _series(df, "minutes", 0)
    starts = _series(df, "starts", 0)
    starts90 = _series(df, "starts_per_90", 0)
    pre_mins = _series(df, "preseason_minutes", 0)
    pre_starts = _series(df, "preseason_starts", 0)
    pre_apps = _series(df, "preseason_appearances", 0)

    # Established-season signal where available.
    avg_if_started = np.where(starts > 0, np.clip(mins / np.maximum(starts, 1), 45, 90), 65)
    if starts90.max() > 0:
        historic_start = np.clip(starts90 / max(float(starts90.max()), 1.0), 0.25, 1.0)
    else:
        historic_start = pd.Series(0.65, index=df.index)

    # Preseason signal is especially valuable before GW1.
    pre_start_rate = np.where(pre_apps > 0, np.clip(pre_starts / np.maximum(pre_apps, 1), 0, 1), 0.5)
    pre_avg_minutes = np.where(pre_apps > 0, np.clip(pre_mins / np.maximum(pre_apps, 1), 0, 90), 55)
    preseason_signal = 0.60 * (90 * pre_start_rate) + 0.40 * pre_avg_minutes

    historic_signal = 0.60 * avg_if_started + 0.40 * (90 * historic_start)
    has_preseason = pre_apps > 0
    base = np.where(has_preseason, 0.58 * preseason_signal + 0.42 * historic_signal, historic_signal)

    avail = df.apply(availability_probability, axis=1)
    manual = _series(df, "availability_multiplier", 1.0)
    news = _series(df, "news_multiplier", 1.0)
    rotation = np.clip(_series(df, "rotation_risk", 0.0), 0, 1)
    injury = np.clip(_series(df, "injury_risk", 0.0), 0, 1)
    transfer = np.clip(_series(df, "transfer_risk", 0.0), 0, 1)
    start_probability = _series(df, "start_probability", np.nan)
    override = _series(df, "expected_minutes_override", np.nan)
    context_risk = np.clip(1.0 - (0.48 * rotation + 0.34 * injury + 0.18 * transfer), 0.05, 1.0)
    start_factor = np.where(np.isfinite(start_probability), np.clip(0.45 + 0.70 * start_probability, 0.45, 1.08), 1.0)
    result = base * avail * manual * news * context_risk * start_factor
    result = np.where(np.isfinite(override), override * avail * manual * news, result)
    # Headline-derived news is advisory and should never override an official
    # zero/near-zero availability flag. Multipliers therefore only reduce the
    # already official-aware minutes expectation.
    return pd.Series(np.clip(result, 0, 90), index=df.index, name="expected_minutes")
