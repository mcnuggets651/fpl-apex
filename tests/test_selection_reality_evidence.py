from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from apex_fpl.services.selection_reality_evidence import materialize_selection_reality_evidence


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "Alpha",
                "team": 1,
                "team_name": "Arsenal",
                "position": "DEF",
                "price": 4.5,
                "status": "a",
                "expected_minutes": 80.0,
                "start_probability": 0.9,
            }
        ]
    )


def _write(path: Path, rows: list[dict], columns: list[str]) -> None:
    pd.DataFrame(rows, columns=columns).to_csv(path, index=False)


def test_materializer_identity_checks_and_writes_reports(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    specialist = tmp_path / "specialist.csv"
    transfer = tmp_path / "transfer.csv"
    common = {
        "player_id": 1,
        "source_player_name": "Alpha",
        "source_url": "https://example.com/evidence",
        "published_at": now.isoformat(),
        "retrieved_at": now.isoformat(),
        "expires_at": (now + timedelta(hours=4)).isoformat(),
    }
    _write(
        specialist,
        [{**common, "source": "fantasy_football_scout", "predicted_start": True}],
        ["player_id", "source_player_name", "source", "predicted_start", "source_url", "published_at", "retrieved_at", "expires_at"],
    )
    _write(
        transfer,
        [{**common, "source": "fabrizio_romano", "signal": "interest"}],
        ["player_id", "source_player_name", "source", "signal", "source_url", "published_at", "retrieved_at", "expires_at"],
    )

    specialist_report, transfer_report = materialize_selection_reality_evidence(
        _players(),
        specialist_path=specialist,
        transfer_path=transfer,
        output_dir=tmp_path / "out",
        selected_ids={1},
        now=now,
    )
    assert len(specialist_report) == 1
    assert len(transfer_report) == 1
    assert (tmp_path / "out" / "specialist_disagreement.csv").exists()
    assert (tmp_path / "out" / "transfer_intelligence.csv").exists()


def test_materializer_rejects_wrong_identity(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    specialist = tmp_path / "specialist.csv"
    transfer = tmp_path / "transfer.csv"
    _write(
        specialist,
        [
            {
                "player_id": 1,
                "source_player_name": "Wrong",
                "source": "fantasy_football_scout",
                "predicted_start": True,
                "source_url": "https://example.com/evidence",
                "published_at": now.isoformat(),
                "retrieved_at": now.isoformat(),
                "expires_at": (now + timedelta(hours=4)).isoformat(),
            }
        ],
        ["player_id", "source_player_name", "source", "predicted_start", "source_url", "published_at", "retrieved_at", "expires_at"],
    )
    _write(
        transfer,
        [],
        ["player_id", "source_player_name", "source", "signal", "source_url", "published_at", "retrieved_at", "expires_at"],
    )
    with pytest.raises(ValueError, match="identity failed"):
        materialize_selection_reality_evidence(
            _players(),
            specialist_path=specialist,
            transfer_path=transfer,
            output_dir=tmp_path / "out",
            now=now,
        )


def test_expired_evidence_is_excluded_not_reused(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    specialist = tmp_path / "specialist.csv"
    transfer = tmp_path / "transfer.csv"
    _write(
        specialist,
        [
            {
                "player_id": 1,
                "source_player_name": "Alpha",
                "source": "fantasy_football_scout",
                "predicted_start": True,
                "source_url": "https://example.com/evidence",
                "published_at": (now - timedelta(hours=6)).isoformat(),
                "retrieved_at": (now - timedelta(hours=5)).isoformat(),
                "expires_at": (now - timedelta(hours=1)).isoformat(),
            }
        ],
        ["player_id", "source_player_name", "source", "predicted_start", "source_url", "published_at", "retrieved_at", "expires_at"],
    )
    _write(
        transfer,
        [],
        ["player_id", "source_player_name", "source", "signal", "source_url", "published_at", "retrieved_at", "expires_at"],
    )
    specialist_report, _ = materialize_selection_reality_evidence(
        _players(),
        specialist_path=specialist,
        transfer_path=transfer,
        output_dir=tmp_path / "out",
        selected_ids={1},
        now=now,
    )
    assert specialist_report.iloc[0]["specialist_source_count"] == 0
