from __future__ import annotations

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pandas as pd
import pytest

from apex_fpl.data.airsenal import AIrsenalProjectionAdapter, validate_airsenal_forecast


PIN = "8c7e18eba1488dd5a7d4bdb00d4da0a75e895717"


def _forecast(now: datetime | None = None) -> pd.DataFrame:
    now = now or datetime.now(timezone.utc)
    rows = []
    for gw in (1, 2):
        for player_id in range(1, 7):
            rows.append(
                {
                    "player_id": player_id,
                    "gw": gw,
                    "xp": 3.0 + player_id / 10,
                    "generated_at": now.isoformat(),
                    "source_version": PIN,
                    "prediction_tag": "tag-1",
                }
            )
    return pd.DataFrame(rows)


def test_adapter_and_validator_accept_current_official_id_contract(tmp_path: Path):
    path = tmp_path / "airsenal.csv"
    _forecast().to_csv(path, index=False)
    out = AIrsenalProjectionAdapter(str(path)).load(valid_ids=set(range(1, 7)))
    ok, detail = validate_airsenal_forecast(
        out,
        set(range(1, 7)),
        [1, 2],
        expected_source_version=PIN,
        min_player_coverage=0.8,
    )
    assert ok, detail
    assert out["airsenal_xp"].notna().all()


def test_adapter_rejects_unknown_official_ids(tmp_path: Path):
    path = tmp_path / "airsenal.csv"
    df = _forecast()
    df.loc[0, "player_id"] = 999
    df.to_csv(path, index=False)
    with pytest.raises(ValueError, match="unknown official FPL IDs"):
        AIrsenalProjectionAdapter(str(path)).load(valid_ids=set(range(1, 7)))


def test_validator_rejects_stale_or_wrong_version(tmp_path: Path):
    path = tmp_path / "airsenal.csv"
    _forecast(datetime.now(timezone.utc) - timedelta(hours=50)).to_csv(path, index=False)
    out = AIrsenalProjectionAdapter(str(path)).load(valid_ids=set(range(1, 7)))
    ok, detail = validate_airsenal_forecast(
        out,
        set(range(1, 7)),
        [1, 2],
        expected_source_version=PIN,
        max_age_hours=36,
        min_player_coverage=0.8,
    )
    assert not ok
    assert "stale" in detail

    fresh = _forecast()
    fresh["source_version"] = "wrong"
    fresh.to_csv(path, index=False)
    out = AIrsenalProjectionAdapter(str(path)).load(valid_ids=set(range(1, 7)))
    ok, detail = validate_airsenal_forecast(
        out,
        set(range(1, 7)),
        [1, 2],
        expected_source_version=PIN,
        min_player_coverage=0.8,
    )
    assert not ok
    assert "version mismatch" in detail


def test_validator_rejects_mixed_generation_rows(tmp_path: Path):
    path = tmp_path / "airsenal.csv"
    frame = _forecast()
    frame.loc[frame["gw"] == 2, "generated_at"] = (
        datetime.now(timezone.utc) - timedelta(hours=1)
    ).isoformat()
    frame.to_csv(path, index=False)
    out = AIrsenalProjectionAdapter(str(path)).load(valid_ids=set(range(1, 7)))
    ok, detail = validate_airsenal_forecast(
        out,
        set(range(1, 7)),
        [1, 2],
        expected_source_version=PIN,
        min_player_coverage=0.8,
    )
    assert not ok
    assert "mixes multiple AIrsenal generations" in detail


def test_validator_rejects_non_finite_or_implausible_expected_points(tmp_path: Path):
    path = tmp_path / "airsenal.csv"
    bad = _forecast()
    bad.loc[0, "xp"] = 99.0
    bad.to_csv(path, index=False)
    out = AIrsenalProjectionAdapter(str(path)).load(valid_ids=set(range(1, 7)))
    ok, detail = validate_airsenal_forecast(
        out,
        set(range(1, 7)),
        [1, 2],
        expected_source_version=PIN,
        min_player_coverage=0.8,
    )
    assert not ok
    assert "outside [0, 40]" in detail


