from __future__ import annotations

from apex.decision.validate import validate_system_decision
from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position, SystemDecision


def _official() -> OfficialSnapshot:
    specs = [
        (1, Position.GK, 1), (2, Position.GK, 2),
        (3, Position.DEF, 1), (4, Position.DEF, 2), (5, Position.DEF, 3),
        (6, Position.DEF, 4), (7, Position.DEF, 5),
        (8, Position.MID, 1), (9, Position.MID, 2), (10, Position.MID, 3),
        (11, Position.MID, 4), (12, Position.MID, 5),
        (13, Position.FWD, 3), (14, Position.FWD, 4), (15, Position.FWD, 5),
    ]
    players = tuple(
        OfficialPlayer(player_id, f"P{player_id}", team_id, position, 50, "a", True)
        for player_id, position, team_id in specs
    )
    return OfficialSnapshot(1, "2026-2027", "2026-09-03T06:00:00Z", "official", players, (), {})


def _decision(*, squad_ids, xi_ids, bench_order) -> SystemDecision:
    return SystemDecision(
        1,
        tuple(squad_ids),
        tuple(xi_ids),
        int(xi_ids[0]),
        int(xi_ids[1]),
        tuple(bench_order),
        decision_mode="INITIAL_SQUAD",
    )


def test_unknown_bench_player_fails_closed_instead_of_raising_keyerror():
    decision = _decision(
        squad_ids=tuple(range(1, 15)) + (999,),
        xi_ids=(1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15),
        bench_order=(2, 6, 7, 999),
    )
    errors = validate_system_decision(_official(), decision)
    assert any("unknown player ids" in error for error in errors)


def test_unknown_xi_player_fails_closed_instead_of_raising_keyerror():
    decision = _decision(
        squad_ids=tuple(range(1, 15)) + (999,),
        xi_ids=(1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 999),
        bench_order=(2, 6, 7, 15),
    )
    errors = validate_system_decision(_official(), decision)
    assert any("unknown player ids" in error for error in errors)
