from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.minute_states import minute_state_probabilities


def availability_probability(row: pd.Series) -> float:
    status = str(row.get("status", "a"))
    chance = row.get("chance_of_playing_next_round")
    if pd.notna(chance):
        return float(np.clip(float(chance) / 100.0, 0.0, 1.0))
    return {"a": 1.0, "d": 0.75, "i": 0.05, "s": 0.0, "u": 0.1}.get(status, 0.85)


def _series(df: pd.DataFrame, col: str, default: float) -> pd.Series:
    src = df[col] if col in df.columns else pd.Series(default, index=df.index)
    return pd.to_numeric(src, errors="coerce").fillna(default)


def _optional_series(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def minutes_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Estimate minutes plus explicit start/appearance probabilities and confidence.

    Preseason and verified team-news evidence can override stale historical roles
    when they are strong enough. Official availability remains the hard ceiling:
    upside evidence can raise a healthy player's role estimate, but cannot erase
    an injury, suspension or explicit negative availability signal.

    Expected minutes are an input to expected FPL points, not a standalone safety
    score. The returned mutually-exclusive minute states make threshold mechanics
    explicit without rewarding probability of 90 minutes for its own sake.
    """
    mins = _series(df, "minutes", 0)
    starts = _series(df, "starts", 0)
    starts90 = _series(df, "starts_per_90", 0)
    pre_mins = _series(df, "preseason_minutes", 0)
    pre_starts = _series(df, "preseason_starts", 0)
    pre_apps = _series(df, "preseason_appearances", 0)

    previous_start = _optional_series(df, "previous_start_probability")
    previous_minutes = _optional_series(df, "previous_minutes_per_match")
    team_matches = _series(df, "current_team_matches", 0)

    avg_if_started = np.where(starts > 0, np.clip(mins / np.maximum(starts, 1), 45, 90), 65)
    current_start = np.where(
        team_matches > 0,
        np.clip(starts / np.maximum(team_matches, 1), 0, 1),
        np.nan,
    )
    current_minutes = np.where(
        team_matches > 0,
        np.clip(mins / np.maximum(team_matches, 1), 0, 90),
        np.nan,
    )
    current_weight = np.clip(team_matches / 6.0, 0, 1)
    prior_start = previous_start.fillna(np.nan).to_numpy(float)
    prior_minutes = previous_minutes.fillna(np.nan).to_numpy(float)
    blended_start = np.where(
        np.isfinite(current_start) & np.isfinite(prior_start),
        current_weight * current_start + (1 - current_weight) * prior_start,
        np.where(np.isfinite(current_start), current_start, prior_start),
    )
    blended_minutes = np.where(
        np.isfinite(current_minutes) & np.isfinite(prior_minutes),
        current_weight * current_minutes + (1 - current_weight) * prior_minutes,
        np.where(np.isfinite(current_minutes), current_minutes, prior_minutes),
    )

    # Backward-compatible in-season fallback when a caller has accumulated starts
    # and minutes but no explicit team-match count or prior-season bridge.
    if float(starts.max()) > 0:
        fallback_start = np.clip(
            np.where(starts > 0, mins / np.maximum(starts * 90.0, 1), starts90),
            0.20,
            0.98,
        )
        fallback_minutes = np.clip(avg_if_started * fallback_start, 0, 90)
    else:
        fallback_start = np.full(len(df), 0.62)
        fallback_minutes = np.full(len(df), 58.0)
    hist_start_prob = np.where(np.isfinite(blended_start), blended_start, fallback_start)
    historic_expected_minutes = np.where(
        np.isfinite(blended_minutes), blended_minutes, fallback_minutes
    )

    pre_start_prob = np.where(pre_apps > 0, np.clip(pre_starts / np.maximum(pre_apps, 1), 0, 1), 0.50)
    pre_avg_minutes = np.where(pre_apps > 0, np.clip(pre_mins / np.maximum(pre_apps, 1), 0, 90), 55)
    preseason_signal = 0.60 * (90 * pre_start_prob) + 0.40 * pre_avg_minutes
    historic_signal = 0.65 * historic_expected_minutes + 0.35 * (
        avg_if_started * hist_start_prob
    )
    has_preseason = pre_apps > 0
    # Preseason is evidence, not a new season-sized prior.  The old formula assigned
    # 58% to *any* appearance, so one 45-minute cameo could overwhelm 30 competitive
    # starts.  Weight now grows from effective team-sheet evidence: starts are much
    # stronger than cameos, minutes add support, and repeated starts can still
    # supersede a stale historical role.  A single non-start is capped at 12%.
    effective_preseason_games = pre_starts + 0.25 * np.maximum(pre_apps - pre_starts, 0)
    sample_reliability = 1.0 - np.exp(-effective_preseason_games / 1.8)
    minutes_reliability = np.clip(pre_mins / 270.0, 0, 1)
    preseason_weight = np.clip(
        0.82 * sample_reliability * (0.70 + 0.30 * minutes_reliability),
        0,
        0.82,
    )
    cameo_only = (pre_apps == 1) & (pre_starts == 0)
    preseason_weight = np.where(cameo_only, np.minimum(preseason_weight, 0.12), preseason_weight)
    base_minutes = np.where(
        has_preseason,
        preseason_weight * preseason_signal + (1 - preseason_weight) * historic_signal,
        historic_signal,
    )
    base_start = np.where(
        has_preseason,
        preseason_weight * pre_start_prob + (1 - preseason_weight) * hist_start_prob,
        hist_start_prob,
    )

    # Current, attributable starting-role evidence can raise a healthy player's
    # statistical prior by only a small, source-tiered amount. The producer caps
    # these deltas; this consumer defensively re-caps them so malformed inputs can
    # never manufacture a near-certain starter.
    news_minutes_delta = _series(df, "news_minutes_delta", 0.0).clip(0, 8.0)
    news_start_delta = _series(
        df, "news_start_probability_delta", 0.0
    ).clip(0, 0.10)
    base_minutes = np.minimum(base_minutes + news_minutes_delta, 85.0)
    base_start = np.minimum(base_start + news_start_delta, 0.95)

    # Explicit deadline evidence from official press conferences, club releases or
    # a verified projected XI may replace the statistical role prior. Overrides are
    # inputs to expected value, not confidence multipliers or optimiser bonuses.
    minutes_override = _optional_series(df, "expected_minutes_override")
    start_override = _optional_series(df, "start_probability_override")
    base_minutes = np.where(
        minutes_override.notna(),
        minutes_override.clip(0, 90),
        base_minutes,
    )
    base_start = np.where(
        start_override.notna(),
        start_override.clip(0, 1),
        base_start,
    )

    avail = df.apply(availability_probability, axis=1).astype(float)
    manual = _series(df, "availability_multiplier", 1.0).clip(0, 1)
    news = _series(df, "news_multiplier", 1.0).clip(0, 1)
    availability = np.minimum(np.minimum(avail, manual), news)

    expected = np.clip(base_minutes * availability, 0, 90)
    start = np.clip(np.asarray(base_start, dtype=float) * availability, 0, 1)
    # A non-starter can still appear from the bench. The coefficient is deliberately
    # below 1 because substitute usage is uncertain rather than guaranteed.
    appearance = np.clip(start + (1 - start) * 0.52 * availability, start, 1)
    appearance_override = _optional_series(df, "appearance_probability_override")
    appearance = np.where(
        appearance_override.notna(),
        np.clip(appearance_override, start, 1) * availability,
        appearance,
    )
    conditional_60 = 1.0 / (1.0 + np.exp(-(np.asarray(expected, dtype=float) - 58.0) / 8.0))
    p60 = np.minimum(appearance, np.clip(0.15 * appearance + 0.85 * conditional_60 * start, 0, 1))
    p80 = np.minimum(p60, np.clip((np.asarray(expected, dtype=float) - 45) / 40, 0, 1) * start)
    states = minute_state_probabilities(start, appearance, p60, p80)
    states.index = df.index

    prior_evidence = np.clip(_optional_series(df, "previous_starts").fillna(0) / 20.0, 0, 1)
    historic_evidence = np.clip(
        (mins / 900.0) + (starts / 10.0) + 0.70 * prior_evidence,
        0,
        1,
    )
    preseason_evidence = np.clip(effective_preseason_games / 4.0, 0, 1)
    availability_clarity = np.where(df.get("chance_of_playing_next_round", pd.Series(np.nan, index=df.index)).notna(), 0.95, 0.72)
    confidence = np.clip(
        0.35 + 0.28 * np.maximum(historic_evidence, preseason_evidence) + 0.22 * availability_clarity,
        0.35,
        0.95,
    )
    evidence_confidence = _optional_series(df, "minutes_evidence_confidence")
    news_confidence = _optional_series(df, "news_confidence")
    confidence = np.where(
        evidence_confidence.notna(),
        np.maximum(confidence, evidence_confidence.clip(0, 0.95)),
        confidence,
    )
    confidence = np.where(
        news_confidence.notna(),
        np.maximum(confidence, news_confidence.clip(0, 0.92)),
        confidence,
    )
    # Explicit news/manual overrides are useful evidence, but also signal that the
    # situation may be moving. They should not create false certainty.
    override_present = (manual < 0.999) | (news < 0.999) | (news_minutes_delta > 0)
    confidence = np.where(override_present, np.minimum(confidence, 0.82), confidence)

    result = pd.DataFrame({
        "expected_minutes": expected,
        "start_probability": start,
        "appearance_probability": appearance,
        "minutes_60_plus_probability": p60,
        "minutes_80_plus_probability": p80,
        "minutes_confidence": confidence,
        # Decision-grade observability: these fields explain the incumbent model
        # without changing it. A future decomposed challenger must be validated
        # before it can replace expected_minutes/start_probability.
        "historical_start_probability": hist_start_prob,
        "historical_expected_minutes": historic_expected_minutes,
        "preseason_start_probability": pre_start_prob,
        "preseason_average_minutes": pre_avg_minutes,
        "preseason_signal_minutes": preseason_signal,
        "historical_signal_minutes": historic_signal,
        "role_expected_minutes_pre_availability": base_minutes,
        "role_start_probability_pre_availability": base_start,
        "availability_probability": availability,
        "preseason_role_weight": preseason_weight,
        "preseason_effective_games": effective_preseason_games,
    }, index=df.index)
    for column in states.columns:
        result[column] = states[column]
    return result


def expected_minutes(df: pd.DataFrame) -> pd.Series:
    return minutes_profile(df)["expected_minutes"]
