from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys


def _make_db(path: Path, *, resolvable_current: bool = True) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """
        CREATE TABLE player (
            player_id INTEGER PRIMARY KEY,
            name TEXT,
            opta_code TEXT,
            fpl_api_id INTEGER
        );
        CREATE TABLE player_attributes (
            id INTEGER PRIMARY KEY,
            player_id INTEGER,
            season TEXT,
            position TEXT
        );
        """
    )
    current_name = "David Raya Martín" if resolvable_current else "Unmapped Current Player"
    current_opta = "p154561" if resolvable_current else "p999999"
    db.executemany(
        "INSERT INTO player(player_id, name, opta_code, fpl_api_id) VALUES (?, ?, ?, ?)",
        [
            (7, current_name, current_opta, 101),
            (8, "Retired Unknown", "p888888", None),
        ],
    )
    db.executemany(
        "INSERT INTO player_attributes(id, player_id, season, position) VALUES (?, ?, ?, ?)",
        [
            (1, 7, "2526", ""),
            (2, 8, "2526", ""),
        ],
    )
    db.commit()
    db.close()


def _make_checkout(root: Path) -> None:
    data = root / "airsenal" / "data"
    data.mkdir(parents=True)
    (data / "player_summary_2526.json").write_text(
        json.dumps(
            [
                {
                    "name": "David Raya Martín",
                    "position": "GKP",
                    "opta_code": "p154561",
                }
            ]
        ),
        encoding="utf-8",
    )


def _script() -> Path:
    return Path(__file__).parents[1] / "scripts" / "patch_airsenal_positions.py"


def test_patch_maps_gkp_to_gk_and_ignores_unresolved_retired_player(tmp_path: Path):
    db_path = tmp_path / "airsenal.db"
    checkout = tmp_path / "worker"
    _make_db(db_path, resolvable_current=True)
    _make_checkout(checkout)

    result = subprocess.run(
        [sys.executable, str(_script()), str(db_path), str(checkout)],
        check=True,
        text=True,
        capture_output=True,
    )
    assert "patched=1" in result.stdout
    assert "unresolved_current=0" in result.stdout

    db = sqlite3.connect(db_path)
    try:
        current_position = db.execute(
            "SELECT position FROM player_attributes WHERE player_id = 7"
        ).fetchone()[0]
        retired_position = db.execute(
            "SELECT position FROM player_attributes WHERE player_id = 8"
        ).fetchone()[0]
    finally:
        db.close()
    assert current_position == "GK"
    assert retired_position == ""


def test_patch_refuses_unresolved_current_fpl_player(tmp_path: Path):
    db_path = tmp_path / "airsenal.db"
    checkout = tmp_path / "worker"
    _make_db(db_path, resolvable_current=False)
    _make_checkout(checkout)

    result = subprocess.run(
        [sys.executable, str(_script()), str(db_path), str(checkout)],
        check=False,
        text=True,
        capture_output=True,
    )
    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "unresolved_current=1" in combined
    assert "refusing to generate a production forecast" in combined
