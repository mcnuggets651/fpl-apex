from __future__ import annotations

import pytest
pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st

from apex.decision.mechanics import _autosub_weights, best_fixed_squad_mechanics
from apex.domain.models import (
    CoverageStatus,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
)

PROB = st.floats(min_value=-2.0, max_value=3.0, allow_nan=False, allow_infinity=False)
XP = st.floats(min_value=0.0, max_value=30.0, allow_nan=False, allow_infinity=False)


def _standard_positions():
    xi = tuple(range(1, 12))
    bench = (12, 13, 14, 15)
    positions = {
        1: Position.GK,
        2: Position.DEF, 3: Position.DEF, 4: Position.DEF, 5: Position.DEF,
        6: Position.MID, 7: Position.MID, 8: Position.MID, 9: Position.MID,
        10: Position.FWD, 11: Position.FWD,
        12: Position.GK, 13: Position.DEF, 14: Position.MID, 15: Position.FWD,
    }
    return xi, bench, positions


@given(probabilities=st.lists(PROB, min_size=15, max_size=15))
@settings(max_examples=40, deadline=None)
def test_autosub_conditional_use_weights_are_probabilities(probabilities):
    xi, bench, positions = _standard_positions()
    appearance = {player_id: probabilities[player_id - 1] for player_id in range(1, 16)}
    weights = _autosub_weights(
        xi,
        bench,
        positions,
        appearance,
        outfield_order=(13, 14, 15),
    )
    assert set(weights) == set(bench)
    assert all(-1e-12 <= weight <= 1.0 + 1e-12 for weight in weights.values())


def _mechanics_fixture(xp_values, appearance_values):
    positions = [Position.GK] * 2 + [Position.DEF] * 5 + [Position.MID] * 5 + [Position.FWD] * 3
    players = tuple(
        OfficialPlayer(index + 1, f"P{index + 1}", (index % 8) + 1, position, 50, "a", True)
        for index, position in enumerate(positions)
    )
    official = OfficialSnapshot(
        1, "2026-2027", "2026-09-03T06:00:00Z", "official", players, (), {3: "2026-09-12T10:00:00Z"}
    )
    rows = tuple(
        ProjectionRow(
            player.element_id, 3, 1, xp_values[player.element_id - 1],
            p_appearance=appearance_values[player.element_id - 1],
            coverage_status=CoverageStatus.FORECAST,
        )
        for player in players
    )
    surface = ProductionProjectionSurface(
        1, "airsenal", "property-v1", "2026-09-03T06:00:00Z", official.season,
        official.source_hash, "fpl-2026-27-v1", (1,), rows,
    )
    return official, surface, tuple(range(1, 16))


@given(
    xp_values=st.lists(XP, min_size=15, max_size=15),
    appearances=st.lists(
        st.floats(min_value=0.05, max_value=1.0, allow_nan=False, allow_infinity=False),
        min_size=15, max_size=15,
    ),
)
@settings(max_examples=10, deadline=None)
def test_complete_mechanics_ev_equals_its_exact_components(xp_values, appearances):
    official, surface, squad = _mechanics_fixture(xp_values, appearances)
    result = best_fixed_squad_mechanics(official, surface, squad)
    assert result.contingency_complete is True
    assert result.mechanics_warning is None
    assert result.expected_xi_points is not None
    assert result.expected_autosub_points is not None
    assert result.expected_captain_bonus is not None
    assert result.captain_id in result.xi_ids
    assert result.vice_captain_id in result.xi_ids
    assert result.captain_id != result.vice_captain_id
    assert result.submitted_ev == pytest.approx(
        result.expected_xi_points + result.expected_autosub_points + result.expected_captain_bonus,
        abs=1e-9,
    )
