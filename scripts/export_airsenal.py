#!/usr/bin/env python3
"""Export one genuine AIrsenal prediction tag into the Apex forecast contract.

Usage:
    python scripts/export_airsenal.py AIRSENAL.sqlite TAG output.csv

`TAG` may be a literal AIrsenal prediction tag or `LATEST`.

Important identity rule: ``player_prediction.player_id`` is AIrsenal's internal
primary key, *not* the official FPL element ID. The exporter joins the ``player``
table and emits ``player.fpl_api_id`` plus AIrsenal's independent player name when
that schema field is available. The witness type is explicit so downstream audits
can fail closed rather than mistaking a compatibility placeholder for evidence.

Official FPL IDs are identifiers, not quantities. They are validated with the same
exact parser used by the downstream identity audit before any output file is opened,
so a malformed upstream value such as ``10.5`` can never be truncated into player 10
and then appear valid downstream.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import os
from pathlib import Path
import sqlite3
import sys

from apex_fpl.services.player_identity import IdentityIntegrityError, parse_exact_player_id


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


def _player_name_expression(db: sqlite3.Connection) -> tuple[str, str]:
    columns = {str(row[1]) for row in db.execute("PRAGMA table_info(player)").fetchall()}
    for candidate in ("name", "player_name"):
        if candidate in columns:
            return f"p.{candidate}", "airsenal_name"
    # Compatibility with minimal historical test fixtures only. The explicit
    # witness type remains non-authoritative and the governed identity audit rejects
    # it for production attachment.
    return "CAST(p.fpl_api_id AS TEXT)", "missing_name_witness"


def _validated_rows(rows: list[tuple]) -> list[tuple[int, object, object, object]]:
    """Validate exact official IDs before serialization can erase corruption."""
    validated: list[tuple[int, object, object, object]] = []
    for row_number, (player_id, source_player_name, gameweek, xp) in enumerate(rows, start=1):
        try:
            exact_id = parse_exact_player_id(
                player_id, label=f"AIrsenal fpl_api_id row {row_number}"
            )
        except IdentityIntegrityError as exc:
            raise SystemExit(
                f"Invalid official FPL player ID in AIrsenal export: {exc}"
            ) from exc
        validated.append((exact_id, source_player_name, gameweek, xp))
    return validated


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: python scripts/export_airsenal.py AIRSENAL.sqlite TAG output.csv"
        )

    db_path, requested_tag, output = sys.argv[1:4]
    db = sqlite3.connect(db_path)
    try:
        tag = _latest_tag(db) if requested_tag.upper() == "LATEST" else requested_tag
        name_expr, witness_type = _player_name_expression(db)
        rows = db.execute(
            f"""
            SELECT p.fpl_api_id, {name_expr}, f.gameweek, SUM(pp.predicted_points)
            FROM player_prediction AS pp
            JOIN player AS p ON p.player_id = pp.player_id
            JOIN fixture AS f ON f.fixture_id = pp.fixture_id
            WHERE pp.tag = ?
              AND f.gameweek IS NOT NULL
              AND p.fpl_api_id IS NOT NULL
            GROUP BY p.fpl_api_id, {name_expr}, f.gameweek
            ORDER BY p.fpl_api_id, f.gameweek
            """,
            (tag,),
        ).fetchall()
    finally:
        db.close()

    if not rows:
        raise SystemExit(f"No official-ID AIrsenal predictions found for tag {tag!r}")

    rows = _validated_rows(rows)
    generated_at = datetime.now(timezone.utc).isoformat()
    source_version = os.getenv("AIRSENAL_SOURCE_VERSION", "")
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "player_id",
                "source_player_name",
                "identity_witness_type",
                "gw",
                "xp",
                "generated_at",
                "source_version",
                "prediction_tag",
            ]
        )
        writer.writerows(
            (
                player_id,
                str(source_player_name),
                witness_type,
                int(gameweek),
                float(xp),
                generated_at,
                source_version,
                tag,
            )
            for player_id, source_player_name, gameweek, xp in rows
        )

    unique_players = len({row[0] for row in rows})
    gameweeks = sorted({int(row[2]) for row in rows})
    print(
        f"Exported {len(rows)} player-gameweek rows for {unique_players} official FPL "
        f"players, GW={gameweeks}, tag={tag!r}, identity_witness={witness_type}, to {path}"
    )


if __name__ == "__main__":
    main()
