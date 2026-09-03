from __future__ import annotations

from datetime import datetime, timezone

from apex.domain.models import (
    EvidenceEffect,
    EvidenceRecord,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
)
from apex.governance.evidence import validate_evidence

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc)


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T11:00:00Z",
        "a" * 64,
        (OfficialPlayer(1, "One", 1, Position.MID, 50, "a", True, 123),),
        (),
        {3: "2026-09-12T10:00:00Z"},
    )


def _record(**changes) -> EvidenceRecord:
    values = {
        "evidence_id": "e1",
        "element_id": 1,
        "source_name": "Club",
        "source_url": "https://club.example/news",
        "source_tier": "official_club",
        "published_at": "2026-09-02T10:00:00Z",
        "retrieved_at": "2026-09-02T10:05:00Z",
        "expires_at": "2026-09-03T10:00:00Z",
        "evidence_type": "availability",
        "gameweek": 3,
        "effect": EvidenceEffect.HARD_EXCLUDE,
        "content_hash": "a" * 64,
        "excerpt": "unavailable",
    }
    values.update(changes)
    return EvidenceRecord(**values)


def test_evidence_rejects_future_publication_time():
    errors = validate_evidence(
        (_record(published_at="2026-09-02T13:00:00Z", retrieved_at="2026-09-02T13:05:00Z"),),
        _official(),
        now=NOW,
    )
    assert any("future" in error.lower() or "published" in error.lower() for error in errors)


def test_evidence_rejects_future_retrieval_time():
    errors = validate_evidence(
        (_record(retrieved_at="2026-09-02T13:00:00Z"),),
        _official(),
        now=NOW,
    )
    assert any("future" in error.lower() or "retrieved" in error.lower() for error in errors)


def test_evidence_rejects_retrieval_before_publication():
    errors = validate_evidence(
        (_record(retrieved_at="2026-09-02T09:59:00Z"),),
        _official(),
        now=NOW,
    )
    assert any("retriev" in error.lower() for error in errors)


def test_evidence_rejects_non_hex_content_hash():
    errors = validate_evidence(
        (_record(content_hash="z" * 64),),
        _official(),
        now=NOW,
    )
    assert any("content hash" in error.lower() for error in errors)
