from __future__ import annotations

from apex.domain.models import (
    CertificationState,
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    ProviderHealth,
    ProviderRole,
    ProviderStatus,
    Qualification,
    SystemDecision,
)
from apex.domain.rules import validate_squad, validate_xi
from apex.forecast.contract import coverage_errors, validate_projection_surface
from apex.forecast.registry import NoServingProvider, serving_provider
from apex.governance.certification import certify


def official() -> OfficialSnapshot:
    players = []
    pid = 1
    for team_id in range(1, 8):
        for position, count in (
            (Position.GK, 1),
            (Position.DEF, 2),
            (Position.MID, 2),
            (Position.FWD, 1),
        ):
            for _ in range(count):
                players.append(
                    OfficialPlayer(pid, f"P{pid}", team_id, position, 45, "a", True)
                )
                pid += 1
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T00:00:00+00:00",
        "abc",
        tuple(players),
        (),
        {2: "2026-08-28T17:30:00Z"},
    )


def surface(ids, provider="p", no_forecast=()) -> ProjectionSurface:
    no_forecast = set(no_forecast)
    rows = []
    for pid in ids:
        no = pid in no_forecast
        rows.append(
            ProjectionRow(
                pid,
                2,
                1,
                None if no else 3.0,
                coverage_status=(
                    CoverageStatus.NO_FORECAST if no else CoverageStatus.FORECAST
                ),
                coverage_reason="UNMAPPED" if no else None,
            )
        )
    return ProjectionSurface(
        1,
        provider,
        "v1",
        "2026-08-28T00:00:00Z",
        "2026-2027",
        "s",
        "2026-27",
        (1,),
        (),
        tuple(rows),
    )


def test_no_forecast_is_not_complete_serving_coverage():
    o = official()
    universe = o.decision_universe()
    s = surface(universe, no_forecast=(min(universe),))
    assert coverage_errors(s, universe, horizon=1)
    status = ProviderStatus(
        "p",
        ProviderRole.CHAMPION,
        0,
        ProviderHealth.HEALTHY,
        {1: Qualification.QUALIFIED},
        s,
    )
    try:
        serving_provider([status], horizon=1, decision_universe=universe)
    except NoServingProvider:
        pass
    else:
        raise AssertionError("incomplete provider must not serve")


def test_shadow_cannot_serve_even_when_complete():
    o = official()
    universe = o.decision_universe()
    s = surface(universe)
    status = ProviderStatus(
        "p",
        ProviderRole.SHADOW,
        0,
        ProviderHealth.HEALTHY,
        {1: Qualification.QUALIFIED},
        s,
    )
    try:
        serving_provider([status], horizon=1, decision_universe=universe)
    except NoServingProvider:
        pass
    else:
        raise AssertionError("shadow provider must never serve")


def test_surface_rejects_unknown_ids():
    o = official()
    s = surface([999])
    errors = validate_projection_surface(s, o)
    assert any("unknown Official FPL id" in error for error in errors)


def test_certification_ignores_shadow_warning_for_actionability():
    o = official()
    universe = o.decision_universe()
    s = surface(universe)
    serving = ProviderStatus(
        "p",
        ProviderRole.CHAMPION,
        0,
        ProviderHealth.HEALTHY,
        {1: Qualification.QUALIFIED},
        s,
    )
    players = o.player_map()
    by_team_pos = {}
    for player in o.players:
        by_team_pos.setdefault((player.team_id, player.position), []).append(player.element_id)
    squad = tuple(
        [by_team_pos[(1, Position.GK)][0], by_team_pos[(2, Position.GK)][0]]
        + [by_team_pos[(team, Position.DEF)][0] for team in range(1, 6)]
        + [by_team_pos[(team, Position.MID)][0] for team in range(1, 6)]
        + [by_team_pos[(team, Position.FWD)][0] for team in range(3, 6)]
    )
    assert not validate_squad(players, squad)
    xi = tuple(
        [by_team_pos[(1, Position.GK)][0]]
        + [by_team_pos[(team, Position.DEF)][0] for team in range(1, 4)]
        + [by_team_pos[(team, Position.MID)][0] for team in range(1, 5)]
        + [by_team_pos[(team, Position.FWD)][0] for team in range(3, 6)]
    )
    assert not validate_xi(players, squad, xi)
    bench = list(set(squad) - set(xi))
    bgk = next(pid for pid in bench if players[pid].position == Position.GK)
    out = sorted(pid for pid in bench if pid != bgk)
    decision = SystemDecision(
        1,
        tuple(sorted(squad)),
        tuple(sorted(xi)),
        xi[1],
        xi[2],
        (bgk, *out),
    )
    result = certify(
        official=o,
        serving=serving,
        decision=decision,
        shadow_warnings=("shadow dead",),
    )
    assert result.state == CertificationState.DEGRADED
    assert result.actionable
