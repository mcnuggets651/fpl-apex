from __future__ import annotations

import numpy as np
import pandas as pd


def _num(df: pd.DataFrame, col: str, default: float = 0.0) -> pd.Series:
    if col not in df.columns:
        return pd.Series(default, index=df.index, dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default)


def expected_bonus_proxy(
    df: pd.DataFrame,
    minutes_share: pd.Series,
    xg90: pd.Series,
    xa90: pd.Series,
    defensive90: pd.Series,
) -> pd.Series:
    """Return a conservative expected bonus-points prior for 2026/27.

    Exact FPL bonus requires jointly predicting all 22 players' Opta actions, so
    Apex deliberately treats bonus as a modest prior rather than deterministic
    points. The proxy reflects the official 2026/27 BPS changes:

    - players are no longer penalised in BPS for being tackled, improving the
      relative outlook for dribbling attackers/full-backs;
    - clearances/blocks/interceptions now earn 1 BPS per three actions rather than
      per two, reducing the bonus overlap for defence-heavy centre-backs;
    - goalkeepers get 2 BPS for any save plus extra BPS for inside-box/big-chance
      saves, so a valid saves/90 signal is explicitly rewarded.

    Historical/current BPS remains the strongest observable prior, but the role
    adjustment stops Apex from applying last season's BPS profile blindly.
    """
    mins = np.maximum(_num(df, "minutes", 0.0), 1.0)
    bps_per90 = _num(df, "bps", 0.0) * 90.0 / mins
    bps_strength = np.clip(bps_per90 / 30.0, 0.0, 1.20)
    attack_strength = np.clip((1.25 * xg90 + 0.95 * xa90) / 0.80, 0.0, 1.10)
    saves90 = _num(df, "saves_per_90", 0.0)
    save_strength = np.clip(saves90 / 5.0, 0.0, 1.10)

    roles = df.get(
        "tactical_role",
        pd.Series("", index=df.index, dtype="string"),
    ).astype(str).str.casefold()
    position = df.get("position", pd.Series("MID", index=df.index)).astype(str)

    role_adjustment = pd.Series(0.0, index=df.index, dtype=float)
    attacking_role = roles.str.contains(
        "wing-back|full-back|advanced|winger|creative|striker|wide / creative",
        regex=True,
    )
    role_adjustment.loc[attacking_role] += 0.07

    centre_back_like = roles.str.contains("central / defensive defender", regex=False)
    heavy_defence = pd.to_numeric(defensive90, errors="coerce").fillna(0) >= 9.0
    role_adjustment.loc[centre_back_like & heavy_defence] -= 0.08

    goalkeeper_boost = np.where(position.eq("GK"), 0.16 * save_strength, 0.0)
    proxy = (
        0.06
        + 0.42 * bps_strength
        + 0.20 * attack_strength
        + goalkeeper_boost
        + role_adjustment
    )
    # Bonus only exists if the player participates. Keep the prior small enough
    # that the explicit goal/assist/clean-sheet/DC models still drive selection.
    return pd.Series(
        np.clip(proxy, 0.0, 1.05) * np.clip(minutes_share, 0.0, 1.0),
        index=df.index,
        name="bonus_proxy",
    )
