#!/usr/bin/env python3
"""Export one genuine AIrsenal prediction tag into the Apex forecast contract.

Usage:
    python scripts/export_airsenal.py AIRSENAL.sqlite TAG output.csv

`TAG` may be a literal AIrsenal prediction tag or `LATEST`.

Important identity rule: ``player_prediction.player_id`` is AIrsenal's internal
primary key, *not* the official FPL element ID. The exporter therefore joins the
``player`` table and emits ``player.fpl_api_id``. This prevents an internal
AIrsenal ID from ever being mistaken for a canonical FPL player ID.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys


def _latest_tag(db: sqlite3.Connection) -> str:
    row = db.execute(
        """
        SELECT tag
        FROM player_prediction
        WHERE tag IS NOT NULL AND tag != ''
        GROUP BY tag
        ORDER BY MAX(id) DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        raise SystemExit("No AIrsenal prediction tags exist in the database")
    return str(row[0])


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python scripts/export_airsenal.py AIRSENAL.sqlite TAG output.csv"
        )

    db_path, requested_tag, output = sys.argv[1:4]
    db = sqlite3.connect(db_path)
    try:
        tag = _latest_tag(db) if requested_tag.upper() == "LATEST" else requested_tag
        rows = db.execute(
            """
            SELECT p.fpl_api_id, f.gameweek, SUM(pp.predicted_points)
            FROM player_prediction AS pp
            JOIN player AS p ON p.player_id = pp.player_id
            JOIN fixture AS f ON f.fixture_id = pp.fixture_id
            WHERE pp.tag = ?
              AND f.gameweek IS NOT NULL
              AND p.fpl_api_id IS NOT NULL
            GROUP BY p.fpl_api_id, f.gameweek
            ORDER BY p.fpl_api_id, f.gameweek
            """,
            (tag,),
        ).fetchall()
    finally:
        db.close()

    if not rows:
        raise SystemExit(f"No official-ID AIrsenal predictions found for tag {tag!r}")

    generated_at = datetime.now(timezone.utc).isoformat()
    source_version = os.getenv("AIRSENAL_SOURCE_VERSION", "")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "player_id",
                "gw",
                "xp",
                "generated_at",
                "source_version",
                "prediction_tag",
            ]
        )
        writer.writerows(
            (int(player_id), int(gameweek), float(xp), generated_at, source_version, tag)
            for player_id, gameweek, xp in rows
        )

    unique_players = len({int(row[0]) for row in rows})
    gameweeks = sorted({int(row[1]) for row in rows})
    print(
        f"Exported {len(rows)} player-gameweek rows for {unique_players} official FPL "
        f"players, GW={gameweeks}, tag={tag!r}, to {path}"
    )


if __name__ == "__main__":
    main()
