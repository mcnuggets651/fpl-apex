from __future__ import annotations

from pathlib import Path

import pandas as pd

from apex_fpl.data.core_insights import FPLCoreClient
from apex_fpl.data.http import CachedHttp
from apex_fpl.data.official import OfficialFPLClient
from apex_fpl.services.integrity import reconcile


def _ids(frame: pd.DataFrame, column: str, label: str) -> set[int]:
    if column not in frame.columns:
        raise ValueError(f"{label} lacks required {column!r} column")
    values = pd.to_numeric(frame[column], errors="coerce")
    if values.isna().any():
        raise ValueError(f"{label} contains invalid {column} values")
    return set(values.astype(int).tolist())


def validate_core_candidate_frames(
    official_players: pd.DataFrame,
    core_playerstats: pd.DataFrame,
    previous: pd.DataFrame,
) -> dict[str, object]:
    """Apply production reconciliation and all-player Core coverage semantics."""
    official_ids = _ids(official_players, "player_id", "Official FPL players")
    if len(official_ids) != len(official_players):
        raise ValueError("Official FPL player_id is not unique")

    core_ids = _ids(core_playerstats, "player_id", "FPL Core playerstats")
    missing_core = sorted(official_ids - core_ids)
    if missing_core:
        raise ValueError(
            "FPL Core candidate lacks current Official FPL player coverage: "
            f"missing={missing_core[:20]} count={len(missing_core)}"
        )

    # Reuse the exact production reconciliation path. It rejects ambiguous
    # longitudinal player/GW snapshots and non-one-to-one canonical assembly.
    reconciled, integrity = reconcile(official_players, core_playerstats)
    if len(reconciled) != len(official_players):
        raise ValueError(
            "FPL Core candidate changed the canonical player universe during reconciliation"
        )

    previous_ids = _ids(previous, "player_id", "FPL Core previous-season bridge")
    missing_bridge = sorted(official_ids - previous_ids)
    if missing_bridge:
        raise ValueError(
            "FPL Core candidate cannot bridge every current Official FPL player ID: "
            f"missing={missing_bridge[:20]} count={len(missing_bridge)}"
        )

    previous_minutes = pd.to_numeric(previous.get("previous_minutes"), errors="coerce")
    previous_coverage = float(previous_minutes.notna().mean()) if len(previous) else 0.0
    if previous_coverage < 0.70:
        raise ValueError(
            "FPL Core candidate previous-season playing-time coverage is below the "
            f"production floor: {previous_coverage:.1%} < 70.0%"
        )

    return {
        "official_players": len(official_players),
        "core_unique_player_ids": len(core_ids),
        "official_player_coverage": 1.0,
        "previous_bridge_player_coverage": 1.0,
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