def test_exporter_maps_airsenal_internal_id_to_official_fpl_id(tmp_path: Path):
    db_path = tmp_path / "airsenal.db"
    db = sqlite3.connect(db_path)
    db.executescript(
        """
        CREATE TABLE player (player_id INTEGER PRIMARY KEY, fpl_api_id INTEGER);
        CREATE TABLE fixture (fixture_id INTEGER PRIMARY KEY, gameweek INTEGER);
        CREATE TABLE player_prediction (
            id INTEGER PRIMARY KEY,
            fixture_id INTEGER,
            predicted_points REAL,
            tag TEXT,
            player_id INTEGER
        );
        INSERT INTO player VALUES (7, 999);
        INSERT INTO fixture VALUES (11, 1);
        INSERT INTO player_prediction VALUES (1, 11, 6.5, 'real-tag', 7);
        """
    )
    db.commit()
    db.close()

    output = tmp_path / "out.csv"
    script = Path(__file__).parents[1] / "scripts" / "export_airsenal.py"
    env = {**__import__("os").environ, "AIRSENAL_SOURCE_VERSION": PIN}
    subprocess.run(
        [sys.executable, str(script), str(db_path), "LATEST", str(output)],
        check=True,
        env=env,
    )
    out = pd.read_csv(output)
    assert out.iloc[0]["player_id"] == 999
    assert out.iloc[0]["gw"] == 1
    assert out.iloc[0]["xp"] == pytest.approx(6.5)
    assert out.iloc[0]["source_version"] == PIN
    assert out.iloc[0]["prediction_tag"] == "real-tag"


def _worker_module():
    path = Path(__file__).parents[1] / "scripts" / "run_airsenal_worker.py"
    spec = importlib.util.spec_from_file_location("run_airsenal_worker", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_worker_resolves_live_unfinished_horizon(monkeypatch):
    worker = _worker_module()
    payload = {
        "events": [
            {"id": 4, "finished": True},
            {"id": 5, "finished": False},
            {"id": 6, "finished": False},
        ],
        "elements": [{"id": 101}, {"id": 202}],
    }

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return json.dumps(payload).encode()

    monkeypatch.setattr(worker.urllib.request, "urlopen", lambda request, timeout: Response())
    assert worker._official_horizon(8) == ([5, 6], {101, 202})


def test_worker_uses_open_deadlines_and_stops_at_season_boundary():
    worker = _worker_module()
    now = datetime(2027, 5, 20, tzinfo=timezone.utc)
    events = [
        {"id": 36, "finished": False, "deadline_time": "2027-05-18T10:00:00Z"},
        {"id": 37, "finished": False, "deadline_time": "2027-05-21T10:00:00Z"},
        {"id": 38, "finished": False, "deadline_time": "2027-05-25T10:00:00Z"},
    ]
    assert worker._actionable_gameweeks(events, 8, now=now) == [37, 38]


def test_worker_rejects_non_official_export_ids(tmp_path: Path):
    worker = _worker_module()
    output = tmp_path / "airsenal.csv"
    pd.DataFrame([{"player_id": 7, "gw": 1, "xp": 3.0}]).to_csv(output, index=False)
    with pytest.raises(SystemExit, match="unknown official FPL IDs"):
        worker._assert_export_contract(output, {1, 2, 3}, [1])


def test_worker_rejects_export_with_truncated_horizon(tmp_path: Path):
    worker = _worker_module()
    output = tmp_path / "airsenal.csv"
    pd.DataFrame([{"player_id": 1, "gw": 1, "xp": 3.0}]).to_csv(output, index=False)
    with pytest.raises(SystemExit, match=r"missing requested Gameweeks: \[2\]"):
        worker._assert_export_contract(output, {1}, [1, 2])


def test_worker_reads_the_pinned_airsenal_revision():
    assert _worker_module()._airsenal_pin() == PIN


def test_worker_runs_prediction_then_official_id_export(tmp_path: Path, monkeypatch):
    worker = _worker_module()
    db_path = tmp_path / "airsenal.db"
    db_path.write_bytes(b"database")
    output = tmp_path / "airsenal.csv"
    calls = []

    monkeypatch.setattr(worker, "_official_horizon", lambda horizon: (list(range(3, 11)), {999}))

    def fake_run(command, *, check, env):
        calls.append((command, check, env))
        if command[0] == sys.executable:
            pd.DataFrame(
                [{"player_id": 999, "gw": gw, "xp": 6.5} for gw in range(3, 11)]
            ).to_csv(
                output, index=False
            )

    monkeypatch.setattr(worker.subprocess, "run", fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_airsenal_worker.py",
            "--db",
            str(db_path),
            "--horizon",
            "8",
            "--output",
            str(output),
        ],
    )
    worker.main()

    assert calls[0][0] == [
        "airsenal_run_prediction",
        "--gameweek_start",
        "3",
        "--gameweek_end",
        "11",
    ]
    assert calls[1][0][1].endswith("scripts/export_airsenal.py")
    assert calls[1][0][2:] == [str(db_path), "LATEST", str(output)]
    assert calls[0][1] is True and calls[1][1] is True
    assert calls[0][2]["AIRSENAL_DB_FILE"] == str(db_path.resolve())
    assert calls[0][2]["AIRSENAL_SOURCE_VERSION"] == PIN
