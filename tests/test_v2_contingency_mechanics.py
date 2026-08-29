from __future__ import annotations

from itertools import product

import pytest

from apex.decision.mechanics import (
    _autosub_weights,
    _best_captain_vice,
    _expected_autosub_points,
    _state_probability,
    best_fixed_squad_mechanics,
)
from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
)


def _squad_players() -> tuple[OfficialPlayer, ...]:
    rows = []
    player_id = 1
    for position, count in (
        (Position.GK, 2),
        (Position.DEF, 5),
        (Position.MID, 5),
        (Position.FWD, 3),
    ):
        for _ in range(count):
            rows.append(
                OfficialPlayer(
                    player_id,
                    f"P{player_id}",
                    player_id,
                    position,
                    45,
                    "a",
                    True,
                )
            )
            player_id += 1
    return tuple(rows)


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-29T12:00:00Z",
        "official",
        _squad_players(),
        (),
        {3: "2026-09-05T10:00:00Z"},
    )


def _surface(
    xp: dict[int, float],
    appearance: dict[int, float | None],
) -> ProductionProjectionSurface:
    return ProductionProjectionSurface(
        1,
        "airsenal",
        "pinned",
        "2026-08-29T12:00:00Z",
        "2026-2027",
        "official",
        "fpl-2026-27-v1",
        (1,),
        tuple(
            ProjectionRow(
                player_id,
                3,
                1,
                points,
                p_appearance=appearance[player_id],
            )
            for player_id, points in sorted(xp.items())
        ),
    )


def test_captain_vice_values_no_show_fallback() -> None:
    captain, vice, bonus = _best_captain_vice(
        (1, 2, 3),
        {1: 8.0, 2: 7.8, 3: 7.0},
        {1: 0.55, 2: 0.99, 3: 0.99},
    )
    assert captain == 1
    assert vice == 2
    assert bonus == pytest.approx(8.0 + 0.45 * 7.8)


def test_three_defender_formation_blocks_midfield_autosub() -> None:
    positions = {
        player.element_id: player.position
        for player in _squad_players()
    }
    # Submitted 3-4-3. Defender 3 is guaranteed to miss. MID12 is first
    # substitute but cannot legally replace a defender; DEF6 can.
    xi = (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15)
    bench = (2, 6, 7, 12)
    appearance = {player_id: 1.0 for player_id in range(1, 16)}
    appearance[3] = 0.0
    xp = {player_id: 4.0 for player_id in range(1, 16)}
    xp[6] = 6.0
    xp[12] = 20.0

    value = _expected_autosub_points(
        xi,
        bench,
        positions,
        xp,
        appearance,
        outfield_order=(12, 6, 7),
    )
    assert value == pytest.approx(6.0)


def test_aggregated_autosub_matches_full_player_state_enumeration() -> None:
    positions = {
        player.element_id: player.position
        for player in _squad_players()
    }
    xi = (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15)
    bench = (2, 6, 7, 12)
    order = (12, 6, 7)
    appearance = {
        player_id: 0.70 + (player_id % 5) * 0.05
        for player_id in range(1, 16)
    }
    xp = {
        player_id: 1.5 + player_id / 3.0
        for player_id in range(1, 16)
    }

    aggregated = _expected_autosub_points(
        xi,
        bench,
        positions,
        xp,
        appearance,
        outfield_order=order,
    )

    starters = tuple(
        player_id
        for player_id in xi
        if positions[player_id] != Position.GK
    )
    brute = (1.0 - appearance[1]) * xp[2]
    for starter_bits in product((0, 1), repeat=len(starters)):
        starter_probability = _state_probability(
            starter_bits,
            [appearance[player_id] for player_id in starters],
        )
        missing_by_position = {
            Position.DEF: 0,
            Position.MID: 0,
            Position.FWD: 0,
        }
        for player_id, appears in zip(starters, starter_bits, strict=True):
            if not appears:
                missing_by_position[positions[player_id]] += 1

        for bench_bits in product((0, 1), repeat=3):
            state_probability = starter_probability * _state_probability(
                bench_bits,
                [appearance[player_id] for player_id in order],
            )
            live_counts = {
                position: sum(positions[player_id] == position for player_id in starters)
                for position in (Position.DEF, Position.MID, Position.FWD)
            }
            missing = dict(missing_by_position)
            for player_id, appears in zip(order, bench_bits, strict=True):
                if not appears or not any(missing.values()):
                    continue
                for missing_position in (Position.DEF, Position.MID, Position.FWD):
                    if missing[missing_position] <= 0:
                        continue
                    trial = dict(live_counts)
                    trial[missing_position] -= 1
                    trial[positions[player_id]] += 1
                    if (
                        3 <= trial[Position.DEF] <= 5
                        and 2 <= trial[Position.MID] <= 5
                        and 1 <= trial[Position.FWD] <= 3
                    ):
                        live_counts = trial
                        missing[missing_position] -= 1
                        brute += (
                            state_probability
                            * xp[player_id]
                            / appearance[player_id]
                        )
                        break

    assert aggregated == pytest.approx(brute)


