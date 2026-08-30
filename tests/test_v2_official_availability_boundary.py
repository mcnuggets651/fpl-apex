from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apex.domain.models import EvidenceEffect, OfficialPlayer, OfficialSnapshot, Position
from apex.sources.evidence import _official_fpl_records


@pytest.mark.parametrize(
    ("status", "chance", "expected_effect"),
    [
        ("i", 75, EvidenceEffect.AUDIT_ONLY),
        ("i", 50, EvidenceEffect.AUDIT_ONLY),
        ("d", 25, EvidenceEffect.AUDIT_ONLY),
        ("n", None, EvidenceEffect.AUDIT_ONLY),
        ("i", 0, EvidenceEffect.HARD_EXCLUDE),
        ("d", 0, EvidenceEffect.HARD_EXCLUDE),
        ("s", None, EvidenceEffect.HARD_EXCLUDE),
        ("u", None, EvidenceEffect.HARD_EXCLUDE),
    ],
)
def test_official_availability_hard_exclusion_requires_definitive_state(
    status,
    chance,
    expected_effect,
):
    player = OfficialPlayer(1, "Player One", 1, Position.MID, 50, status, True, 1001)
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-29T08:00:00+00:00",
        "a" * 64,
        (player,),
        (),
        {3: "2026-09-12T10:00:00+00:00"},
    )
    raw = {
        "elements": [
            {
                "id": 1,
                "status": status,
                "chance_of_playing_this_round": chance,
                "news": "Availability update",
                "news_added": "2026-08-29T07:30:00Z",
            }
        ]
    }
    records = _official_fpl_records(
        raw,
        official=official,
        target_gameweek=3,
        deadline=datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
    )
    assert len(records) == 1
    assert records[0].effect == expected_effect
