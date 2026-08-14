from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd

from apex_fpl.data.understat import fetch_understat_season, season_start_year
from apex_fpl.evaluation.understat_player_ab import map_understat_to_current_ids
from apex_fpl.evaluation.understat_players import normalise_understat_players

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


def _understat_player_mode() -> str:
    mode = os.getenv("APEX_UNDERSTAT_PLAYER_MODEL_MODE", "production").strip().casefold()
    if mode not in {"shadow", "production"}:
        raise RuntimeError(
            "APEX_UNDERSTAT_PLAYER_MODEL_MODE must be 'shadow' or 'production'"
        )
    return mode


def _enrich_understat_player_rates(out: pd.DataFrame) -> pd.DataFrame:
    """Attach the validated prior-season Understat player rates to real Core rows.

    Acquisition and conservative identity mapping live here, not in the projection
    model. The A/B baseline sets ``APEX_UNDERSTAT_PLAYER_MODEL_MODE=shadow`` and
    therefore receives no player-rate enrichment. Production defaults to
    ``production`` and fails closed once genuine Core attacking context is present
    but the promoted Understat surface cannot be constructed.
    """
    if _understat_player_mode() != "production":
        return out

    # Synthetic/unit-test contexts intentionally do not carry genuine FPL Core
    # attacking fields. Do not turn these pure/model tests into network tests.
    genuine_core_context = {
        "player_id",
        "first_name",
        "second_name",
        "expected_goals_per_90_core",
        "expected_assists_per_90_core",
    }
    if not genuine_core_context.issubset(out.columns):
        return out

    season = os.getenv("APEX_SEASON", "2026-2027")
    previous_year = season_start_year(season) - 1
    payload = fetch_understat_season(
        previous_year,
        cache_dir=Path("data/cache/understat"),
        refresh=False,
    )
    understat = normalise_understat_players(payload, previous_year)
    identity_cols = [
        col
        for col in [
            "player_id",
            "first_name",
            "second_name",
            "web_name",
            "team_name",
        ]
        if col in out.columns
    ]
    rates = map_understat_to_current_ids(
        out[identity_cols].drop_duplicates("player_id"),
        understat,
    )
    if rates.empty:
        raise RuntimeError(
            "Understat player production enrichment produced no matched players"
        )

    enriched = out.merge(
        rates,
        on="player_id",
        how="left",
        validate="one_to_one",
    )
    matched = int(
        enriched[["understat_xg90", "understat_xa90"]].notna().all(axis=1).sum()
    )
    if matched < 1:
        raise RuntimeError(
            "Understat player production enrichment has zero usable mapped rows"
        )
    return enriched


def coalesce_context(df: pd.DataFrame) -> pd.DataFrame:
    """Use auxiliary context when official current-season context is blank/zero.

    This is deliberately restricted to performance context. Club, position, price and
    player identity remain official-only. Production player-level Understat rates are
    attached here so downstream projection remains data-source agnostic.
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
    return _enrich_understat_player_rates(out)


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
