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
    """Return reliability-weighted influence for preseason per-90 rates.

    Minutes alone are not enough to make one exceptional friendly a season-sized
    attacking prior. When team-sheet evidence is available, weight grows with
    effective starts/appearances and then with minutes. The 35% ceiling is the
    incumbent production ceiling; this change only makes the path to that ceiling
    sample-reliability aware.
    """
    mins = pd.to_numeric(preseason_minutes, errors="coerce").fillna(0.0)
    if preseason_starts is None or preseason_appearances is None:
        return pd.Series(np.clip(mins / 270.0, 0.0, 0.35), index=mins.index)

    starts = pd.to_numeric(preseason_starts, errors="coerce").fillna(0.0)
    apps = pd.to_numeric(preseason_appearances, errors="coerce").fillna(0.0)
    effective_games = starts + 0.25 * np.maximum(apps - starts, 0.0)
    sample_reliability = 1.0 - np.exp(-effective_games / 1.8)
    minutes_reliability = np.clip(mins / 270.0, 0.0, 1.0)
    weight = 0.35 * sample_reliability * (0.70 + 0.30 * minutes_reliability)
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
    # Missing preseason return data is not a measured zero. Minutes may still be
    # useful for role/start evidence, but cannot pull an attacking rate down unless
    # that return statistic was actually observed by the source. Observed rates are
    # reliability-weighted by effective team-sheet sample, not minutes alone.
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
    """Do not turn an ordinal set-piece rank into fabricated probability.

    Official FPL's order fields say who is first/second/third in a hierarchy. They
    do not say that rank 1 takes 100%, rank 2 takes 45% or rank 3 takes 15% of future
    events. Production therefore gives ordinal rank zero additive share. A literal
    share may enter only through the separately sourced override columns.
    """
    return pd.Series(0.0, index=order.index, dtype=float)


def _with_override(official_share: pd.Series, override: pd.Series) -> pd.Series:
    clean = pd.to_numeric(override, errors="coerce")
    return clean.where(clean.notna(), official_share).clip(0, 1)


def _at(values, idx: int) -> float:
    if hasattr(values, "iloc"):
        return float(values.iloc[idx])
    return float(values[idx])


