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
    """Allocate full-GW expert values across fixture rows exactly once.

    ``project_players`` intentionally keeps one row per player/fixture so DGW
    decomposition remains auditable. Official ``ep_next`` and the AIrsenal export,
    however, are already player/Gameweek totals. Merging them naively onto both DGW
    fixture rows doubles those experts. Equal allocation is neutral with respect to
    the eventual player/GW sum and prevents that silent inflation.
    """
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
    """Blend experts with missing-source reweighting and quantified uncertainty."""
    out = _allocate_gameweek_experts(base.copy())
    n = len(out)
    numerator = np.zeros(n, dtype=float)
    denominator = np.zeros(n, dtype=float)
    sumsq = np.zeros(n, dtype=float)
    total_configured_weight = (
        sum(max(float(weights.get(k, 0)), 0) for k in EXPERT_COLUMNS) or 1.0
    )
    expert_count = np.zeros(n, dtype=int)

    for key, col in EXPERT_COLUMNS.items():
        if col not in out.columns:
            continue
        v = pd.to_numeric(out[col], errors="coerce").to_numpy(float)
        mask = np.isfinite(v)
        w = max(float(weights.get(key, 0)), 0.0)
        numerator[mask] += v[mask] * w
        sumsq[mask] += (v[mask] ** 2) * w
        denominator[mask] += w
        expert_count[mask] += 1

    fallback = (
        pd.to_numeric(out.get("apex_xp", 0), errors="coerce")
        .fillna(0)
        .to_numpy(float)
    )
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
    min_conf = (
        pd.to_numeric(min_src, errors="coerce").fillna(0.65).to_numpy(float)
    )
    role_conf = (
        pd.to_numeric(role_src, errors="coerce").fillna(0.65).to_numpy(float)
    )
    confidence = np.clip(
        coverage
        * agreement
        * (0.55 + 0.30 * min_conf + 0.15 * role_conf),
        0.05,
        0.99,
    )

    out["xp"] = mean
    out["expert_count"] = expert_count
    out["expert_coverage"] = coverage
    out["expert_disagreement_sd"] = disagreement_sd
    # ``projection_sd`` includes the transparent model's match-outcome variance.
    # That is useful for points-distribution reporting, but it is not uncertainty
    # about the latent expected-points forecast and must not drive decision
    # stability re-solves. Keep a separate epistemic scale built from expert
    # disagreement and an explicit evidence-gap allowance.
    evidence_gap_sd = np.maximum(mean, 0.0) * (
        0.05 + 0.25 * (1.0 - confidence)
    )
    out["forecast_uncertainty_sd"] = np.sqrt(
        disagreement_sd**2 + evidence_gap_sd**2
    )
    out["projection_sd"] = total_sd
    out["projection_confidence"] = confidence
    penalty_scale = 1.15 - 0.30 * confidence
    out["risk_adjusted_xp"] = np.maximum(
        mean - risk_penalty * total_sd * penalty_scale, 0
    )
    out["projection_floor_80"] = np.maximum(mean - 1.2816 * total_sd, 0)
    out["projection_ceiling_80"] = mean + 1.2816 * total_sd
    return out
