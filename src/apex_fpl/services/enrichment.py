from __future__ import annotations

import numpy as np
import pandas as pd

# Statistical context may safely come from FPL Core. Identity fields never do.
CONTEXT_FIELDS = [
    "expected_goals_per_90",
    "expected_assists_per_90",
    "expected_goal_involvements_per_90",
    "expected_goals_conceded_per_90",
    "starts_per_90",
    "defensive_contribution_per_90",
    "saves_per_90",
    "corners_and_indirect_freekicks_order",
    "direct_freekicks_order",
    "penalties_order",
    "bps",
    "minutes",
    "starts",
    "recoveries",
    "tackles",
    "clearances_blocks_interceptions",
]


def coalesce_context(df: pd.DataFrame) -> pd.DataFrame:
    """Use auxiliary context when official current-season context is blank/zero.

    This is deliberately restricted to performance context. Club, position, price and
    player identity remain official-only.
    """
    out = df.copy()
    for field in CONTEXT_FIELDS:
        core = f"{field}_core"
        if core not in out.columns:
            continue
        ext = pd.to_numeric(out[core], errors="coerce")
        if field not in out.columns:
            out[field] = ext
            continue
        cur = pd.to_numeric(out[field], errors="coerce")
        use_ext = cur.isna() | ((cur == 0) & ext.notna() & (ext != 0))
        out.loc[use_ext, field] = ext[use_ext]
    return out


def add_preseason_features(players: pd.DataFrame, friendlies: pd.DataFrame) -> pd.DataFrame:
    if friendlies.empty:
        out = players.copy()
        out["preseason_minutes"] = 0.0
        out["preseason_starts"] = 0.0
        out["preseason_appearances"] = 0.0
        for stat in ("xg", "xa", "defcon"):
            out[f"preseason_{stat}90"] = np.nan
            out[f"preseason_{stat}_observed"] = False
        return out
    f = friendlies.copy()
    for col in ["minutes_played", "xg", "xa", "defensive_contributions", "start_min"]:
        if col in f.columns:
            f[col] = pd.to_numeric(f[col], errors="coerce")
    f["is_start"] = (f.get("start_min", pd.Series(0, index=f.index)).fillna(0) <= 1).astype(int)
    for col in ("xg", "xa", "defensive_contributions"):
        if col not in f.columns:
            f[col] = np.nan

    grouped = f.groupby("player_id", as_index=False)
    agg = grouped.agg(
        preseason_minutes=("minutes_played", "sum"),
        preseason_starts=("is_start", "sum"),
        preseason_appearances=("match_id", "nunique"),
    )
    sums = grouped[["xg", "xa", "defensive_contributions"]].sum(min_count=1)
    sums = sums.rename(
        columns={
            "xg": "preseason_xg",
            "xa": "preseason_xa",
            "defensive_contributions": "preseason_defcon",
        }
    )
    agg = agg.merge(sums, on="player_id", how="left", validate="one_to_one")
    mins = np.maximum(pd.to_numeric(agg["preseason_minutes"], errors="coerce").fillna(0), 1)
    for stat in ("xg", "xa", "defcon"):
        total = pd.to_numeric(agg[f"preseason_{stat}"], errors="coerce")
        agg[f"preseason_{stat}90"] = total * 90 / mins
        agg[f"preseason_{stat}_observed"] = total.notna()
    keep = [
        "player_id",
        "preseason_minutes",
        "preseason_starts",
        "preseason_appearances",
        "preseason_xg90",
        "preseason_xa90",
        "preseason_defcon90",
        "preseason_xg_observed",
        "preseason_xa_observed",
        "preseason_defcon_observed",
    ]
    out = players.merge(agg[keep], on="player_id", how="left")
    out[["preseason_minutes", "preseason_starts", "preseason_appearances"]] = out[
        ["preseason_minutes", "preseason_starts", "preseason_appearances"]
    ].fillna(0.0)
    for col in (
        "preseason_xg_observed",
        "preseason_xa_observed",
        "preseason_defcon_observed",
    ):
        out[col] = out[col].fillna(False).astype(bool)
    return out