def project_players(
    players: pd.DataFrame,
    fixture_mult: pd.DataFrame,
    gameweeks: list[int],
) -> pd.DataFrame:
    """Generate one transparent projection row per player/fixture.

    This function is intentionally data-source agnostic. Production enrichment is
    responsible for supplying optional ``understat_xg90``/``understat_xa90``
    columns. If they are absent, the baseline Apex attacking rates are preserved.
    """
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
            p_app = np.clip(
                _num(d, "appearance_probability", 0.8), 0, 1
            ).to_numpy(float)
        if "minutes_60_plus_probability" in d.columns:
            p60 = np.minimum(
                p_app,
                np.clip(
                    _num(d, "minutes_60_plus_probability", 0.6), 0, 1
                ).to_numpy(float),
            )
        role_multiplier = np.clip(_num(d, "role_multiplier", 1.0), 0.80, 1.20)
        premins = _num(d, "preseason_minutes", 0)
        prestarts = _num(d, "preseason_starts", 0)
        preapps = _num(d, "preseason_appearances", 0)
        preseason_rate_weight = _preseason_rate_weight(premins, prestarts, preapps)
        xg90 = _blend_rate(
            _num(d, "expected_goals_per_90", 0),
            _optional_num(d, "preseason_xg90"),
            premins,
            prestarts,
            preapps,
        )
        xa90 = _blend_rate(
            _num(d, "expected_assists_per_90", 0),
            _optional_num(d, "preseason_xa90"),
            premins,
            prestarts,
            preapps,
        )
        dc90 = _blend_rate(
            _num(d, "defensive_contribution_per_90", 0),
            _optional_num(d, "preseason_defcon90"),
            premins,
            prestarts,
            preapps,
        )
        pos = d["position"].fillna("MID")
        goal_pts = pos.map({"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}).fillna(5)
        clean_pts = pos.map({"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}).fillna(0)

        # Apply the exact validated 50% xG / 30% xA player blend to the direct
        # attacking signal only when the pipeline supplied a matched Understat rate.
        # The separate bonus prior deliberately retains baseline model rates, exactly
        # matching the sealed A/B contract.
        us_xg90 = _optional_num(d, "understat_xg90")
        us_xa90 = _optional_num(d, "understat_xa90")
        matched = xg90.notna() & xa90.notna() & us_xg90.notna() & us_xa90.notna()
        base_signal = xg90.fillna(0.0) * goal_pts + xa90.fillna(0.0) * 3.0
        repricable = matched & base_signal.gt(1e-9)
        attack_xg90 = xg90.copy()
        attack_xa90 = xa90.copy()
        attack_xg90.loc[repricable] = (
            (1.0 - UNDERSTAT_XG_WEIGHT) * xg90.loc[repricable]
            + UNDERSTAT_XG_WEIGHT * us_xg90.loc[repricable]
        )
        attack_xa90.loc[repricable] = (
            (1.0 - UNDERSTAT_XA_WEIGHT) * xa90.loc[repricable]
            + UNDERSTAT_XA_WEIGHT * us_xa90.loc[repricable]
        )

        appearance = p_app + p60
        attack = (
            min_share
            * d["attack_multiplier"]
            * role_multiplier
            * (attack_xg90 * goal_pts + attack_xa90 * 3.0)
        )
        if "clean_sheet_prob" in d.columns:
            cs_prob = pd.to_numeric(
                d["clean_sheet_prob"], errors="coerce"
            ).fillna(0.30)
            cs_prob = np.clip(cs_prob, 0.04, 0.72)
        else:
            cs_prob = np.clip(0.30 * d["defence_multiplier"], 0.08, 0.60)
        clean = p60 * clean_pts * cs_prob
        defensive = expected_defensive_contribution_points(pos, dc90, min_share)

        saves90 = _num(d, "saves_per_90", 0)
        save_points = np.where(pos.eq("GK"), min_share * saves90 / 3.0, 0.0)

        # 2026/27 bonus potential is a separate calibrated prior. It incorporates
        # historical/current BPS but explicitly adjusts for this season's removal
        # of the tackled penalty, reduced CBI reward and stronger goalkeeper-save BPS.
        bonus_proxy = expected_bonus_proxy(d, min_share, xg90, xa90, dc90)

        # Official set-piece order is ordinal context only. `_order_share` therefore
        # contributes zero. Only current sourced override columns may create an
        # additive set-piece share. This avoids fabricated rank probabilities and
        # keeps the separate current-role adjustment distinct from historical xG/xA.
        official_pen = _order_share(_num(d, "penalties_order", 99))
        official_corner_indirect = _order_share(
            _num(d, "corners_and_indirect_freekicks_order", 99)
        )
        official_direct = _order_share(_num(d, "direct_freekicks_order", 99))
        penalty_share = _with_override(
            official_pen,
            _optional_num(d, "penalty_share"),
        )
        corners_share = _with_override(
            official_corner_indirect,
            _optional_num(d, "corners_share"),
        )
        indirect_share = _with_override(
            official_corner_indirect,
            _optional_num(d, "indirect_freekick_share"),
        )
        direct_share = _with_override(
            official_direct,
            _optional_num(d, "direct_freekick_share"),
        )
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
        xp = (
            appearance
            + attack
            + clean
            + defensive
            + save_points
            + bonus_proxy
            + set_piece
        )
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
                    "opponent": (
                        int(row["opponent"])
                        if "opponent" in row and pd.notna(row["opponent"])
                        else None
                    ),
                    "is_home": (
                        bool(row["is_home"])
                        if "is_home" in row and pd.notna(row["is_home"])
                        else None
                    ),
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
