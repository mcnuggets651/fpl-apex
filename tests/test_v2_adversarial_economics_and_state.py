from __future__ import annotations

from dataclasses import replace

from apex.decision.transfers import optimise_transfer_horizon
from apex.decision.validate import validate_system_decision
from apex.domain.models import (
    CertificationState,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
    ProviderHealth,
    ProviderRole,
    ProviderStatus,
    Qualification,
    ReasonCode,
    SystemDecision,
    TeamState,
)
from apex.governance.certification import certify


def _legal_players(*, price_tenths: int = 50) -> tuple[OfficialPlayer, ...]:
    specs = (
        (Position.GK, (1, 2)),
        (Position.DEF, (1, 2, 3, 4, 5)),
        (Position.MID, (3, 4, 5, 6, 7)),
        (Position.FWD, (6, 7, 8)),
    )
    players = []
    player_id = 1
    for position, team_ids in specs:
        for team_id in team_ids:
            players.append(
                OfficialPlayer(
                    player_id,
                    f"P{player_id}",
                    team_id,
                    position,
                    price_tenths,
                    "a",
                    True,
                )
            )
            player_id += 1
    return tuple(players)


def _legal_decision(*, mode: str = "INITIAL_SQUAD") -> SystemDecision:
    # 1 GK + 3 DEF + 4 MID + 3 FWD. Bench is reserve GK, 2 DEF, 1 MID.
    return SystemDecision(
        1,
        tuple(range(1, 16)),
        (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15),
        13,
        14,
        (2, 6, 7, 12),
        decision_mode=mode,
    )


def test_initial_squad_over_100m_is_illegal_at_decision_boundary():
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T12:00:00Z",
        "snap",
        _legal_players(price_tenths=80),
        (),
        {2: "2026-09-12T10:00:00Z"},
    )

    errors = validate_system_decision(official, _legal_decision())

    assert any("budget exceeded" in error for error in errors)


def test_certification_cannot_authorize_over_budget_initial_squad():
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T12:00:00Z",
        "snap",
        _legal_players(price_tenths=80),
        (),
        {2: "2026-09-12T10:00:00Z"},
    )
    serving = ProviderStatus(
        "champion",
        ProviderRole.CHAMPION,
        0,
        ProviderHealth.HEALTHY,
        {1: Qualification.QUALIFIED},
        None,
        (),
        True,
    )

    result = certify(
        official=official,
        serving=serving,
        decision=_legal_decision(),
    )

    assert result.state == CertificationState.BLOCKED
    assert result.actionable is False
    assert ReasonCode.DECISION_ILLEGAL in result.reasons
    assert any("budget exceeded" in warning for warning in result.warnings)


def _transfer_case():
    players = list(_legal_players())
    player_id = 16
    for position in Position:
        for index in range(4):
            players.append(
                OfficialPlayer(
                    player_id,
                    f"A{player_id}",
                    9 + index,
                    position,
                    50,
                    "a",
                    True,
                )
            )
            player_id += 1

    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-02T12:00:00Z",
        "snap",
        tuple(players),
        (),
        {
            1: "2026-08-15T10:00:00Z",
            2: "2026-08-22T10:00:00Z",
            3: "2026-08-29T10:00:00Z",
            4: "2026-09-05T10:00:00Z",
            5: "2026-09-12T10:00:00Z",
            6: "2026-09-19T10:00:00Z",
        },
    )
    squad = tuple(range(1, 16))
    team = TeamState(
        1,
        1,
        4,
        squad,
        0,
        1,
        {player: 50 for player in squad},
        {player: 50 for player in squad},
        None,
        True,
    )
    rows = []
    for player in players:
        rows.extend(
            (
                ProjectionRow(
                    player.element_id,
                    5,
                    1,
                    10.0 if player.element_id > 15 else 3.0,
                ),
                ProjectionRow(
                    player.element_id,
                    6,
                    2,
                    10.0 if player.element_id > 15 else 3.0,
                ),
            )
        )
    surface = ProductionProjectionSurface(
        1,
        "p",
        "v",
        "2026-09-02T12:00:00Z",
        official.season,
        official.source_hash,
        "2026-2027",
        (1, 2),
        tuple(rows),
    )
    return official, team, surface


def test_transfer_plan_week_labels_follow_team_state_not_season_minimum_deadline():
    official, team, surface = _transfer_case()

    result = optimise_transfer_horizon(
        official,
        surface,
        team,
        max_horizon=2,
    )

    assert result.status == "OPTIMAL"
    assert tuple(week.gameweek for week in result.weeks) == (5, 6)
