from __future__ import annotations

from pathlib import Path

import pandas as pd

from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.services.data_quality import (
    MAX_CORE_REGISTRATION_LAG_PLAYERS,
    MIN_CORE_REGISTRATION_LAG_COVERAGE,
)
from apex_fpl.services.integrity import reconcile


def _ids(frame: pd.DataFrame, column: str, label: str) -> set[int]:
    if column not in frame.columns:
        raise ValueError(f"{label} lacks required {column!r} column")
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"{label} contains invalid {column} values")
    return set(values.astype(int).tolist())


def _bounded_registration_lag(official_ids: set[int], core_ids: set[int]) -> tuple[bool, list[int], float]:
    """Return whether missing Core IDs are the governed append-only registration lag."""
    if not official_ids:
        return False, [], 0.0
    missing = sorted(official_ids - core_ids)
    coverage = len(official_ids & core_ids) / len(official_ids)
    if not missing:
        return True, missing, coverage
    max_core_id = max(core_ids) if core_ids else None
    trailing_only = bool(
        max_core_id is not None and all(player_id > max_core_id for player_id in missing)
    )
    bounded = (
        len(missing) <= MAX_CORE_REGISTRATION_LAG_PLAYERS
        and coverage >= MIN_CORE_REGISTRATION_LAG_COVERAGE
    )
    return bool(trailing_only and bounded), missing, coverage


def validate_core_candidate_frames(
    official_players: pd.DataFrame,
    core_playerstats: pd.DataFrame,
    previous: pd.DataFrame,
) -> dict[str, object]:
    """Apply production reconciliation and bounded Core registration-lag semantics.

    Official FPL remains canonical identity. The publication validator must not be
    stricter than the production quality contract for the one explicitly governed
    race condition where Official FPL appends a tiny trailing block of new player
    IDs before FPL Core has ingested them. Interior holes, large gaps, ambiguous
    snapshots, or missing bridges for already-covered Core players still fail closed.
    """
    official_ids = _ids(official_players, "player_id", "Official FPL players")
    if len(official_ids) != len(official_players):
        raise ValueError("Official FPL player_id is not unique")

    core_ids = _ids(core_playerstats, "player_id", "FPL Core playerstats")
    lag_ok, missing_core, core_coverage = _bounded_registration_lag(official_ids, core_ids)
    if missing_core and not lag_ok:
        raise ValueError(
            "FPL Core candidate lacks current Official FPL player coverage outside "
            "the bounded trailing registration-lag policy: "
            f"missing={missing_core[:20]} count={len(missing_core)} "
            f"coverage={core_coverage:.1%}"
        )

    # Reuse the exact production reconciliation path. It rejects ambiguous
    # longitudinal player/GW snapshots and preserves Official FPL as canonical
    # identity even for a bounded trailing registration lag.
    reconciled, integrity = reconcile(official_players, core_playerstats)
    if len(reconciled) != len(official_players):
        raise ValueError(
            "FPL Core candidate changed the canonical player universe during reconciliation"
        )

    previous_ids = _ids(previous, "player_id", "FPL Core previous-season bridge")
    missing_bridge = sorted(official_ids - previous_ids)
    unexpected_missing_bridge = sorted(set(missing_bridge) - set(missing_core))
    if unexpected_missing_bridge:
        raise ValueError(
            "FPL Core candidate cannot bridge current Official FPL player IDs already "
            "covered by Core: "
            f"missing={unexpected_missing_bridge[:20]} count={len(unexpected_missing_bridge)}"
        )

    previous_minutes = pd.to_numeric(previous.get("previous_minutes"), errors="coerce")
    previous_coverage = float(previous_minutes.notna().mean()) if len(previous) else 0.0
    if previous_coverage < 0.70:
        raise ValueError(
            "FPL Core candidate previous-season playing-time coverage is below the "
            f"production floor: {previous_coverage:.1%} < 70.0%"
        )

    bridge_coverage = len(official_ids & previous_ids) / len(official_ids) if official_ids else 0.0
    return {
        "official_players": len(official_players),
        "core_unique_player_ids": len(core_ids),
        "official_player_coverage": core_coverage,
        "bounded_registration_lag": bool(missing_core),
        "bounded_registration_lag_missing_ids": missing_core,
        "previous_bridge_player_coverage": bridge_coverage,
        "previous_minutes_coverage": previous_coverage,
        "identity_mismatch_warnings": int(len(integrity)),
    }


def validate_core_candidate(
    ref: str,
    season: str,
    cache_dir: Path,
) -> dict[str, object]:
    """Validate one immutable Core revision against the live Official FPL universe."""
    http = CachedHttp(cache_dir)
    official = OfficialFPLClient(http).snapshot(force=True)
    core = FPLCoreClient(http, season, ref=ref)
    playerstats = core.playerstats(force=True)
    previous = core.previous_season_playerstats(force=True)
    summary = validate_core_candidate_frames(official.players, playerstats, previous)
    summary.update({"candidate_ref": ref, "season": season})
    return summary
