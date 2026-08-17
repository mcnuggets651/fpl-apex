from __future__ import annotations

import numpy as np
import pandas as pd


EXPERT_COLUMNS = {
    "official_ep": "official_xp",
    "apex_model": "apex_xp",
    "airsenal": "airsenal_xp",
    "market": "market_xp",
}

# These experts currently enter Apex as one total expected-points value per
# player/Gameweek. The transparent Apex model is the only fixture-row expert.
FULL_GAMEWEEK_EXPERTS = {"official_xp", "airsenal_xp", "market_xp"}
AIRSENAL_ZERO_TOLERANCE = 1e-12
AIRSENAL_ROLE_CONFLICT_MIN_APPEARANCE_XP = 1.0
AIRSENAL_ROLE_CONFLICT_MIN_OFFICIAL_XP = 1.0


def _allocate_gameweek_experts(out: pd.DataFrame) -> pd.DataFrame:
    """Allocate full-GW expert values across fixture rows exactly once."""
    if not {"player_id", "gw"}.issubset(out.columns):
        return out
    counts = out.groupby(["player_id", "gw"])["player_id"].transform("size")
    counts = pd.to_numeric(counts, errors="coerce").fillna(1).clip(lower=1)
    out["expert_allocation_count"] = counts.astype(int)
    for col in FULL_GAMEWEEK_EXPERTS:
        if col in out.columns:
            values = pd.to_numeric(out[col], errors="coerce")
            out[col] = values / counts
    return out


def _airsenal_zero_role_conflict(out: pd.DataFrame) -> np.ndarray:
    """Identify exact-zero AIrsenal rows contradicted by current role evidence.

    The pinned AIrsenal model explicitly predicts zero when its recent-minutes
    history sums to zero. Before GW1 that history falls back to previous-season
    minutes for the player's *current* club, so transfers/new roles can receive a
    structural zero despite current evidence of participation. We only abstain when
    two independent current signals agree that the zero-minute premise is stale:
    Official FPL expected points and Apex's explicit appearance component must both
    imply meaningful participation.

    Once that contradiction is established for a player on a row where Official EP
    exists, other exact-zero AIrsenal rows for the same player in the horizon inherit
    the abstention. Positive AIrsenal forecasts are never suppressed.
    """
    n = len(out)
    if "airsenal_xp" not in out.columns:
        return np.zeros(n, dtype=bool)
    air = pd.to_numeric(out["airsenal_xp"], errors="coerce")
    official = pd.to_numeric(
        out.get("official_xp", pd.Series(np.nan, index=out.index)),
        errors="coerce",
    )
    appearance = pd.to_numeric(
        out.get("xp_appearance", pd.Series(0.0, index=out.index)),
        errors="coerce",
    ).fillna(0.0)
    zero = air.notna() & air.abs().le(AIRSENAL_ZERO_TOLERANCE)
    direct = (
        zero
        & official.notna()
        & official.ge(AIRSENAL_ROLE_CONFLICT_MIN_OFFICIAL_XP)
        & appearance.ge(AIRSENAL_ROLE_CONFLICT_MIN_APPEARANCE_XP)
    )
    if "player_id" not in out.columns or not direct.any():
        return direct.to_numpy(bool)
    conflicted_ids = set(
        pd.to_numeric(out.loc[direct, "player_id"], errors="coerce")
        .dropna()
        .astype(int)
    )
    player_ids = pd.to_numeric(out["player_id"], errors="coerce")
    return (zero & player_ids.isin(conflicted_ids)).to_numpy(bool)


