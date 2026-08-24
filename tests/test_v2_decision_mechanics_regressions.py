from __future__ import annotations

from fractions import Fraction
from itertools import permutations
from pathlib import Path

from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.decision import CandidatePlayer, DecisionChip
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.decision.mechanics import (
    PlayerGameweekValue,
    _autosub_weights,
    _starter_missing_distribution,
    optimise_squad_submission,
)


def _ruleset():
    return load_ruleset(Path("config/rules/2026-2027.yaml"))


def _squad() -> tuple[CandidatePlayer, ...]:
    positions = {
        1: "GK",
        2: "GK",
        3: "DEF",
        4: "DEF",
        5: "DEF",
        6: "DEF",
        7: "DEF",
        8: "MID",
        9: "MID",
        10: "MID",
        11: "MID",
        12: "MID",
        13: "FWD",
        14: "FWD",
        15: "FWD",
    }
    return tuple(
        CandidatePlayer(
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            position=position,
            current_price_tenths=50,
        )
        for player_id, position in positions.items()
    )


def _values(*, tied_defenders: bool = False) -> dict[OfficialPlayerId, PlayerGameweekValue]:
    starting_ids = {1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14}
    expected = {player_id: Fraction(10, 1) for player_id in starting_ids}
    expected.update(
        {
            2: Fraction(1, 1),
            6: Fraction(3, 1),
            7: Fraction(3 if tied_defenders else 4, 1),
            15: Fraction(2, 1),
            13: Fraction(15, 1),
            14: Fraction(14, 1),
        }
    )
    values: dict[OfficialPlayerId, PlayerGameweekValue] = {}
    for player_id in range(1, 16):
        pid = OfficialPlayerId(player_id)
        values[pid] = PlayerGameweekValue(
            player_id=pid,
            expected_points=expected[player_id],
            appearance_probability=(
                Fraction(1, 1)
                if player_id in {2, 6, 7, 15}
                else Fraction(1, 2)
            ),
        )
    return values


def test_submission_optimises_bench_order_and_captain_inside_exact_objective() -> None:
    result = optimise_squad_submission(
        _squad(),
        _values(),
        chip=DecisionChip.NONE,
        hit_points=0,
        ruleset=_ruleset(),
    )
    assert result.captain_id == OfficialPlayerId(13)
    assert result.vice_captain_id == OfficialPlayerId(14)
    assert result.bench_gk_id == OfficialPlayerId(2)
    assert result.outfield_bench_order == (
        OfficialPlayerId(7),
        OfficialPlayerId(6),
        OfficialPlayerId(15),
    )


def test_submission_ties_are_deterministic_under_reversed_input_order() -> None:
    values = _values(tied_defenders=True)
    first = optimise_squad_submission(
        _squad(),
        values,
        chip=DecisionChip.NONE,
        hit_points=0,
        ruleset=_ruleset(),
    )
    second = optimise_squad_submission(
        tuple(reversed(_squad())),
        values,
        chip=DecisionChip.NONE,
        hit_points=0,
        ruleset=_ruleset(),
    )
    assert first.xi_ids == second.xi_ids
    assert first.captain_id == second.captain_id
    assert first.vice_captain_id == second.vice_captain_id
    assert first.outfield_bench_order == second.outfield_bench_order
    assert first.mechanics == second.mechanics


def test_reused_starter_absence_distribution_matches_exact_recomputation() -> None:
    squad = _squad()
    values = _values()
    positions = {row.player_id: row.position for row in squad}
    appearance = {
        player_id: value.appearance_probability for player_id, value in values.items()
    }
    squad_ids = tuple(sorted(positions))
    xi_ids = tuple(
        OfficialPlayerId(player_id)
        for player_id in (1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14)
    )
    starters = tuple(pid for pid in xi_ids if positions[pid] != "GK")
    cached = _starter_missing_distribution(
        starters,
        positions=positions,
        appearance=appearance,
    )
    ruleset = _ruleset()
    minimum = {
        position: int(value)
        for position, value in ruleset.mapping("FPL-XI-POSITION-MIN-001").items()
    }
    maximum = {
        position: int(value)
        for position, value in ruleset.mapping("FPL-XI-POSITION-MAX-001").items()
    }
    outfield = tuple(OfficialPlayerId(player_id) for player_id in (6, 7, 15))
    for order in permutations(outfield):
        recomputed = _autosub_weights(
            xi_ids=xi_ids,
            squad_ids=squad_ids,
            positions=positions,
            appearance=appearance,
            outfield_order=order,
            minimum=minimum,
            maximum=maximum,
        )
        reused = _autosub_weights(
            xi_ids=xi_ids,
            squad_ids=squad_ids,
            positions=positions,
            appearance=appearance,
            outfield_order=order,
            minimum=minimum,
            maximum=maximum,
            missing_distribution=cached,
        )
        assert reused == recomputed
