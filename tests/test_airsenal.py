from __future__ import annotations

from datetime import datetime, timedelta, timezone
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
