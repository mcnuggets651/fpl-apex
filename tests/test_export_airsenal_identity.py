from __future__ import annotations

import csv
import importlib.util
from pathlib import Path
import sqlite3
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts" / "export_airsenal.py"
    spec = importlib.util.spec_from_file_location("export_airsenal_identity_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _db(path: Path, fpl_api_id: object) -> None:
    db = sqlite3.connect(path)
    try:
        db.executescript(
            """
            CREATE TABLE player (
                player_id INTEGER PRIMARY KEY,
                fpl_api_id,
                name TEXT
            );
            CREATE TABLE fixture (
                fixture_id INTEGER PRIMARY KEY,
                gameweek INTEGER
            );
            CREATE TABLE player_prediction (
                id INTEGER PRIMARY KEY,
                player_id INTEGER,
                fixture_id INTEGER,
                tag TEXT,
                predicted_points REAL
            );
            """
        )
        db.execute(
            "INSERT INTO player(player_id, fpl_api_id, name) VALUES (?, ?, ?)",
            (1, fpl_api_id, "Alpha"),
        )
        db.execute("INSERT INTO fixture(fixture_id, gameweek) VALUES (?, ?)", (1, 1))
        db.execute(
            """
            INSERT INTO player_prediction(
                id, player_id, fixture_id, tag, predicted_points
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (1, 1, 1, "tag-test", 4.25),
        )
        db.commit()
    finally:
        db.close()


def test_exporter_preserves_exact_integral_official_fpl_id(tmp_path, monkeypatch) -> None:
    module = _module()
    db_path = tmp_path / "airsenal.sqlite"
    output = tmp_path / "airsenal.csv"
    _db(db_path, 10.0)
    monkeypatch.setattr(
        sys,
        "argv",
        ["export_airsenal.py", str(db_path), "tag-test", str(output)],
    )

    module.main()

    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 1
    assert rows[0]["player_id"] == "10"
    assert rows[0]["source_player_name"] == "Alpha"
    assert rows[0]["identity_witness_type"] == "airsenal_name"


def test_exporter_rejects_fractional_fpl_id_before_creating_output(
    tmp_path, monkeypatch
) -> None:
    module = _module()
    db_path = tmp_path / "airsenal.sqlite"
    output = tmp_path / "airsenal.csv"
    _db(db_path, 10.5)
    monkeypatch.setattr(
        sys,
        "argv",
        ["export_airsenal.py", str(db_path), "tag-test", str(output)],
    )

    with pytest.raises(SystemExit, match="non-integral"):
        module.main()

    assert not output.exists()


def test_exporter_rejects_non_numeric_fpl_id_before_creating_output(
    tmp_path, monkeypatch
) -> None:
    module = _module()
    db_path = tmp_path / "airsenal.sqlite"
    output = tmp_path / "airsenal.csv"
    _db(db_path, "not-an-id")
    monkeypatch.setattr(
        sys,
        "argv",
        ["export_airsenal.py", str(db_path), "tag-test", str(output)],
    )

    with pytest.raises(SystemExit, match="non-numeric"):
        module.main()

    assert not output.exists()
