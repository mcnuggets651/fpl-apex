from __future__ import annotations

from dataclasses import replace

from apex.decision.validate import validate_system_decision
from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    SystemDecision,
    TeamState,
)


def _official(*, incoming_price: int = 50, include_incoming: bool = True) -> OfficialSnapshot:
    specs = [
        (1, Position.GK, 1),
        (2, Position.GK, 2),
        (3, Position.DEF, 1),
        (4, Position.DEF, 2),
        (5, Position.DEF, 3),
        (6, Position.DEF, 4),
        (7, Position.DEF, 5),
        (8, Position.MID, 1),
        (9, Position.MID, 2),
        (10, Position.MID, 3),
        (11, Position.MID, 4),
        (12, Position.MID, 5),
        (13, Position.FWD, 3),
        (14, Position.FWD, 4),
        (15, Position.FWD, 5),
    ]
    players = [
        OfficialPlayer(player_id, f"P{player_id}", team_id, position, 50, "a", True)
        for player_id, position, team_id in specs
    ]
    if include_incoming:
        players.append(OfficialPlayer(16, "P16", 6, Position.DEF, incoming_price, "a", True))
    return OfficialSnapshot(1, "2026-2027", "2026-09-03T06:00:00Z", "official", tuple(players), (), {})


def _initial() -> SystemDecision:
    return SystemDecision(
        1,
        tuple(range(1, 16)),
        (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15),
        13,
        14,
        (2, 6, 7, 12),
        objective=50.0,
        horizon=1,
        decision_mode="INITIAL_SQUAD",
    )


def _team(**changes) -> TeamState:
    base = TeamState(
        1,
        63984,
        2,
        tuple(range(1, 16)),
        0,
        1,
        {player_id: 50 for player_id in range(1, 16)},
        {player_id: 50 for player_id in range(1, 16)},
        None,
        True,
    )
    return replace(base, **changes)


def _transfer(**changes) -> SystemDecision:
    base = SystemDecision(
        1,
        tuple(player_id for player_id in range(1, 17) if player_id != 7),
        (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15),
        13,
        14,
        (2, 6, 16, 12),
        transfers_in=(16,),
        transfers_out=(7,),
        objective=50.0,
        horizon=2,
        transfer_hits=0,
        decision_mode="TRANSFER_HORIZON",
    )
    return replace(base, **changes)


def _assert_error(errors: tuple[str, ...], needle: str) -> None:
    assert any(needle in error for error in errors), errors


def test_valid_initial_and_transfer_decisions_have_no_validator_errors():
    official = _official()
    assert validate_system_decision(official, _initial()) == ()
    assert validate_system_decision(official, _transfer(), _team()) == ()


def test_transfer_state_requires_complete_frozen_team_state():
    official = _official()
    _assert_error(
        validate_system_decision(official, _transfer(), None),
        "requires frozen team state",
    )
    _assert_error(
        validate_system_decision(
            official,
            _transfer(),
            _team(state_complete_for_transfers=False),
        ),
        "incomplete for transfers",
    )


def test_transfer_state_rejects_ownership_transition_and_price_incoherence():
    official = _official()
    _assert_error(
        validate_system_decision(
            official,
            _transfer(transfers_out=(99,)),
            _team(),
        ),
        "not owned",
    )
    _assert_error(
        validate_system_decision(
            official,
            _transfer(transfers_in=(6,), transfers_out=(7,), squad_ids=tuple(range(1, 16))),
            _team(),
        ),
        "already owned",
    )
    _assert_error(
        validate_system_decision(
            official,
            _transfer(squad_ids=tuple(range(1, 16))),
            _team(),
        ),
        "transition does not match",
    )
    selling = {player_id: 50 for player_id in range(1, 16) if player_id != 7}
    _assert_error(
        validate_system_decision(official, _transfer(), _team(selling_prices_tenths=selling)),
        "lacks exact selling price",
    )
    unknown = _transfer(
        transfers_in=(99,),
        squad_ids=tuple(player_id for player_id in range(1, 16) if player_id != 7) + (99,),
        bench_order=(2, 6, 99, 12),
    )
    _assert_error(
        validate_system_decision(_official(include_incoming=False), unknown, _team()),
        "unknown Official FPL ids",
    )


def test_transfer_state_rejects_unaffordable_ft_hit_and_horizon_state():
    expensive = _official(incoming_price=60)
    _assert_error(
        validate_system_decision(expensive, _transfer(), _team()),
        "cash affordability failed",
    )
    _assert_error(
        validate_system_decision(_official(), _transfer(), _team(free_transfers=99)),
        "free-transfer state outside",
    )
    _assert_error(
        validate_system_decision(_official(), _transfer(transfer_hits=1), _team()),
        "hit count does not match",
    )
    _assert_error(
        validate_system_decision(_official(), _transfer(horizon=1), _team()),
        "requires horizon >= 2",
    )


def test_generic_transfer_metadata_and_scalar_invariants_fail_closed():
    official = _official()
    cases = (
        (_transfer(transfers_in=(16, 16), transfers_out=(6, 7)), "duplicate player in permanent transfers in"),
        (_transfer(transfers_in=(16,), transfers_out=(7, 7)), "duplicate player in permanent transfers out"),
        (_transfer(transfers_in=(7,), transfers_out=(7,)), "same player cannot be transferred in and out"),
        (_transfer(transfers_out=()), "permanent transfers must balance"),
        (replace(_initial(), horizon=0), "decision horizon must be positive"),
        (replace(_initial(), transfer_hits=-1), "transfer hits cannot be negative"),
        (replace(_initial(), decision_mode="UNRECOGNISED"), "unknown decision mode"),
    )
    for decision, expected in cases:
        _assert_error(validate_system_decision(official, decision, _team()), expected)


def test_initial_hold_and_leadership_mode_rules_fail_closed():
    official = _official()
    initial = _initial()
    _assert_error(
        validate_system_decision(official, replace(initial, captain_id=2)),
        "captain must be in XI",
    )
    _assert_error(
        validate_system_decision(official, replace(initial, vice_captain_id=2)),
        "vice-captain must be in XI",
    )
    _assert_error(
        validate_system_decision(official, replace(initial, vice_captain_id=13)),
        "captain and vice-captain must differ",
    )
    _assert_error(
        validate_system_decision(
            official,
            replace(initial, transfers_in=(16,), transfers_out=(7,)),
        ),
        "INITIAL_SQUAD decision cannot contain transfer metadata",
    )
    _assert_error(
        validate_system_decision(official, replace(initial, transfer_hits=1)),
        "INITIAL_SQUAD decision cannot contain transfer hits",
    )

    hold = replace(initial, decision_mode="HOLD_H1_ONLY")
    _assert_error(
        validate_system_decision(
            official,
            replace(hold, transfers_in=(16,), transfers_out=(7,)),
            _team(),
        ),
        "hold decision cannot contain permanent transfers",
    )
    _assert_error(
        validate_system_decision(official, replace(hold, transfer_hits=1), _team()),
        "hold decision cannot contain transfer hits",
    )
    mutated = replace(
        hold,
        squad_ids=tuple(player_id for player_id in range(1, 16) if player_id != 7) + (16,),
        bench_order=(2, 6, 16, 12),
    )
    _assert_error(
        validate_system_decision(official, mutated, _team()),
        "hold decision cannot mutate frozen team-state squad",
    )
