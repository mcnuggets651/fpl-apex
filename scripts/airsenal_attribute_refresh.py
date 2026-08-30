#!/usr/bin/env python3
"""Idempotent mutable-window maintenance for the cached AIrsenal SQLite DB.

AIrsenal intentionally rebuilds player attributes from and including the last
completed gameweek because prices, availability and other FPL fields may change
between a match and the next deadline. Its SQLAlchemy session is configured with
``autoflush=False``. During a live refresh the pinned refiller can encounter the
same (player, season, gameweek) twice; without an autoflush, its second lookup
cannot see the first pending insert and both collide only at final commit.

Apex therefore applies two narrowly scoped guards around the pinned refiller:
1. rewind only the exact current-season window upstream intends to rebuild;
2. temporarily enable session autoflush while that refiller runs so its own
   duplicate-key lookup/update logic can observe pending inserts.

Rows before the rewind point and every other season are kept. The session's
original autoflush configuration is always restored afterwards.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


@contextmanager
def refiller_autoflush(session: Any) -> Iterator[None]:
    """Expose pending rows to the pinned refiller's lookup/update queries.

    AIrsenal globally chooses ``autoflush=False``. Changing that global session
    policy would be a broad upstream semantic modification, so Apex enables it
    only for the attribute-refill call and restores the exact previous value on
    both success and failure.
    """
    if not hasattr(session, "autoflush"):
        raise TypeError("session must expose an autoflush attribute")
    previous = session.autoflush
    session.autoflush = True
    try:
        yield
    finally:
        session.autoflush = previous


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
