from __future__ import annotations

import numpy as np
import pandas as pd


EXPERT_COLUMNS = {
    "official_ep": "official_xp",
    "apex_model": "apex_xp",
    "airsenal": "airsenal_xp",
    "market": "market_xp",
}

FULL_GAMEWEEK_EXPERTS = {"official_xp", "airsenal_xp", "market_xp"}
AIRSENAL_ZERO_TOLERANCE = 1e-12
AIRSENAL_ROLE_CONFLICT_MIN_APPEARANCE_XP = 1.0
AIRSENAL_ROLE_CONFLICT_MIN_OFFICIAL_XP = 1.0
APEX_RELIABILITY_MIN_MULTIPLIER = 0.20
APEX_OUTLIER_ABSOLUTE_MARGIN = 0.75
APEX_OUTLIER_RELATIVE_MARGIN = 0.20


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
    """Identify exact-zero AIrsenal rows contradicted by current role evidence."""
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


def _apex_reliability_policy(
    out: pd.DataFrame,
    expert_values: dict[str, np.ndarray],
    expert_usable: dict[str, np.ndarray],
    expert_weights: dict[str, float],
) -> dict[str, np.ndarray]:
    """Attenuate only unsupported Apex outliers confirmed by independent experts.

    Generic minutes or role uncertainty is *not* a reason to lower expected value.
    The nominal Apex expert weight remains the ceiling.  A row is attenuated only
    when all three conditions are true:

    1. Apex itself marks the component evidence as less than fully reliable;
    2. at least two independent experts are simultaneously usable and Apex lies
       materially outside their envelope; and
    3. for later horizon rows where Official EP is unavailable, the same player's
       Apex forecast remains on the already-confirmed side of the independent
       consensus.

    This lets Apex keep differentiated high-EV views when evidence is strong, while
    preventing a tiny-sample attacking rate from dominating two independent models.
    """
    n = len(out)
    apex = expert_values.get("apex_model", np.full(n, np.nan, dtype=float))
    apex_usable = expert_usable.get("apex_model", np.zeros(n, dtype=bool))
    reliability = pd.to_numeric(
        out.get("apex_model_reliability", pd.Series(1.0, index=out.index)),
        errors="coerce",
    ).fillna(1.0).clip(0.0, 1.0).to_numpy(float)

    independent_keys = ["official_ep", "airsenal", "market"]
    independent_count = np.zeros(n, dtype=int)
    independent_weight = np.zeros(n, dtype=float)
    consensus_num = np.zeros(n, dtype=float)
    lower = np.full(n, np.nan, dtype=float)
    upper = np.full(n, np.nan, dtype=float)

    for key in independent_keys:
        if key not in expert_values:
            continue
        values = expert_values[key]
        usable = expert_usable[key]
        weight = max(float(expert_weights.get(key, 0.0)), 0.0)
        active = usable & (weight > 0)
        independent_count[active] += 1
        independent_weight[active] += weight
        consensus_num[active] += values[active] * weight
        lower = np.where(
            active & (np.isnan(lower) | (values < lower)), values, lower
        )
        upper = np.where(
            active & (np.isnan(upper) | (values > upper)), values, upper
        )

    consensus = np.divide(
        consensus_num,
        np.maximum(independent_weight, 1e-12),
        out=np.full(n, np.nan, dtype=float),
        where=independent_weight > 0,
    )
    margin = np.maximum(
        APEX_OUTLIER_ABSOLUTE_MARGIN,
        APEX_OUTLIER_RELATIVE_MARGIN * np.maximum(np.abs(consensus), 1.0),
    )
    direct_high = (
        apex_usable
        & (reliability < 0.999)
        & (independent_count >= 2)
        & np.isfinite(upper)
        & (apex > upper + margin)
    )
    direct_low = (
        apex_usable
        & (reliability < 0.999)
        & (independent_count >= 2)
        & np.isfinite(lower)
        & (apex < lower - margin)
    )
    direct = direct_high | direct_low
    direction = np.where(direct_high, 1, np.where(direct_low, -1, 0)).astype(int)

    inherited = np.zeros(n, dtype=bool)
    if "player_id" in out.columns and direct.any():
        player_ids = pd.to_numeric(out["player_id"], errors="coerce")
        direct_frame = pd.DataFrame(
            {"player_id": player_ids, "direction": direction, "direct": direct}
        )
        confirmed: dict[int, int] = {}
        for player_id, group in direct_frame[direct_frame["direct"]].groupby("player_id"):
            directions = set(group["direction"].astype(int)) - {0}
            if len(directions) == 1 and pd.notna(player_id):
                confirmed[int(player_id)] = int(next(iter(directions)))
        for idx, player_id in enumerate(player_ids):
            if direct[idx] or pd.isna(player_id):
                continue
            inherited_direction = confirmed.get(int(player_id), 0)
            if inherited_direction == 0 or independent_count[idx] < 1:
                continue
            if inherited_direction > 0:
                inherited[idx] = bool(
                    np.isfinite(consensus[idx]) and apex[idx] > consensus[idx] + margin[idx]
                )
            else:
                inherited[idx] = bool(
                    np.isfinite(consensus[idx]) and apex[idx] < consensus[idx] - margin[idx]
                )
            if inherited[idx]:
                direction[idx] = inherited_direction

    conflict = direct | inherited
    multiplier = np.ones(n, dtype=float)
    multiplier[conflict] = np.clip(
        reliability[conflict],
        APEX_RELIABILITY_MIN_MULTIPLIER,
        1.0,
    )
    return {
        "reliability": reliability,
        "independent_count": independent_count,
        "consensus": consensus,
        "lower": lower,
        "upper": upper,
        "margin": margin,
        "direct": direct,
        "inherited": inherited,
        "direction": direction,
        "conflict": conflict,
        "multiplier": multiplier,
    }


