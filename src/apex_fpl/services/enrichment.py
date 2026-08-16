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

# The projection-truth audit already defines <270 competitive minutes as a low
# sample and the top positional decile as an extreme rate. Production reuses those
# existing semantics rather than introducing a player-specific threshold here.
LOW_SAMPLE_ATTACK_MINUTES = 270.0
LOW_SAMPLE_ATTACK_UPPER_QUANTILE = 0.90


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
    enriched["understat_player_matched"] = (
        pd.to_numeric(enriched["understat_xg90"], errors="coerce").notna()
        & pd.to_numeric(enriched["understat_xa90"], errors="coerce").notna()
    )
    if "understat_match_method" not in enriched.columns:
        enriched["understat_match_method"] = pd.NA
    return enriched


def _position_rate_reference(
    raw_rate: pd.Series,
    positions: pd.Series,
    previous_minutes: pd.Series,
) -> tuple[pd.Series, pd.Series]:
    """Return mature positional mean and upper-decile reference for each row."""
    prior = pd.Series(np.nan, index=raw_rate.index, dtype=float)
    upper = pd.Series(np.nan, index=raw_rate.index, dtype=float)
    for position in positions.dropna().unique():
        same_position = positions.eq(position)
        mature = (
            same_position
            & previous_minutes.ge(LOW_SAMPLE_ATTACK_MINUTES)
            & raw_rate.notna()
            & raw_rate.ge(0)
        )
        if not mature.any():
            continue
        weights = previous_minutes.loc[mature]
        prior_value = float(np.average(raw_rate.loc[mature], weights=weights))
        upper_value = float(
            raw_rate.loc[mature].quantile(LOW_SAMPLE_ATTACK_UPPER_QUANTILE)
        )
        prior.loc[same_position] = prior_value
        upper.loc[same_position] = upper_value
    return prior, upper


