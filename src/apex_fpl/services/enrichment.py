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
        for col in ["preseason_minutes", "preseason_starts", "preseason_xg90", "preseason_xa90", "preseason_defcon90"]:
            players[col] = 0.0
        return players
    f = friendlies.copy()
    for col in ["minutes_played", "xg", "xa", "defensive_contributions", "start_min"]:
        if col in f.columns:
            f[col] = pd.to_numeric(f[col], errors="coerce")
    f["is_start"] = (f.get("start_min", pd.Series(0, index=f.index)).fillna(0) <= 1).astype(int)
    agg = f.groupby("player_id", as_index=False).agg(
        preseason_minutes=("minutes_played", "sum"),
        preseason_starts=("is_start", "sum"),
        preseason_xg=("xg", "sum"),
        preseason_xa=("xa", "sum"),
        preseason_defcon=("defensive_contributions", "sum"),
        preseason_appearances=("match_id", "nunique"),
    )
    mins = np.maximum(pd.to_numeric(agg["preseason_minutes"], errors="coerce").fillna(0), 1)
    agg["preseason_xg90"] = pd.to_numeric(agg["preseason_xg"], errors="coerce").fillna(0) * 90 / mins
    agg["preseason_xa90"] = pd.to_numeric(agg["preseason_xa"], errors="coerce").fillna(0) * 90 / mins
    agg["preseason_defcon90"] = pd.to_numeric(agg["preseason_defcon"], errors="coerce").fillna(0) * 90 / mins
    keep = ["player_id", "preseason_minutes", "preseason_starts", "preseason_appearances", "preseason_xg90", "preseason_xa90", "preseason_defcon90"]
    return players.merge(agg[keep], on="player_id", how="left").fillna({c: 0 for c in keep if c != "player_id"})
