from __future__ import annotations

import pytest

from apex_fpl.core.evidence import EvidenceClaim, EvidenceClaimType, EvidencePolarity
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.reliability import ReliabilityContext, ReliabilityQualification


def _context() -> ReliabilityContext:
    return ReliabilityContext(
        source_id="example_source",
        claim_type=EvidenceClaimType.INJURY.value,
        horizon_gameweeks=1,
        recency_bucket="deadline_day",
        qualification=ReliabilityQualification.UNKNOWN,
    )


def _claim(**overrides) -> EvidenceClaim:
    values = {
        "player_id": OfficialPlayerId(1),
        "claim_type": EvidenceClaimType.INJURY,
        "source_id": "example_source",
        "source_capability": "football_news",
        "statement": "Player reported with an injury.",
        "polarity": EvidencePolarity.NEGATIVE,
        "confidence_bps": 7000,
        "reliability": _context(),
        "raw_artifact_id": "sha256:" + "a" * 64,
        "source_url": "https://example.com/injury",
        "source_event_at": "2026-08-24T04:50:00Z",
        "observed_at": "2026-08-24T05:00:00Z",
        "first_known_at": "2026-08-24T05:01:00Z",
        "ingested_at": "2026-08-24T05:02:00Z",
    }
    values.update(overrides)
    return EvidenceClaim(**values)


def test_evidence_chronology_requires_event_observed_known_ingested_order():
    claim = _claim()
    assert claim.known_by("2026-08-24T05:00:59Z") is False
    assert claim.known_by("2026-08-24T05:01:00Z") is True

    with pytest.raises(ValueError, match="source_event_at cannot be after observed_at"):
        _claim(source_event_at="2026-08-24T05:00:01Z")
    with pytest.raises(ValueError, match="observed_at cannot be after first_known_at"):
        _claim(first_known_at="2026-08-24T04:59:59Z")
    with pytest.raises(ValueError, match="first_known_at cannot be after ingested_at"):
        _claim(first_known_at="2026-08-24T05:03:00Z")