def blend_projection(
    base: pd.DataFrame,
    weights: dict[str, float],
    risk_penalty: float,
) -> pd.DataFrame:
    """Blend expert forecasts while keeping expected value separate from risk.

    AIrsenal can legitimately omit a newly registered player even after the player
    exists in its refreshed database. Missing AIrsenal rows must not be fabricated,
    but they also must not silently increase every other expert's effective weight.
    Its configured weight is explicitly assigned to the transparent Apex estimate.

    A second explicit AIrsenal abstention handles a known pre-GW1 source semantic:
    exact zero can mean "no recent minutes at the current club" rather than a
    current-role forecast. If Official FPL and Apex both contradict that zero-minute
    premise, the raw AIrsenal source remains visible but is not allowed to vote as a
    certain zero. Its weight follows the same auditable Apex fallback as a missing
    AIrsenal prediction.

    Market xP has no such fallback. A positive market weight therefore requires a
    genuine market_xp surface; otherwise the model fails instead of silently
    renormalising a configured expert away.
    """
    out = _allocate_gameweek_experts(base.copy())
    n = len(out)
    numerator = np.zeros(n, dtype=float)
    denominator = np.zeros(n, dtype=float)
    sumsq = np.zeros(n, dtype=float)
    total_configured_weight = (
        sum(max(float(weights.get(k, 0)), 0) for k in EXPERT_COLUMNS) or 1.0
    )
    expert_count = np.zeros(n, dtype=int)
    expert_values: dict[str, np.ndarray] = {}
    expert_weights: dict[str, float] = {}
    expert_usable: dict[str, np.ndarray] = {}

    market_w = max(float(weights.get("market", 0)), 0.0)
    market_available = (
        "market_xp" in out.columns
        and pd.to_numeric(out["market_xp"], errors="coerce").notna().any()
    )
    if market_w > 0 and not market_available:
        raise ValueError(
            "positive market ensemble weight requires genuine market_xp data; "
            "set market weight to zero until a production market source is configured"
        )

    fallback = (
        pd.to_numeric(out.get("apex_xp", 0), errors="coerce")
        .fillna(0)
        .to_numpy(float)
    )
    air_role_conflict = _airsenal_zero_role_conflict(out)

    for key, col in EXPERT_COLUMNS.items():
        if col not in out.columns:
            continue
        v = pd.to_numeric(out[col], errors="coerce").to_numpy(float)
        source_present = np.isfinite(v)
        usable = source_present.copy()
        if key == "airsenal":
            usable &= ~air_role_conflict
        w = max(float(weights.get(key, 0)), 0.0)
        expert_values[key] = v
        expert_weights[key] = w
        expert_usable[key] = usable
        numerator[usable] += v[usable] * w
        sumsq[usable] += (v[usable] ** 2) * w
        denominator[usable] += w
        expert_count[usable] += 1

    # Required-source absence/abstention policy: preserve AIrsenal provenance as
    # source-present where appropriate, but keep configured weights fixed by assigning
    # unavailable/unusable AIrsenal weight explicitly to transparent Apex.
    air_w = max(float(weights.get("airsenal", 0)), 0.0)
    if air_w > 0:
        if "airsenal" in expert_values:
            air_present = np.isfinite(expert_values["airsenal"])
            air_usable = expert_usable["airsenal"]
        else:
            air_present = np.zeros(n, dtype=bool)
            air_usable = np.zeros(n, dtype=bool)
        air_missing = ~air_present
        air_fallback = ~air_usable
        numerator[air_fallback] += fallback[air_fallback] * air_w
        sumsq[air_fallback] += (fallback[air_fallback] ** 2) * air_w
        denominator[air_fallback] += air_w
    else:
        air_present = np.zeros(n, dtype=bool)
        air_missing = np.zeros(n, dtype=bool)
        air_fallback = np.zeros(n, dtype=bool)

    mean = np.where(
        denominator > 0,
        numerator / np.maximum(denominator, 1e-12),
        fallback,
    )
    weighted_second = np.where(
        denominator > 0,
        sumsq / np.maximum(denominator, 1e-12),
        mean**2,
    )
    disagreement_var = np.maximum(weighted_second - mean**2, 0)
    disagreement_sd = np.sqrt(disagreement_var)
    model_sd = (
        pd.to_numeric(out.get("apex_sd", 0), errors="coerce")
        .fillna(0)
        .to_numpy(float)
    )
    total_sd = np.sqrt(model_sd**2 + disagreement_sd**2)
    coverage = np.clip(denominator / total_configured_weight, 0, 1)
    agreement = np.exp(-disagreement_sd / 3.0)
    min_src = (
        out["minutes_confidence"]
        if "minutes_confidence" in out
        else pd.Series(0.65, index=out.index)
    )
    role_src = (
        out["role_confidence"]
        if "role_confidence" in out
        else pd.Series(0.65, index=out.index)
    )
    min_conf = pd.to_numeric(min_src, errors="coerce").fillna(0.65).to_numpy(float)
    role_conf = pd.to_numeric(role_src, errors="coerce").fillna(0.65).to_numpy(float)
    confidence = np.clip(
        coverage
        * agreement
        * (0.55 + 0.30 * min_conf + 0.15 * role_conf),
        0.05,
        0.99,
    )

    out["xp"] = mean
    out["canonical_ev_xp"] = mean
    out["expert_count"] = expert_count
    out["expert_coverage"] = coverage
    out["expert_disagreement_sd"] = disagreement_sd
    out["configured_weight_total"] = float(total_configured_weight)
    out["available_or_fallback_weight"] = denominator

    for key, column in EXPERT_COLUMNS.items():
        contrib = np.zeros(n, dtype=float)
        effective_weight = np.zeros(n, dtype=float)
        source_present = np.zeros(n, dtype=bool)
        source_usable = np.zeros(n, dtype=bool)
        if key in expert_values:
            values = expert_values[key]
            source_present = np.isfinite(values)
            source_usable = expert_usable[key]
            valid = source_usable & (denominator > 0)
            effective_weight[valid] = (
                expert_weights[key] / np.maximum(denominator[valid], 1e-12)
            )
            contrib[valid] = values[valid] * effective_weight[valid]
        out[f"xp_expert_{key}"] = contrib
        out[f"effective_weight_{key}"] = effective_weight
        out[f"configured_weight_{key}"] = max(float(weights.get(key, 0.0)), 0.0)
        out[f"source_present_{key}"] = source_present
        out[f"source_usable_{key}"] = source_usable

    air_fallback_weight = np.zeros(n, dtype=float)
    air_fallback_contrib = np.zeros(n, dtype=float)
    if air_w > 0:
        valid_fallback = air_fallback & (denominator > 0)
        air_fallback_weight[valid_fallback] = air_w / np.maximum(
            denominator[valid_fallback], 1e-12
        )
        air_fallback_contrib[valid_fallback] = (
            fallback[valid_fallback] * air_fallback_weight[valid_fallback]
        )
    out["airsenal_source_absent"] = air_missing
    out["airsenal_zero_role_conflict"] = air_role_conflict
    out["airsenal_abstained_role_conflict"] = air_role_conflict
    out["effective_weight_airsenal_fallback_apex"] = air_fallback_weight
    out["xp_expert_airsenal_fallback_apex"] = air_fallback_contrib

    # Canonical Apex contribution includes any explicitly delegated AIrsenal share.
    # Preserve the direct values separately so provenance can still distinguish the
    # configured Apex vote from the source-fallback vote. This keeps decomposition
    # additive: official + Apex(total) + usable AIrsenal + market == canonical xP.
    out["xp_expert_apex_model_direct"] = out["xp_expert_apex_model"]
    out["effective_weight_apex_model_direct"] = out["effective_weight_apex_model"]
    out["xp_expert_apex_model"] = (
        out["xp_expert_apex_model"] + air_fallback_contrib
    )
    out["effective_weight_apex_model"] = (
        out["effective_weight_apex_model"] + air_fallback_weight
    )

    no_expert = denominator <= 0
    if np.any(no_expert):
        out.loc[no_expert, "xp_expert_apex_model"] = fallback[no_expert]
        out.loc[no_expert, "effective_weight_apex_model"] = 1.0
        out.loc[no_expert, "source_usable_apex_model"] = True

    evidence_gap_sd = np.maximum(mean, 0.0) * (0.05 + 0.25 * (1.0 - confidence))
    out["forecast_uncertainty_sd"] = np.sqrt(
        disagreement_sd**2 + evidence_gap_sd**2
    )
    out["projection_sd"] = total_sd
    out["projection_confidence"] = confidence

    penalty_scale = 1.15 - 0.30 * confidence
    out["downside_adjusted_xp"] = np.maximum(
        mean - risk_penalty * total_sd * penalty_scale, 0
    )
    out["risk_adjusted_xp"] = mean
    out["projection_floor_80"] = np.maximum(mean - 1.2816 * total_sd, 0)
    out["projection_ceiling_80"] = mean + 1.2816 * total_sd
    return out
