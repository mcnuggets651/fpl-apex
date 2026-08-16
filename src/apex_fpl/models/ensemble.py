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


def blend_projection(
    base: pd.DataFrame,
    weights: dict[str, float],
    risk_penalty: float,
) -> pd.DataFrame:
    """Blend expert forecasts while keeping expected value separate from risk.

    AIrsenal can legitimately omit a newly registered player even after the player
    exists in its refreshed database. Missing AIrsenal rows must not be fabricated,
    but they also must not silently increase every other expert's effective weight.
    For that one required expert, Apex explicitly assigns the missing configured
    weight to the transparent Apex model for the affected player/Gameweek. The raw
    AIrsenal source remains absent and is exposed as such in provenance columns.
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

    fallback = (
        pd.to_numeric(out.get("apex_xp", 0), errors="coerce")
        .fillna(0)
        .to_numpy(float)
    )

    for key, col in EXPERT_COLUMNS.items():
        if col not in out.columns:
            continue
        v = pd.to_numeric(out[col], errors="coerce").to_numpy(float)
        mask = np.isfinite(v)
        w = max(float(weights.get(key, 0)), 0.0)
        expert_values[key] = v
        expert_weights[key] = w
        numerator[mask] += v[mask] * w
        sumsq[mask] += (v[mask] ** 2) * w
        denominator[mask] += w
        expert_count[mask] += 1

    # Required-source absence policy: preserve AIrsenal provenance as absent, but
    # keep the configured ensemble weights fixed by assigning its missing weight
    # explicitly to the transparent Apex estimate. This is not an AIrsenal value.
    air_w = max(float(weights.get("airsenal", 0)), 0.0)
    if air_w > 0:
        if "airsenal" in expert_values:
            air_present = np.isfinite(expert_values["airsenal"])
        else:
            air_present = np.zeros(n, dtype=bool)
        air_missing = ~air_present
        numerator[air_missing] += fallback[air_missing] * air_w
        sumsq[air_missing] += (fallback[air_missing] ** 2) * air_w
        denominator[air_missing] += air_w
    else:
        air_missing = np.zeros(n, dtype=bool)

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

    for key, column in EXPERT_COLUMNS.items():
        contrib = np.zeros(n, dtype=float)
        effective_weight = np.zeros(n, dtype=float)
        source_present = np.zeros(n, dtype=bool)
        if key in expert_values:
            values = expert_values[key]
            source_present = np.isfinite(values)
            valid = source_present & (denominator > 0)
            effective_weight[valid] = (
                expert_weights[key] / np.maximum(denominator[valid], 1e-12)
            )
            contrib[valid] = values[valid] * effective_weight[valid]
        out[f"xp_expert_{key}"] = contrib
        out[f"effective_weight_{key}"] = effective_weight
        out[f"configured_weight_{key}"] = max(float(weights.get(key, 0.0)), 0.0)
        out[f"source_present_{key}"] = source_present

    air_fallback_weight = np.zeros(n, dtype=float)
    air_fallback_contrib = np.zeros(n, dtype=float)
    if air_w > 0:
        valid_fallback = air_missing & (denominator > 0)
        air_fallback_weight[valid_fallback] = air_w / np.maximum(
            denominator[valid_fallback], 1e-12
        )
        air_fallback_contrib[valid_fallback] = (
            fallback[valid_fallback] * air_fallback_weight[valid_fallback]
        )
    out["airsenal_source_absent"] = air_missing
    out["effective_weight_airsenal_fallback_apex"] = air_fallback_weight
    out["xp_expert_airsenal_fallback_apex"] = air_fallback_contrib

    no_expert = denominator <= 0
    if np.any(no_expert):
        out.loc[no_expert, "xp_expert_apex_model"] = fallback[no_expert]
        out.loc[no_expert, "effective_weight_apex_model"] = 1.0

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
