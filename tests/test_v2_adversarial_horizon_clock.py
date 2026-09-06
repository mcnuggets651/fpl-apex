from __future__ import annotations

from datetime import datetime, timezone

from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    Qualification,
)
from apex.forecast.qualification import qualify_surface


def test_valid_but_shifted_gameweek_cannot_qualify_as_h1():
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T10:00:00Z",
        "official-hash",
        (OfficialPlayer(1, "One", 1, Position.MID, 50, "a", True),),
        (),
        {
            3: "2026-09-05T10:00:00Z",
            4: "2026-09-12T10:00:00Z",
            5: "2026-09-19T10:00:00Z",
        },
    )
    # H1 is complete and points at a real Official gameweek, but it is shifted
    # one week ahead of the actual next deadline (GW3).
    surface = ProjectionSurface(
        1,
        "airsenal",
        "v1",
        "2026-09-02T10:05:00Z",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        (1,),
        (),
        (
            ProjectionRow(
                1,
                4,
                1,
                5.0,
                p_appearance=1.0,
                coverage_status=CoverageStatus.FORECAST,
            ),
        ),
    )

    result = qualify_surface(
        surface,
        official,
        decision_universe=frozenset({1}),
        requested_horizons=(1,),
        max_age_hours=18,
        required_scoring_rules_version="fpl-2026-27-v1",
        now=datetime(2026, 9, 2, 12, 0, tzinfo=timezone.utc),
    )

    assert result.operational == Qualification.UNQUALIFIED
    assert any(
        "gameweek" in reason.lower() and "horizon" in reason.lower()
        for reason in result.reasons
    )
