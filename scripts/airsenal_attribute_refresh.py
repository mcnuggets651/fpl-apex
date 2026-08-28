#!/usr/bin/env python3
"""Idempotent mutable-window maintenance for the cached AIrsenal SQLite DB.

AIrsenal intentionally rebuilds player attributes from and including the last
completed gameweek because prices, availability and other FPL fields may change
between a match and the next deadline. Its SQLAlchemy session is configured with
``autoflush=False``; on a restored cache this can leave an existing/pending row
colliding with a second insert for the same (player, season, gameweek) key.

Apex therefore rewinds only the exact current-season window that upstream intends
to rebuild, then lets the pinned AIrsenal API refiller reconstruct it from fresh
Official FPL data. Rows before the rewind point and every other season are kept.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def rewind_player_attributes(
    db_path: str | Path,
    *,
    season: str,
    from_gameweek: int,
) -> int:
    """Delete the mutable current-season attribute window transactionally.

    Returns the number of removed rows. ``from_gameweek`` is inclusive and must
    be >= 1. The function is intentionally idempotent: a second call before the
    refill removes zero rows.
    """
    if not season or not str(season).strip():
        raise ValueError("season must be non-empty")
    if int(from_gameweek) < 1:
        raise ValueError("from_gameweek must be >= 1")

    path = Path(db_path)
    if not path.is_file():
        raise FileNotFoundError(path)

    with sqlite3.connect(path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_attributes'"
        ).fetchone()
        if exists is None:
            raise RuntimeError("AIrsenal database is missing player_attributes table")

        before = connection.total_changes
        connection.execute(
            "DELETE FROM player_attributes WHERE season = ? AND gameweek >= ?",
            (str(season), int(from_gameweek)),
        )
        removed = connection.total_changes - before
        connection.commit()
    return int(removed)