def test_fixed_squad_mechanics_uses_exact_contingency_ev() -> None:
    xp = {
        player.element_id: 2.0 + player.element_id / 10.0
        for player in _squad_players()
    }
    appearance = {
        player.element_id: 0.80 + (player.element_id % 4) * 0.05
        for player in _squad_players()
    }
    mechanics = best_fixed_squad_mechanics(
        _official(),
        _surface(xp, appearance),
        tuple(range(1, 16)),
    )
    assert mechanics.contingency_complete is True
    assert mechanics.mechanics_warning is None
    assert mechanics.expected_autosub_points is not None
    assert mechanics.expected_autosub_points > 0.0
    assert mechanics.expected_captain_bonus is not None
    assert mechanics.submitted_ev == pytest.approx(
        mechanics.expected_xi_points
        + mechanics.expected_autosub_points
        + mechanics.expected_captain_bonus
    )
    assert mechanics.captain_id != mechanics.vice_captain_id
    assert len(mechanics.bench_order) == 4


def test_incomplete_appearance_inputs_never_claim_exact_mechanics() -> None:
    xp = {player.element_id: 3.0 for player in _squad_players()}
    appearance = {player.element_id: 0.9 for player in _squad_players()}
    appearance[15] = None
    mechanics = best_fixed_squad_mechanics(
        _official(),
        _surface(xp, appearance),
        tuple(range(1, 16)),
    )
    assert mechanics.contingency_complete is False
    assert "lacks complete appearance probabilities" in mechanics.mechanics_warning


def test_hard_exclusion_forces_zero_appearance_in_autosub_model() -> None:
    positions = {
        player.element_id: player.position
        for player in _squad_players()
    }
    xi = (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15)
    bench = (2, 6, 7, 12)
    appearance = {player_id: 1.0 for player_id in range(1, 16)}
    appearance[12] = 0.0
    weights = _autosub_weights(
        xi,
        bench,
        positions,
        appearance,
        outfield_order=(12, 6, 7),
    )
    assert weights[12] == 0.0


def test_ruled_out_reserve_goalkeeper_has_no_phantom_autosub_value() -> None:
    positions = {
        player.element_id: player.position
        for player in _squad_players()
    }
    xi = (1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15)
    bench = (2, 6, 7, 12)
    appearance = {player_id: 1.0 for player_id in range(1, 16)}
    appearance[1] = 0.0
    appearance[2] = 0.0
    xp = {player_id: 0.0 for player_id in range(1, 16)}
    xp[2] = 50.0

    weights = _autosub_weights(
        xi,
        bench,
        positions,
        appearance,
        outfield_order=(6, 7, 12),
    )
    value = _expected_autosub_points(
        xi,
        bench,
        positions,
        xp,
        appearance,
        outfield_order=(6, 7, 12),
    )
    assert weights[2] == 0.0
    assert value == 0.0
