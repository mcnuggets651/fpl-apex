from __future__ import annotations

from dataclasses import replace

from apex.decision.optimiser import optimise_initial_squad
from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
)
from apex.forecast.contract import production_view


def _players() -> tuple[OfficialPlayer, ...]:
    players: list[OfficialPlayer] = []
    player_id = 1
    for position, team_ids in (
        (Position.GK, (1, 2)),
        (Position.DEF, (1, 2, 3, 4, 5)),
        (Position.MID, (3, 4, 5, 6, 7)),
        (Position.FWD, (6, 7, 8)),
    ):
        for team_id in team_ids:
            players.append(
                OfficialPlayer(
                    player_id,
                    f"P{player_id}",
                    team_id,
                    position,
                    50,
                    "a",
                    True,
                )
            )
            player_id += 1

    for position in Position:
        for offset in range(4):
            players.append(
                OfficialPlayer(
                    player_id,
                    f"A{player_id}",
                    9 + offset,
                    position,
                    50,
                    "a",
                    True,
                )
            )
            player_id += 1
    return tuple(players)


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-03T06:00:00Z",
        "deterministic-official",
        _players(),
        (),
        {2: "2026-09-12T10:00:00Z"},
    )


def _surface(official: OfficialSnapshot):
    rows = tuple(
        ProjectionRow(
            player.element_id,
            2,
            1,
            5.0,
            expected_minutes=90.0,
            p_appearance=1.0,
            p_start=1.0,
            p_60=1.0,
            coverage_status=CoverageStatus.FORECAST,
        )
        for player in official.players
    )
    raw = ProjectionSurface(
        1,
        "airsenal",
        "tie-fixture",
        "2026-09-03T06:30:00Z",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        (1,),
        (),
        rows,
    )
    return production_view(raw, horizon=1)


def test_primary_optimum_tie_break_is_independent_of_catalogue_order():
    official = _official()
    surface = _surface(official)

    forward = optimise_initial_squad(
        official,
        surface,
        candidate_limit=1,
        candidate_regret_fraction=0.0,
    )
    reversed_official = replace(official, players=tuple(reversed(official.players)))
    reverse = optimise_initial_squad(
        reversed_official,
        surface,
        candidate_limit=1,
        candidate_regret_fraction=0.0,
    )

    assert forward.status == "OPTIMAL"
    assert reverse.status == "OPTIMAL"
    assert forward.decision is not None
    assert reverse.decision is not None
    assert forward.decision.squad_ids == tuple(range(1, 16))
    assert reverse.decision.squad_ids == tuple(range(1, 16))
    assert forward.decision == reverse.decision
    assert forward.raw_solver["primary_tiebreak"] == (
        "LEXICOGRAPHIC_SQUAD_BLOCKS_UNDER_EXACT_PRIMARY_LOCK"
    )
    assert reverse.raw_solver["primary_tiebreak"] == (
        "LEXICOGRAPHIC_SQUAD_BLOCKS_UNDER_EXACT_PRIMARY_LOCK"
    )
