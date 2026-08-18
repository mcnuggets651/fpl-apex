from __future__ import annotations

import math

import numpy as np
import pandas as pd

from apex_fpl.models.bonus import expected_bonus_proxy
from apex_fpl.models.defcon import expected_defensive_contribution_points


# Production-promoted 2026-08-14 after the sealed predictive-validity and exact
# decision A/B gates passed. These values are intentionally frozen to the audited
# challenger; changing them requires a new predictive and decision-level audit.
UNDERSTAT_XG_WEIGHT = 0.50
UNDERSTAT_XA_WEIGHT = 0.30
RATE_RELIABILITY_MINUTES = 270.0
RATE_CREDIBILITY_FLOOR = 0.05


def _num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _optional_num(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce")


def _preseason_rate_weight(
    preseason_minutes: pd.Series,
    preseason_starts: pd.Series | None = None,
    preseason_appearances: pd.Series | None = None,
) -> pd.Series:
    """Return reliability-weighted influence for preseason per-90 rates."""
    mins = pd.to_numeric(preseason_minutes, errors="coerce").fillna(0.0)
    legacy_weight = pd.Series(np.clip(mins / 270.0, 0.0, 0.35), index=mins.index)
    if preseason_starts is None or preseason_appearances is None:
        return legacy_weight

    starts = pd.to_numeric(preseason_starts, errors="coerce").fillna(0.0)
    apps = pd.to_numeric(preseason_appearances, errors="coerce").fillna(0.0)
    effective_games = starts + 0.25 * np.maximum(apps - starts, 0.0)
    sample_reliability = 1.0 - np.exp(-effective_games / 1.8)
    minutes_reliability = np.clip(mins / 270.0, 0.0, 1.0)
    reliable_weight = 0.35 * sample_reliability * (0.70 + 0.30 * minutes_reliability)
    has_team_sheet_sample = apps > 0
    weight = np.where(has_team_sheet_sample, reliable_weight, legacy_weight)
    return pd.Series(np.clip(weight, 0.0, 0.35), index=mins.index)


def _blend_rate(
    primary: pd.Series,
    preseason: pd.Series,
    preseason_minutes: pd.Series,
    preseason_starts: pd.Series | None = None,
    preseason_appearances: pd.Series | None = None,
) -> pd.Series:
    p = pd.to_numeric(primary, errors="coerce").fillna(0)
    pre_raw = pd.to_numeric(preseason, errors="coerce")
    pre = pre_raw.fillna(0)
    pre_weight = _preseason_rate_weight(
        preseason_minutes,
        preseason_starts,
        preseason_appearances,
    ) * pre_raw.notna().astype(float)
    return p * (1 - pre_weight) + pre * pre_weight


def _appearance_probabilities(expected_mins: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    em = pd.to_numeric(expected_mins, errors="coerce").fillna(0).to_numpy(float)
    p_app = np.clip(em / 28.0, 0, 1)
    p60 = np.where(em <= 0, 0.0, 1.0 / (1.0 + np.exp(-(em - 58.0) / 8.0)))
    p60 = np.minimum(p60, p_app)
    return p_app, p60


def _order_share(order: pd.Series) -> pd.Series:
    """Do not turn an ordinal set-piece rank into fabricated probability."""
    return pd.Series(0.0, index=order.index, dtype=float)


def _with_override(official_share: pd.Series, override: pd.Series) -> pd.Series:
    clean = pd.to_numeric(override, errors="coerce")
    return clean.where(clean.notna(), official_share).clip(0, 1)


def _at(values, idx: int) -> float:
    if hasattr(values, "iloc"):
        return float(values.iloc[idx])
    return float(values[idx])


def _weighted_quantile(values: np.ndarray, weights: np.ndarray, quantile: float) -> float:
    valid = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not valid.any():
        return float("nan")
    v = values[valid]
    w = weights[valid]
    order = np.argsort(v, kind="mergesort")
    v = v[order]
    w = w[order]
    cumulative = np.cumsum(w)
    threshold = float(np.clip(quantile, 0.0, 1.0)) * float(cumulative[-1])
    idx = int(np.searchsorted(cumulative, threshold, side="left"))
    return float(v[min(idx, len(v) - 1)])


def _position_attack_reference(
    d: pd.DataFrame,
    rate: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Build a mature, minutes-weighted same-position attack-rate reference.

    The projection layer reconstructs this independently from enrichment so a
    statistically explosive per-90 row can never bypass credibility control because
    of merge order or an optional upstream field. Before GW1, Core's generic
    ``minutes`` column may contain the same prior-season context; it is used only as
    a fallback when the explicit cross-season bridge has no sample.
    """
    positions = d.get("position", pd.Series("MID", index=d.index)).astype("string")
    previous = _optional_num(d, "previous_minutes")
    current_context = _num(d, "minutes", 0.0).clip(lower=0.0)
    current_team_matches = _num(d, "current_team_matches", 0.0).clip(lower=0.0)
    sample = previous.where(previous.notna() & previous.gt(0.0), np.nan)
    pre_gw1_fallback = sample.isna() & current_team_matches.le(0.0)
    sample.loc[pre_gw1_fallback] = current_context.loc[pre_gw1_fallback]
    sample = sample.fillna(0.0).clip(lower=0.0)

    prior = pd.Series(np.nan, index=d.index, dtype=float)
    upper = pd.Series(np.nan, index=d.index, dtype=float)
    for position in positions.dropna().unique():
        same = positions.eq(position)
        mature = same & sample.ge(RATE_RELIABILITY_MINUTES) & rate.notna() & rate.ge(0.0)
        if not mature.any():
            continue
        values = rate.loc[mature].to_numpy(float)
        weights = sample.loc[mature].to_numpy(float)
        prior_value = float(np.average(values, weights=weights))
        upper_value = _weighted_quantile(values, weights, 0.90)
        prior.loc[same] = prior_value
        upper.loc[same] = max(prior_value, upper_value)
    return sample, prior, upper


def _evidence_support(
    target_rate: pd.Series,
    evidence_rate: pd.Series,
    *,
    strong: float,
    moderate: float,
) -> np.ndarray:
    target = pd.to_numeric(target_rate, errors="coerce")
    evidence = pd.to_numeric(evidence_rate, errors="coerce")
    gap = (evidence - target).abs() / np.maximum(target.abs(), 0.10)
    return np.where(
        evidence.notna() & gap.le(0.50),
        strong,
        np.where(evidence.notna() & gap.le(1.00), moderate, 0.0),
    )


def _credible_attack_rate(
    d: pd.DataFrame,
    rate: pd.Series,
    label: str,
    understat_rate: pd.Series,
    preseason_rate: pd.Series,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return a credibility-adjusted attacking rate and its evidence reliability.

    Expected minutes determine opportunity; they must not suppress upside merely
    because a player is uncertain to start. This function addresses a different
    problem: estimating a *per-90 scoring rate* from a tiny sample. A 21-minute
    1.59 xG/90 observation is mathematically valid but cannot be treated as a mature
    expectation without corroboration.

    Only a materially extreme rate with <270 prior PL minutes is adjusted. The rate
    is shrunk toward a mature same-position, minutes-weighted prior. Genuine
    Understat or observed preseason xG/xA can rebuild credibility when it supports
    the same rate. Team-sheet appearances alone never count as attacking-rate
    evidence.
    """
    raw = pd.to_numeric(rate, errors="coerce").fillna(0.0).clip(lower=0.0)
    sample, computed_prior, computed_upper = _position_attack_reference(d, raw)
    context_prior = _optional_num(d, f"{label}_context_prior")
    context_upper = _optional_num(d, f"{label}_context_mature_p90")
    prior = context_prior.where(context_prior.notna(), computed_prior)
    upper = context_upper.where(context_upper.notna(), computed_upper)

    sample_reliability = np.clip(sample / RATE_RELIABILITY_MINUTES, 0.0, 1.0)
    us_support = _evidence_support(raw, understat_rate, strong=0.90, moderate=0.60)
    pre_support = _evidence_support(raw, preseason_rate, strong=0.80, moderate=0.50)
    reliability = np.maximum.reduce(
        [
            sample_reliability.to_numpy(float),
            np.asarray(us_support, dtype=float),
            np.asarray(pre_support, dtype=float),
            np.full(len(d), RATE_CREDIBILITY_FLOOR, dtype=float),
        ]
    )
    reliability = np.clip(reliability, RATE_CREDIBILITY_FLOOR, 1.0)

    # Use the empirical 90th percentile as the first-line materiality threshold.
    # If an upstream context percentile is itself permissive, a rate more than one
    # mature-prior above the mean is still treated as an extreme. This second guard
    # is scale-relative rather than a player-specific hard cap.
    scale_guard = prior + np.maximum(prior, 0.10)
    threshold = pd.concat([upper, scale_guard], axis=1).min(axis=1, skipna=True)
    eligible = (
        sample.lt(RATE_RELIABILITY_MINUTES)
        & raw.notna()
        & prior.notna()
        & threshold.notna()
        & raw.gt(threshold)
        & raw.gt(prior)
    )
    adjusted = raw.copy()
    adjusted.loc[eligible] = (
        prior.loc[eligible]
        + reliability[eligible] * (raw.loc[eligible] - prior.loc[eligible])
    )
    row_reliability = np.where(eligible, reliability, 1.0)
    return (
        pd.Series(adjusted, index=d.index).clip(lower=0.0),
        pd.Series(row_reliability, index=d.index).clip(RATE_CREDIBILITY_FLOOR, 1.0),
        pd.Series(eligible, index=d.index, dtype=bool),
    )


def _position_defcon_reference(
    d: pd.DataFrame,
    dc90: pd.Series,
    club_changed: pd.Series,
) -> pd.Series:
    """Return a mature same-position defensive-rate reference for transfer resets."""
    positions = d.get("position", pd.Series("MID", index=d.index)).astype("string")
    previous_minutes = _num(d, "previous_minutes", 0.0)
    reference = pd.Series(np.nan, index=d.index, dtype=float)
    for position in positions.dropna().unique():
        same = positions.eq(position)
        mature = (
            same
            & ~club_changed
            & previous_minutes.ge(RATE_RELIABILITY_MINUTES)
            & dc90.notna()
            & dc90.ge(0.0)
        )
        if mature.any():
            value = float(np.median(dc90.loc[mature]))
        else:
            fallback = same & dc90.notna() & dc90.ge(0.0)
            value = float(np.median(dc90.loc[fallback])) if fallback.any() else 0.0
        reference.loc[same] = value
    return reference.fillna(0.0)


def project_players(
    players: pd.DataFrame,
    fixture_mult: pd.DataFrame,
    gameweeks: list[int],
) -> pd.DataFrame:
    """Generate one transparent projection row per player/fixture."""
    rows = []
    for gw in gameweeks:
        fx_cols = [
            col
            for col in [
                "team",
                "opponent",
                "is_home",
                "attack_multiplier",
                "defence_multiplier",
                "clean_sheet_prob",
            ]
            if col in fixture_mult.columns
        ]
        fx = fixture_mult[fixture_mult["gw"] == gw][fx_cols].copy()
        fx["has_fixture"] = 1.0
        d = players.merge(fx, on="team", how="left")
        d["has_fixture"] = d["has_fixture"].fillna(0.0)
        d["attack_multiplier"] = d["attack_multiplier"].fillna(1.0)
        d["defence_multiplier"] = d["defence_multiplier"].fillna(1.0)

        em = _num(d, "expected_minutes", 70)
        min_share = np.clip(em / 90.0, 0, 1)
        p_app, p60 = _appearance_probabilities(em)
        if "appearance_probability" in d.columns:
            p_app = np.clip(_num(d, "appearance_probability", 0.8), 0, 1).to_numpy(float)
        if "minutes_60_plus_probability" in d.columns:
            p60 = np.minimum(
                p_app,
                np.clip(_num(d, "minutes_60_plus_probability", 0.6), 0, 1).to_numpy(float),
            )
        role_multiplier = np.clip(_num(d, "role_multiplier", 1.0), 0.80, 1.20)
        premins = _num(d, "preseason_minutes", 0)
        prestarts = _num(d, "preseason_starts", 0)
        preapps = _num(d, "preseason_appearances", 0)
        preseason_rate_weight = _preseason_rate_weight(premins, prestarts, preapps)
        preseason_xg90 = _optional_num(d, "preseason_xg90")
        preseason_xa90 = _optional_num(d, "preseason_xa90")
        xg90 = _blend_rate(
            _num(d, "expected_goals_per_90", 0),
            preseason_xg90,
            premins,
            prestarts,
            preapps,
        )
        xa90 = _blend_rate(
            _num(d, "expected_assists_per_90", 0),
            preseason_xa90,
            premins,
            prestarts,
            preapps,
        )
        raw_dc90 = _blend_rate(
            _num(d, "defensive_contribution_per_90", 0),
            _optional_num(d, "preseason_defcon90"),
            premins,
            prestarts,
            preapps,
        )
        club_changed = d.get("club_changed", pd.Series(False, index=d.index)).fillna(False).astype(bool)
        transfer_evidence = _num(d, "transfer_current_role_evidence", 0.0).clip(0.0, 1.0)
        defensive_reliability = pd.Series(
            np.where(club_changed, 0.35 + 0.65 * transfer_evidence, 1.0),
            index=d.index,
        ).clip(0.35, 1.0)
        dc_reference = _position_defcon_reference(d, raw_dc90, club_changed)
        dc90 = pd.Series(
            np.where(
                club_changed,
                dc_reference + defensive_reliability * (raw_dc90 - dc_reference),
                raw_dc90,
            ),
            index=d.index,
        ).clip(lower=0.0)

        pos = d["position"].fillna("MID")
        goal_pts = pos.map({"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}).fillna(5)
        clean_pts = pos.map({"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}).fillna(0)

        us_xg90 = _optional_num(d, "understat_xg90")
        us_xa90 = _optional_num(d, "understat_xa90")
        credible_xg90, xg_reliability, xg_credibility_adjusted = _credible_attack_rate(
            d, xg90, "xg90", us_xg90, preseason_xg90
        )
        credible_xa90, xa_reliability, xa_credibility_adjusted = _credible_attack_rate(
            d, xa90, "xa90", us_xa90, preseason_xa90
        )

        matched = (
            credible_xg90.notna()
            & credible_xa90.notna()
            & us_xg90.notna()
            & us_xa90.notna()
        )
        base_signal = credible_xg90.fillna(0.0) * goal_pts + credible_xa90.fillna(0.0) * 3.0
        repricable = matched & base_signal.gt(1e-9)
        attack_xg90 = credible_xg90.copy()
        attack_xa90 = credible_xa90.copy()
        attack_xg90.loc[repricable] = (
            (1.0 - UNDERSTAT_XG_WEIGHT) * credible_xg90.loc[repricable]
            + UNDERSTAT_XG_WEIGHT * us_xg90.loc[repricable]
        )
        attack_xa90.loc[repricable] = (
            (1.0 - UNDERSTAT_XA_WEIGHT) * credible_xa90.loc[repricable]
            + UNDERSTAT_XA_WEIGHT * us_xa90.loc[repricable]
        )

        xg_signal = np.maximum(attack_xg90.to_numpy(float) * goal_pts.to_numpy(float), 0.0)
        xa_signal = np.maximum(attack_xa90.to_numpy(float) * 3.0, 0.0)
        attack_signal_total = xg_signal + xa_signal
        attack_reliability = np.divide(
            xg_signal * xg_reliability.to_numpy(float)
            + xa_signal * xa_reliability.to_numpy(float),
            np.maximum(attack_signal_total, 1e-12),
            out=np.ones(len(d), dtype=float),
            where=attack_signal_total > 1e-12,
        )

        appearance = p_app + p60
        attack = (
            min_share
            * d["attack_multiplier"]
            * role_multiplier
            * (attack_xg90 * goal_pts + attack_xa90 * 3.0)
        )
        if "clean_sheet_prob" in d.columns:
            cs_prob = pd.to_numeric(d["clean_sheet_prob"], errors="coerce").fillna(0.30)
            cs_prob = np.clip(cs_prob, 0.04, 0.72)
        else:
            cs_prob = np.clip(0.30 * d["defence_multiplier"], 0.08, 0.60)
        clean = p60 * clean_pts * cs_prob
        defensive = expected_defensive_contribution_points(pos, dc90, min_share)

        saves90 = _num(d, "saves_per_90", 0)
        save_points = np.where(pos.eq("GK"), min_share * saves90 / 3.0, 0.0)
        # Bonus must use the same credibility-adjusted attacking rates as the direct
        # attack component; otherwise an unsupported rate can leak back into xP.
        bonus_proxy = expected_bonus_proxy(d, min_share, attack_xg90, attack_xa90, dc90)

        official_pen = _order_share(_num(d, "penalties_order", 99))
        official_corner_indirect = _order_share(
            _num(d, "corners_and_indirect_freekicks_order", 99)
        )
        official_direct = _order_share(_num(d, "direct_freekicks_order", 99))
        penalty_share = _with_override(official_pen, _optional_num(d, "penalty_share"))
        corners_share = _with_override(
            official_corner_indirect, _optional_num(d, "corners_share")
        )
        indirect_share = _with_override(
            official_corner_indirect, _optional_num(d, "indirect_freekick_share")
        )
        direct_share = _with_override(official_direct, _optional_num(d, "direct_freekick_share"))
        set_piece = (
            0.34 * penalty_share
            + 0.09 * corners_share
            + 0.07 * indirect_share
            + 0.12 * direct_share
        ) * min_share * role_multiplier

        fixture = d["has_fixture"].to_numpy(float)
        appearance = appearance * fixture
        attack = attack * fixture
        clean = clean * fixture
        defensive = defensive * fixture
        save_points = save_points * fixture
        bonus_proxy = bonus_proxy * fixture
        set_piece = set_piece * fixture
        xp = appearance + attack + clean + defensive + save_points + bonus_proxy + set_piece

        stable_components = np.maximum(
            np.asarray(appearance + clean + save_points + set_piece, dtype=float),
            0.0,
        )
        attack_component = np.maximum(np.asarray(attack, dtype=float), 0.0)
        defensive_component = np.maximum(np.asarray(defensive, dtype=float), 0.0)
        bonus_component = np.maximum(np.asarray(bonus_proxy, dtype=float), 0.0)
        bonus_reliability = np.clip(
            0.50
            + 0.50
            * np.minimum(
                np.asarray(attack_reliability, dtype=float),
                defensive_reliability.to_numpy(float),
            ),
            0.50,
            1.0,
        )
        reliability_numerator = (
            stable_components
            + attack_component * np.asarray(attack_reliability, dtype=float)
            + defensive_component * defensive_reliability.to_numpy(float)
            + bonus_component * bonus_reliability
        )
        apex_model_reliability = np.divide(
            reliability_numerator,
            np.maximum(np.asarray(xp, dtype=float), 1e-12),
            out=np.ones(len(d), dtype=float),
            where=np.asarray(xp, dtype=float) > 1e-12,
        )
        apex_model_reliability = np.clip(apex_model_reliability, 0.15, 1.0)

        variance = np.where(
            fixture > 0,
            np.maximum(0.8, 0.45 * xp + (1 - min_share) * 2.2),
            0.01,
        )

        for idx, row in d.reset_index(drop=True).iterrows():
            rows.append(
                {
                    "player_id": int(row["player_id"]),
                    "gw": gw,
                    "opponent": int(row["opponent"])
                    if "opponent" in row and pd.notna(row["opponent"])
                    else None,
                    "is_home": bool(row["is_home"])
                    if "is_home" in row and pd.notna(row["is_home"])
                    else None,
                    "apex_xp": max(_at(xp, idx), 0.0),
                    "apex_sd": math.sqrt(max(_at(variance, idx), 0.01)),
                    "xp_appearance": max(_at(appearance, idx), 0.0),
                    "xp_attack": max(_at(attack, idx), 0.0),
                    "xp_clean_sheet": max(_at(clean, idx), 0.0),
                    "xp_defensive_contribution": max(_at(defensive, idx), 0.0),
                    "xp_saves": max(_at(save_points, idx), 0.0),
                    "xp_bonus_prior": max(_at(bonus_proxy, idx), 0.0),
                    "xp_set_piece_prior": max(_at(set_piece, idx), 0.0),
                    "model_xg90": max(_at(xg90, idx), 0.0),
                    "model_xa90": max(_at(xa90, idx), 0.0),
                    "attack_model_xg90": max(_at(attack_xg90, idx), 0.0),
                    "attack_model_xa90": max(_at(attack_xa90, idx), 0.0),
                    "xg_rate_credibility_adjusted": bool(xg_credibility_adjusted.iloc[idx]),
                    "xa_rate_credibility_adjusted": bool(xa_credibility_adjusted.iloc[idx]),
                    "raw_defensive_contribution_per_90": max(_at(raw_dc90, idx), 0.0),
                    "model_defensive_contribution_per_90": max(_at(dc90, idx), 0.0),
                    "attack_rate_reliability": _at(attack_reliability, idx),
                    "defensive_rate_reliability": _at(defensive_reliability, idx),
                    "apex_model_reliability": _at(apex_model_reliability, idx),
                    "club_changed": bool(club_changed.iloc[idx]),
                    "transfer_current_role_evidence": _at(transfer_evidence, idx),
                    "preseason_rate_weight": max(_at(preseason_rate_weight, idx), 0.0),
                    "understat_player_matched": bool(_at(matched.astype(float), idx)),
                    "understat_player_repricable": bool(_at(repricable.astype(float), idx)),
                    "penalty_share": _at(penalty_share, idx),
                    "corners_share": _at(corners_share, idx),
                    "direct_freekick_share": _at(direct_share, idx),
                    "indirect_freekick_share": _at(indirect_share, idx),
                }
            )
    return pd.DataFrame(rows)
