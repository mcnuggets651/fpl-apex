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


def minutes_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Estimate minutes plus explicit start/appearance probabilities and confidence.

    This is intentionally conservative before enough 2026/27 observations exist:
    preseason contributes, but cannot fully erase established-season context.
    Official availability is applied before any lower-authority news/manual signal.
    """
    mins = _series(df, "minutes", 0)
    starts = _series(df, "starts", 0)
    starts90 = _series(df, "starts_per_90", 0)
    pre_mins = _series(df, "preseason_minutes", 0)
    pre_starts = _series(df, "preseason_starts", 0)
    pre_apps = _series(df, "preseason_appearances", 0)

    avg_if_started = np.where(starts > 0, np.clip(mins / np.maximum(starts, 1), 45, 90), 65)
    if float(starts90.max()) > 0:
        hist_start_prob = np.clip(starts90 / max(float(starts90.max()), 1.0), 0.20, 0.98)
    elif float(starts.max()) > 0:
        hist_start_prob = np.clip(starts / max(float(starts.max()), 1.0), 0.20, 0.98)
    else:
        hist_start_prob = pd.Series(0.62, index=df.index)

    pre_start_prob = np.where(pre_apps > 0, np.clip(pre_starts / np.maximum(pre_apps, 1), 0, 1), 0.50)
    pre_avg_minutes = np.where(pre_apps > 0, np.clip(pre_mins / np.maximum(pre_apps, 1), 0, 90), 55)
    preseason_signal = 0.60 * (90 * pre_start_prob) + 0.40 * pre_avg_minutes
    historic_signal = 0.60 * avg_if_started + 0.40 * (90 * hist_start_prob)
    has_preseason = pre_apps > 0
    base_minutes = np.where(has_preseason, 0.58 * preseason_signal + 0.42 * historic_signal, historic_signal)
    base_start = np.where(has_preseason, 0.58 * pre_start_prob + 0.42 * hist_start_prob, hist_start_prob)

    avail = df.apply(availability_probability, axis=1).astype(float)
    manual = _series(df, "availability_multiplier", 1.0).clip(0, 1)
    news = _series(df, "news_multiplier", 1.0).clip(0, 1)
    availability = np.minimum(np.minimum(avail, manual), news)

    expected = np.clip(base_minutes * availability, 0, 90)
    start = np.clip(np.asarray(base_start, dtype=float) * availability, 0, 1)
    # A non-starter can still appear from the bench. The coefficient is deliberately
    # below 1 because substitute usage is uncertain rather than guaranteed.
    appearance = np.clip(start + (1 - start) * 0.52 * availability, start, 1)
    conditional_60 = 1.0 / (1.0 + np.exp(-(np.asarray(expected, dtype=float) - 58.0) / 8.0))
    p60 = np.minimum(appearance, np.clip(0.15 * appearance + 0.85 * conditional_60 * start, 0, 1))
    p80 = np.minimum(p60, np.clip((np.asarray(expected, dtype=float) - 45) / 40, 0, 1) * start)

    historic_evidence = np.clip((mins / 900.0) + (starts / 10.0), 0, 1)
    preseason_evidence = np.clip(pre_apps / 4.0, 0, 1)
    availability_clarity = np.where(df.get("chance_of_playing_next_round", pd.Series(np.nan, index=df.index)).notna(), 0.95, 0.72)
    confidence = np.clip(
        0.35 + 0.28 * np.maximum(historic_evidence, preseason_evidence) + 0.22 * availability_clarity,
        0.35,
        0.95,
    )
    # Explicit news/manual overrides are useful evidence, but also signal that the
    # situation may be moving. They should not create false certainty.
    override_present = (manual < 0.999) | (news < 0.999)
    confidence = np.where(override_present, np.minimum(confidence, 0.82), confidence)

    return pd.DataFrame({
        "expected_minutes": expected,
        "start_probability": start,
        "appearance_probability": appearance,
        "minutes_60_plus_probability": p60,
        "minutes_80_plus_probability": p80,
        "minutes_confidence": confidence,
    }, index=df.index)


def expected_minutes(df: pd.DataFrame) -> pd.Series:
    return minutes_profile(df)["expected_minutes"]