def stabilise_low_sample_attack_context(players: pd.DataFrame) -> pd.DataFrame:
    """Shrink only extreme pre-GW1 attacking rates backed by a tiny PL sample.

    FPL/Core preseason context can carry a prior-season per-90 rate even though the
    new season has zero competitive minutes. An extreme rate from only a few prior
    minutes must not be treated like a mature estimate. Returning players with
    1-269 prior Premier League minutes are therefore shrunk only when their rate is
    above the mature positional 90th percentile. Reliability rises linearly to one
    at the already-governed 270-minute boundary, so mature rates are exact no-ops.

    Players with no prior Premier League sample are deliberately untouched: their
    cross-league/other-source treatment belongs to the independent source model,
    not this narrow returning-player correction.
    """
    out = players.copy()
    if "position" not in out.columns or "previous_minutes" not in out.columns:
        return out

    positions = out["position"].astype("string")
    previous_minutes = pd.to_numeric(
        out["previous_minutes"], errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    current_minutes = pd.to_numeric(
        out.get("minutes", pd.Series(0.0, index=out.index)), errors="coerce"
    ).fillna(0.0).clip(lower=0.0)
    pre_gw1_context = current_minutes.le(0.0)
    reliability = (previous_minutes / LOW_SAMPLE_ATTACK_MINUTES).clip(0.0, 1.0)

    for label, field in (
        ("xg90", "expected_goals_per_90"),
        ("xa90", "expected_assists_per_90"),
    ):
        if field not in out.columns:
            continue
        raw = pd.to_numeric(out[field], errors="coerce")
        prior, upper = _position_rate_reference(raw, positions, previous_minutes)
        eligible = (
            pre_gw1_context
            & previous_minutes.gt(0.0)
            & previous_minutes.lt(LOW_SAMPLE_ATTACK_MINUTES)
            & raw.notna()
            & prior.notna()
            & upper.notna()
            & raw.ge(upper)
            & raw.gt(prior)
        )
        adjusted = prior + reliability * (raw - prior)

        out[f"{label}_context_raw"] = raw
        out[f"{label}_context_prior"] = prior
        out[f"{label}_context_mature_p90"] = upper
        out[f"{label}_context_reliability"] = reliability
        out[f"{label}_low_sample_adjusted"] = eligible.astype(bool)
        out.loc[eligible, field] = adjusted.loc[eligible]

    return out


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
    out = stabilise_low_sample_attack_context(out)
    return _enrich_understat_player_rates(out)


def add_preseason_features(players: pd.DataFrame, friendlies: pd.DataFrame) -> pd.DataFrame:
    """Attach preseason role and attacking evidence without inventing missing xG/xA.

    Core friendlies expose reliable event counts (goals, assists, shots and chances)
    even when advanced xG/xA is unavailable for a fixture. Those observations are
    retained as separate evidence for a validated fallback challenger; they do not
    silently become xG/xA in production.

    FPL Core also emits roster rows for unused players. A row is role/return evidence
    only when ``minutes_played > 0``; a start additionally requires ``start_min <= 1``.
    This prevents unused zero-minute rows with a start_min sentinel of zero from being
    counted as appearances or starts.
    """
    rate_sources = {
        "xg": "xg",
        "xa": "xa",
        "defcon": "defensive_contributions",
        "goals": "goals",
        "assists": "assists",
        "shots": "total_shots",
        "shots_on_target": "shots_on_target",
        "chances_created": "chances_created",
        "box_touches": "touches_opposition_box",
    }
    if friendlies.empty:
        out = players.copy()
        out["preseason_minutes"] = 0.0
        out["preseason_starts"] = 0.0
        out["preseason_appearances"] = 0.0
        for stat in rate_sources:
            out[f"preseason_{stat}90"] = np.nan
            out[f"preseason_{stat}_observed"] = False
        return out

    f = friendlies.copy()
    numeric_cols = ["minutes_played", "start_min", *rate_sources.values()]
    for col in numeric_cols:
        if col in f.columns:
            f[col] = pd.to_numeric(f[col], errors="coerce")
    if "minutes_played" not in f.columns:
        f["minutes_played"] = 0.0
    minutes = pd.to_numeric(f["minutes_played"], errors="coerce").fillna(0.0)
    f["is_appearance"] = minutes.gt(0).astype(int)
    start_min = pd.to_numeric(
        f.get("start_min", pd.Series(0, index=f.index)), errors="coerce"
    ).fillna(0)
    f["is_start"] = (minutes.gt(0) & start_min.le(1)).astype(int)
    for source in rate_sources.values():
        if source not in f.columns:
            f[source] = np.nan
        # Unused roster rows are not attacking/defensive evidence either. Preserve
        # measured zeroes for genuine appearances, but turn unused-row values into
        # missing observations before aggregation.
        f.loc[~minutes.gt(0), source] = np.nan

    grouped = f.groupby("player_id", as_index=False)
    agg = grouped.agg(
        preseason_minutes=("minutes_played", "sum"),
        preseason_starts=("is_start", "sum"),
        preseason_appearances=("is_appearance", "sum"),
    )
    source_columns = list(dict.fromkeys(rate_sources.values()))
    sums = grouped[source_columns].sum(min_count=1)
    rename = {source: f"preseason_{stat}" for stat, source in rate_sources.items()}
    sums = sums.rename(columns=rename)
    agg = agg.merge(sums, on="player_id", how="left", validate="one_to_one")

    mins = np.maximum(
        pd.to_numeric(agg["preseason_minutes"], errors="coerce").fillna(0),
        1,
    )
    for stat in rate_sources:
        total = pd.to_numeric(agg[f"preseason_{stat}"], errors="coerce")
        agg[f"preseason_{stat}90"] = total * 90 / mins
        agg[f"preseason_{stat}_observed"] = total.notna()

    keep = [
        "player_id",
        "preseason_minutes",
        "preseason_starts",
        "preseason_appearances",
        *[f"preseason_{stat}90" for stat in rate_sources],
        *[f"preseason_{stat}_observed" for stat in rate_sources],
    ]
    out = players.merge(agg[keep], on="player_id", how="left")
    out[["preseason_minutes", "preseason_starts", "preseason_appearances"]] = out[
        ["preseason_minutes", "preseason_starts", "preseason_appearances"]
    ].fillna(0.0)
    for stat in rate_sources:
        col = f"preseason_{stat}_observed"
        out[col] = out[col].fillna(False).astype(bool)
    return out