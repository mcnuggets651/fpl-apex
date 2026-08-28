from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apex_airsenal_attribute_refresh",
    ROOT / "scripts/airsenal_attribute_refresh.py",
)
assert SPEC is not None and SPEC.loader is not None
REFRESH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REFRESH)


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "data.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE player_attributes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                season TEXT NOT NULL,
                gameweek INTEGER NOT NULL,
                price INTEGER,
                UNIQUE(player_id, season, gameweek)
            )
            """
        )
        connection.executemany(
            "INSERT INTO player_attributes(player_id, season, gameweek, price) "
            "VALUES (?, ?, ?, ?)",
            [
                (1, "2627", 1, 50),
                (1, "2627", 2, 51),
                (1, "2627", 3, 52),
                (2, "2627", 1, 45),
                (2, "2627", 2, 46),
                (1, "2526", 38, 49),
            ],
        )
        connection.commit()
    return path


def _rows(path: Path) -> list[tuple[int, str, int, int]]:
    with sqlite3.connect(path) as connection:
        return connection.execute(
            "SELECT player_id, season, gameweek, price "
            "FROM player_attributes ORDER BY season, player_id, gameweek"
        ).fetchall()


def test_rewind_removes_only_current_season_mutable_window(tmp_path: Path) -> None:
    path = _db(tmp_path)

    removed = REFRESH.rewind_player_attributes(
        path,
        season="2627",
        from_gameweek=2,
    )

    assert removed == 3
    assert _rows(path) == [
        (1, "2526", 38, 49),
        (1, "2627", 1, 50),
        (2, "2627", 1, 45),
    ]


def test_rewind_is_idempotent(tmp_path: Path) -> None:
    path = _db(tmp_path)
    first = REFRESH.rewind_player_attributes(
        path,
        season="2627",
        from_gameweek=2,
    )
    second = REFRESH.rewind_player_attributes(
        path,
        season="2627",
        from_gameweek=2,
    )
    assert first == 3
    assert second == 0


def test_rewind_from_gw1_rebuilds_only_requested_season(tmp_path: Path) -> None:
    path = _db(tmp_path)
    removed = REFRESH.rewind_player_attributes(
        path,
        season="2627",
        from_gameweek=1,
    )
    assert removed == 5
    assert _rows(path) == [(1, "2526", 38, 49)]


def test_rewind_requires_existing_database(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        REFRESH.rewind_player_attributes(
            tmp_path / "missing.db",
            season="2627",
            from_gameweek=1,
        )


def test_rewind_requires_player_attributes_table(tmp_path: Path) -> None:
    path = tmp_path / "empty.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE other_table(id INTEGER PRIMARY KEY)")
        connection.commit()
    with pytest.raises(RuntimeError, match="player_attributes"):
        REFRESH.rewind_player_attributes(
            path,
            season="2627",
            from_gameweek=1,
        )


def test_rewind_rejects_invalid_scope(tmp_path: Path) -> None:
    path = _db(tmp_path)
    with pytest.raises(ValueError, match="season"):
        REFRESH.rewind_player_attributes(path, season="", from_gameweek=1)
    with pytest.raises(ValueError, match="from_gameweek"):
        REFRESH.rewind_player_attributes(path, season="2627", from_gameweek=0)
