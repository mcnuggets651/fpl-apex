from datetime import datetime, timezone

import pandas as pd
import pytest

from apex_fpl.data.news import load_manual_signals


def _row() -> dict:
    return {
        "player_id": 1,
        "availability_multiplier": 0.2,
        "confidence": 0.95,
        "reason": "ruled out",
        "source_name": "Example FC",
        "source_tier": "official_club",
        "source_url": "https://example.test/team-news",
        "evidence_type": "official_availability",
        "published_at": "2026-08-07T07:00:00Z",
        "expires_at": "2026-08-10T07:00:00Z",
        "relevant_excerpt": "Example is ruled out.",
        "content_hash": "a" * 64,
        "transcriber": "codex:test",
    }


def test_manual_availability_preserves_provenance(tmp_path):
    path = tmp_path / "availability.csv"
    pd.DataFrame([_row()]).to_csv(path, index=False)
    loaded = load_manual_signals(
        path, now=datetime(2026, 8, 8, tzinfo=timezone.utc)
    ).iloc[0]
    assert loaded["availability_source_name"] == "Example FC"
    assert loaded["availability_source_tier"] == "official_club"
    assert loaded["availability_published_at"] == "2026-08-07T07:00:00Z"
    assert loaded["availability_retrieved_at"]


def test_expired_manual_availability_is_rejected(tmp_path):
    path = tmp_path / "availability.csv"
    pd.DataFrame([_row()]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="expired"):
        load_manual_signals(
            path, now=datetime(2026, 8, 11, tzinfo=timezone.utc)
        )


def test_unverifiable_manual_availability_is_rejected(tmp_path):
    path = tmp_path / "availability.csv"
    row = _row()
    row["source_url"] = ""
    pd.DataFrame([row]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="provenance"):
        load_manual_signals(
            path, now=datetime(2026, 8, 8, tzinfo=timezone.utc)
        )


def test_manual_transcription_cannot_promote_trusted_media_to_official(tmp_path):
    path = tmp_path / "availability.csv"
    row = _row()
    row["source_tier"] = "trusted_media"
    pd.DataFrame([row]).to_csv(path, index=False)
    with pytest.raises(ValueError, match="official source"):
        load_manual_signals(path, now=datetime(2026, 8, 8, tzinfo=timezone.utc))
