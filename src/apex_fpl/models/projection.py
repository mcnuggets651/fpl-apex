from __future__ import annotations

import math

import numpy as np
import pandas as pd

from apex_fpl.models.defcon import expected_defensive_contribution_points


def _num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def _blend_rate(primary: pd.Series, preseason: pd.Series, preseason_minutes: pd.Series) -> pd.Series:
    p = pd.to_numeric(primary, errors="coerce").fillna(0)
    pre = pd.to_numeric(preseason, errors="coerce").fillna(0)
    mins = pd.to_numeric(preseason_minutes, errors="coerce").fillna(0)
    pre_weight = np.clip(mins / 270.0, 0, 0.35)
    # Never let tiny preseason samples erase established context.
    return p * (1 - pre_weight) + pre * pre_weight


def _appearance_probabilities(expected_mins: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    em = pd.to_numeric(expected_mins, errors="coerce").fillna(0).to_numpy(float)
    # Approximate probability of taking the pitch and reaching 60 minutes from
    # the expected-minutes signal. This avoids a hard 59/60 discontinuity.
    p_app = np.clip(em / 28.0, 0, 1)
    p60 = np.where(em <= 0, 0.0, 1.0 / (1.0 + np.exp(-(em - 58.0) / 8.0)))
    p60 = np.minimum(p60, p_app)
    return p_app, p60


def project_players(players: pd.DataFrame, fixture_mult: pd.DataFrame, gameweeks: list[int]) -> pd.DataFrame:
    rows = []
    for gw in gameweeks:
        fx_cols = [
            c for c in ["team", "attack_multiplier", "defence_multiplier", "clean_sheet_prob"]
            if c in fixture_mult.columns
        ]
        fx = fixture_mult[fixture_mult["gw"] == gw][fx_cols].copy()
        fx["has_fixture"] = 1.0
        # A left merge deliberately creates one row per fixture in a DGW. A
        # blank-GW player gets has_fixture=0 and therefore exactly zero xP.
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
            p60 = np.minimum(p_app, np.clip(_num(d, "minutes_60_plus_probability", 0.6), 0, 1).to_numpy(float))
        role_multiplier = np.clip(_num(d, "role_multiplier", 1.0), 0.80, 1.20)
        premins = _num(d, "preseason_minutes", 0)
        xg90 = _blend_rate(
            _num(d, "expected_goals_per_90", 0), _num(d, "preseason_xg90", 0), premins
        )
        xa90 = _blend_rate(
            _num(d, "expected_assists_per_90", 0), _num(d, "preseason_xa90", 0), premins
        )
        dc90 = _blend_rate(
            _num(d, "defensive_contribution_per_90", 0),
            _num(d, "preseason_defcon90", 0),
            premins,
        )
        pos = d["position"].fillna("MID")
        goal_pts = pos.map({"GK": 10, "DEF": 6, "MID": 5, "FWD": 4}).fillna(5)
        clean_pts = pos.map({"GK": 4, "DEF": 4, "MID": 1, "FWD": 0}).fillna(0)

        appearance = p_app + p60
        attack = min_share * d["attack_multiplier"] * role_multiplier * (xg90 * goal_pts + xa90 * 3.0)
        # FPL clean-sheet points require 60+ minutes, so use p60 rather than a
        # simple minutes fraction.
        if "clean_sheet_prob" in d.columns:
            cs_prob = pd.to_numeric(d["clean_sheet_prob"], errors="coerce").fillna(0.30)
            cs_prob = np.clip(cs_prob, 0.04, 0.72)
        else:
            cs_prob = np.clip(0.30 * d["defence_multiplier"], 0.08, 0.60)
        clean = p60 * clean_pts * cs_prob
        defensive = expected_defensive_contribution_points(pos, dc90, min_share)

        # Goalkeeper save points: one point per three saves. This becomes active
        # once current/historical saves_per_90 is available; it is zero rather
        # than invented when no evidence exists.
        saves90 = _num(d, "saves_per_90", 0)
        save_points = np.where(pos.eq("GK"), min_share * saves90 / 3.0, 0.0)

        # BPS proxy is deliberately capped; exact bonus requires predicting all
        # 22 players' Opta events jointly, so this remains a calibrated prior.
        bonus_proxy = min_share * np.clip(
            (_num(d, "bps", 0) / np.maximum(_num(d, "minutes", 1), 1)) * 3.2, 0, 1.0
        )
        set_piece = (
            (_num(d, "penalties_order", 99) == 1).astype(float) * 0.35
            + (_num(d, "corners_and_indirect_freekicks_order", 99) == 1).astype(float) * 0.18
            + (_num(d, "direct_freekicks_order", 99) == 1).astype(float) * 0.12
        ) * min_share * role_multiplier

        fixture = d["has_fixture"].to_numpy(float)
        xp = (appearance + attack + clean + defensive + save_points + bonus_proxy + set_piece) * fixture
        variance = np.where(
            fixture > 0,
            np.maximum(0.8, 0.45 * xp + (1 - min_share) * 2.2),
            0.01,
        )
        for idx, r in d.reset_index(drop=True).iterrows():
            rows.append(
                {
                    "player_id": int(r["player_id"]),
                    "gw": gw,
                    "apex_xp": float(max(xp.iloc[idx] if hasattr(xp, "iloc") else xp[idx], 0)),
                    "apex_sd": float(math.sqrt(max(variance.iloc[idx] if hasattr(variance, "iloc") else variance[idx], 0.01))),
                }
            )
    return pd.DataFrame(rows)
