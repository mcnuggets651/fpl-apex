#!/usr/bin/env python3
"""Work around AIrsenal issue #827 without weakening Apex identity controls.

Pinned AIrsenal commit 8c7e18e can load historical ``player_details`` rows with
an empty ``PlayerAttributes.position`` because that JSON no longer carries the
position field. The matching ``player_summary_<season>.json`` files *do* carry
it. This worker-only patch backfills blank historical positions by Opta code
(first choice) or normalized name, mapping ``GKP`` to AIrsenal's ``GK`` label.

Only rows for players that AIrsenal itself already created are changed. Current
FPL identity is still validated later through official ``fpl_api_id`` in Apex.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import sqlite3
import sys
import unicodedata

VALID_POSITIONS = {"GK", "DEF", "MID", "FWD"}


def _norm(value: str | None) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def _summaries(airsenal_root: Path) -> dict[str, tuple[dict[str, str], dict[str, str]]]:
    result: dict[str, tuple[dict[str, str], dict[str, str]]] = {}
    for path in sorted((airsenal_root / "airsenal" / "data").glob("player_summary_*.json")):
        season = path.stem.rsplit("_", 1)[-1]
        by_opta: dict[str, str] = {}
        by_name: dict[str, str] = {}
        for row in json.loads(path.read_text(encoding="utf-8")):
            position = str(row.get("position") or "").upper()
            if position == "GKP":
                position = "GK"
            if position not in VALID_POSITIONS:
                continue
            opta = str(row.get("opta_code") or "").strip()
            if opta:
                by_opta[opta] = position
            name = _norm(str(row.get("name") or ""))
            if name:
                by_name[name] = position
        result[season] = (by_opta, by_name)
    return result


def patch(db_path: Path, airsenal_root: Path) -> tuple[int, int]:
    summary = _summaries(airsenal_root)
    if not summary:
        raise RuntimeError(f"No AIrsenal player_summary_*.json files found under {airsenal_root}")

    db = sqlite3.connect(db_path)
    try:
        players = {
            int(player_id): (name, opta_code, fpl_api_id)
            for player_id, name, opta_code, fpl_api_id in db.execute(
                "SELECT player_id, name, opta_code, fpl_api_id FROM player"
            )
        }
        blanks = db.execute(
            """
            SELECT id, player_id, season
            FROM player_attributes
            WHERE position IS NULL OR TRIM(position) = ''
            """
        ).fetchall()
        patched = 0
        for attr_id, player_id, season in blanks:
            maps = summary.get(str(season))
            player = players.get(int(player_id))
            if not maps or not player:
                continue
            name, opta_code, _ = player
            by_opta, by_name = maps
            position = None
            if opta_code:
                position = by_opta.get(str(opta_code))
            if position is None:
                position = by_name.get(_norm(str(name)))
            if position in VALID_POSITIONS:
                db.execute(
                    "UPDATE player_attributes SET position = ? WHERE id = ?",
                    (position, int(attr_id)),
                )
                patched += 1
        db.commit()

        # A blank historical position for a player that is in the current FPL
        # pool can directly distort the AIrsenal player model. Retired historical
        # players are not a blocker for a current-season forecast.
        unresolved_current = int(
            db.execute(
                """
                SELECT COUNT(*)
                FROM player_attributes AS pa
                JOIN player AS p ON p.player_id = pa.player_id
                WHERE p.fpl_api_id IS NOT NULL
                  AND (pa.position IS NULL OR TRIM(pa.position) = '')
                """
            ).fetchone()[0]
        )
        return patched, unresolved_current
    finally:
        db.close()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "Usage: python scripts/patch_airsenal_positions.py AIRSENAL.sqlite AIRSENAL_CHECKOUT"
        )
    patched, unresolved = patch(Path(sys.argv[1]), Path(sys.argv[2]))
    print(f"AIrsenal historical-position patch: patched={patched}, unresolved_current={unresolved}")
    if unresolved:
        raise SystemExit(
            "Current-season AIrsenal players still have blank historical positions; "
            "refusing to generate a production forecast"
        )


if __name__ == "__main__":
    main()