def blend_projection(
    base: pd.DataFrame,
    weights: dict[str, float],
    risk_penalty: float,
) -> pd.DataFrame:
    """Blend expert forecasts while keeping expected value separate from risk.

    Missing AIrsenal rows retain the explicit Apex fallback contract. Market xP has
    no fallback.  Apex-specific reliability can reduce only the *direct* Apex vote,
    and only under independently confirmed material disagreement; generic uncertainty
    remains diagnostic and cannot turn the optimiser into a nailed-minutes selector.
    """
    out = _allocate_gameweek_experts(base.copy())
    n = len(out)
    total_configured_weight = (
        sum(max(float(weights.get(k, 0)), 0) for k in EXPERT_COLUMNS) or 1.0
    )
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

    fallback = pd.to_numeric(
        out.get("apex_xp", pd.Series(0.0, index=out.index)), errors="coerce"
    ).fillna(0).to_numpy(float)
    air_role_conflict = _airsenal_zero_role_conflict(out)

    for key, col in EXPERT_COLUMNS.items():
        if col not in out.columns:
            continue
        values = pd.to_numeric(out[col], errors="coerce").to_numpy(float)
        usable = np.isfinite(values)
        if key == "airsenal":
            usable &= ~air_role_conflict
        expert_values[key] = values
        expert_weights[key] = max(float(weights.get(key, 0)), 0.0)
        expert_usable[key] = usable

    policy = _apex_reliability_policy(
        out,
        expert_values,
        expert_usable,
        expert_weights,
    )
    apex_nominal = max(float(weights.get("apex_model", 0.0)), 0.0)
    apex_row_weight = apex_nominal * policy["multiplier"]

    numerator = np.zeros(n, dtype=float)
    denominator = np.zeros(n, dtype=float)
    sumsq = np.zeros(n, dtype=float)
    expert_count = np.zeros(n, dtype=int)
    row_weights: dict[str, np.ndarray] = {}

    for key, values in expert_values.items():
        usable = expert_usable[key]
        if key == "apex_model":
            weight = apex_row_weight
        else:
            weight = np.full(n, expert_weights[key], dtype=float)
        row_weights[key] = weight
        active = usable & (weight > 0)
        numerator[active] += values[active] * weight[active]
        sumsq[active] += (values[active] ** 2) * weight[active]
        denominator[active] += weight[active]
        expert_count[active] += 1

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
    model_sd = pd.to_numeric(
        out.get("apex_sd", pd.Series(0.0, index=out.index)), errors="coerce"
    ).fillna(0).to_numpy(float)
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
    out["apex_model_reliability"] = policy["reliability"]
    out["apex_reliability_conflict"] = policy["direct"]
    out["apex_reliability_conflict_inherited"] = policy["inherited"]
    out["apex_reliability_conflict_direction"] = policy["direction"]
    out["apex_reliability_weight_multiplier"] = policy["multiplier"]
    out["independent_expert_count"] = policy["independent_count"]
    out["independent_consensus_xp"] = policy["consensus"]
    out["independent_consensus_lower"] = policy["lower"]
    out["independent_consensus_upper"] = policy["upper"]
    out["independent_consensus_margin"] = policy["margin"]

    for key in EXPERT_COLUMNS:
        contrib = np.zeros(n, dtype=float)
        effective_weight = np.zeros(n, dtype=float)
        source_present = np.zeros(n, dtype=bool)
        source_usable = np.zeros(n, dtype=bool)
        if key in expert_values:
            values = expert_values[key]
            source_present = np.isfinite(values)
            source_usable = expert_usable[key]
            weights_for_key = row_weights[key]
            valid = source_usable & (denominator > 0) & (weights_for_key > 0)
            effective_weight[valid] = weights_for_key[valid] / np.maximum(
                denominator[valid], 1e-12
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

    out["xp_expert_apex_model_direct"] = out["xp_expert_apex_model"]
    out["effective_weight_apex_model_direct"] = out["effective_weight_apex_model"]
    out["xp_expert_apex_model"] = out["xp_expert_apex_model"] + air_fallback_contrib
    out["effective_weight_apex_model"] = (
        out["effective_weight_apex_model"] + air_fallback_weight
    )

    no_expert = denominator <= 0
    if np.any(no_expert):
        out.loc[no_expert, "xp_expert_apex_model"] = fallback[no_expert]
        out.loc[no_expert, "effective_weight_apex_model"] = 1.0
        out.loc[no_expert, "source_usable_apex_model"] = True

    evidence_gap_sd = np.maximum(mean, 0.0) * (0.05 + 0.25 * (1.0 - confidence))
    out["forecast_uncertainty_sd"] = np.sqrt(disagreement_sd**2 + evidence_gap_sd**2)
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
