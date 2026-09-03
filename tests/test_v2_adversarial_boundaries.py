from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from apex.domain.models import (
    CoverageStatus,
    OfficialFixture,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    Qualification,
)
from apex.forecast.contract import validate_projection_surface
from apex.forecast.qualification import qualify_surface


def _official() -> OfficialSnapshot:
    players = tuple(
        OfficialPlayer(
            element_id=player_id,
            web_name=f"P{player_id}",
            team_id=((player_id - 1) % 4) + 1,
            position=Position.MID,
            price_tenths=50,
            status="a",
            can_transact=True,
        )
        for player_id in range(1, 5)
    )
    fixtures = (
        OfficialFixture(101, 2, 1, 2, "2026-09-12T14:00:00Z"),
        OfficialFixture(102, 2, 3, 4, "2026-09-12T14:00:00Z"),
    )
    return OfficialSnapshot(
        schema_version=1,
        season="2026-2027",
        acquired_at="2026-09-02T12:00:00+00:00",
        source_hash="official-snapshot-A",
        players=players,
        fixtures=fixtures,
        deadlines={2: "2026-09-12T10:00:00Z"},
    )


def _surface(official: OfficialSnapshot) -> ProjectionSurface:
    fixture_by_player = {1: 101, 2: 101, 3: 102, 4: 102}
    rows = tuple(
        ProjectionRow(
            element_id=player.element_id,
            gameweek=2,
            horizon=1,
            expected_points=3.0,
            fixture_ids=(fixture_by_player[player.element_id],),
            n_fixtures=1,
            expected_minutes=75.0,
            p_appearance=0.95,
            p_start=0.90,
            p_60=0.80,
            coverage_status=CoverageStatus.FORECAST,
        )
        for player in official.players
    )
    return ProjectionSurface(
        schema_version=1,
        provider_id="adversarial-provider",
        provider_version="v1",
        generated_at="2026-09-02T12:00:00+00:00",
        season=official.season,
        source_snapshot=official.source_hash,
        scoring_rules_version="2026-2027",
        supported_horizons=(1,),
        runtime_dependencies=(),
        rows=rows,
    )


def _qualify(surface: ProjectionSurface, official: OfficialSnapshot):
    return qualify_surface(
        surface,
        official,
        decision_universe=official.decision_universe(),
        requested_horizons=(1,),
        max_age_hours=18.0,
        now=datetime(2026, 9, 2, 13, tzinfo=timezone.utc),
    )


def test_projection_from_different_official_snapshot_cannot_qualify():
    official = _official()
    surface = replace(_surface(official), source_snapshot="official-snapshot-B")

    result = _qualify(surface, official)

    assert result.operational == Qualification.UNQUALIFIED
    assert any("snapshot" in reason.casefold() for reason in result.reasons)


def test_projection_gameweek_unknown_to_official_snapshot_is_invalid():
    official = _official()
    surface = _surface(official)
    bad_rows = tuple(replace(row, gameweek=99) for row in surface.rows)
    surface = replace(surface, rows=bad_rows)

    errors = validate_projection_surface(surface, official)

    assert any("gameweek" in error.casefold() for error in errors)


def test_projection_fixture_id_must_exist_in_official_snapshot():
    official = _official()
    surface = _surface(official)
    first = replace(surface.rows[0], fixture_ids=(999999,), n_fixtures=1)
    surface = replace(surface, rows=(first, *surface.rows[1:]))

    errors = validate_projection_surface(surface, official)

    assert any("fixture" in error.casefold() for error in errors)


def test_projection_fixture_gameweek_must_match_projection_gameweek():
    official = _official()
    extra_fixture = OfficialFixture(103, 3, 1, 2, "2026-09-19T14:00:00Z")
    official = replace(official, fixtures=(*official.fixtures, extra_fixture))
    surface = _surface(official)
    first = replace(surface.rows[0], fixture_ids=(103,), n_fixtures=1)
    surface = replace(surface, rows=(first, *surface.rows[1:]))

    errors = validate_projection_surface(surface, official)

    assert any("fixture" in error.casefold() and "gameweek" in error.casefold() for error in errors)
