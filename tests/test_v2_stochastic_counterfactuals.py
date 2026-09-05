from __future__ import annotations

from dataclasses import replace

import pytest

from apex.decision.price_scenarios import PriceScenario
from apex.decision.price_transitions import DeterministicMarketPricePath, PriceStateError
from apex.decision.stochastic_counterfactuals import (
    optimise_stochastic_transfer_policy_for_root_action,
)
from apex.decision.stochastic_transfers import optimise_stochastic_transfer_policy
from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
    TeamState,
)


def _fixture() -> tuple[OfficialSnapshot, TeamState, ProductionProjectionSurface]:
    positions = {
        1: Position.GK,
        2: Position.GK,
        3: Position.DEF,
        4: Position.DEF,
        5: Position.DEF,
        6: Position.DEF,
        7: Position.DEF,
        8: Position.MID,
        9: Position.MID,
        10: Position.MID,
        11: Position.MID,
        12: Position.MID,
        13: Position.FWD,
        14: Position.FWD,
        15: Position.FWD,
        18: Position.MID,
        20: Position.MID,
        21: Position.MID,
    }
    constrained_club_ids = {8, 9, 10, 18, 20, 21}
    players = tuple(
        OfficialPlayer(
            element_id,
            f"P{element_id}",
            99 if element_id in constrained_club_ids else element_id,
            position,
            50,
            "a",
            True,
        )
        for element_id, position in positions.items()
    )
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-05T08:00:00Z",
        "official",
        players,
        (),
        {
            4: "2026-09-12T10:00:00Z",
            5: "2026-09-19T10:00:00Z",
        },
    )
    squad = tuple(range(1, 16))
    prices = {element_id: 50 for element_id in squad}
    team = TeamState(
        1,
        63984,
        3,
        squad,
        0,
        1,
        dict(prices),
        dict(prices),
        None,
        True,
    )

    rows = []
    for player in players:
        for horizon in (1, 2):
            points = 3.0
            if player.element_id in {9, 10}:
                points = 30.0
            elif player.element_id == 18:
                points = 20.0 if horizon == 1 else 0.0
            elif player.element_id == 20:
                points = 0.0 if horizon == 1 else 20.0
            elif player.element_id == 21:
                points = 0.0 if horizon == 1 else 6.0
            rows.append(
                ProjectionRow(
                    player.element_id,
                    3 + horizon,
                    horizon,
                    points,
                    p_appearance=1.0,
                )
            )
    surface = ProductionProjectionSurface(
        1,
        "airsenal",
        "pinned",
        "2026-09-05T08:00:00Z",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        (1, 2),
        tuple(rows),
    )
    return official, team, surface


def _stress_scenarios() -> tuple[PriceScenario, ...]:
    return (
        PriceScenario("flat", 0.5),
        PriceScenario(
            "target-rises",
            0.5,
            DeterministicMarketPricePath.from_mapping({2: {20: 51}}),
        ),
    )


def _root(result):
    return next(node for node in result.node_decisions if node.horizon == 1)


def test_counterfactual_can_pin_roll_on_same_stochastic_tree() -> None:
    official, team, surface = _fixture()
    unconstrained = optimise_stochastic_transfer_policy(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
    )
    roll = optimise_stochastic_transfer_policy_for_root_action(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
        root_transfers_in=(),
        root_transfers_out=(),
    )

    assert unconstrained.status == roll.status == "OPTIMAL"
    assert _root(roll).transfers_in == ()
    assert _root(roll).transfers_out == ()
    assert roll.decision is not None
    assert roll.decision.transfers_in == ()
    assert roll.decision.transfers_out == ()
    assert roll.expected_objective is not None
    assert unconstrained.expected_objective is not None
    assert unconstrained.expected_objective >= roll.expected_objective - 1e-9
    assert roll.solver["counterfactual_root_pinned"] is True
    assert roll.solver["counterfactual_root_transfer_count"] == 0
    assert roll.solver["counterfactual_diagnostic_only"] is True


def test_counterfactual_can_pin_exact_transfer_root() -> None:
    official, team, surface = _fixture()
    result = optimise_stochastic_transfer_policy_for_root_action(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
        root_transfers_in=(18,),
        root_transfers_out=(8,),
    )

    assert result.status == "OPTIMAL"
    assert _root(result).transfers_in == (18,)
    assert _root(result).transfers_out == (8,)
    assert result.decision is not None
    assert result.decision.transfers_in == (18,)
    assert result.decision.transfers_out == (8,)
    assert result.solver["counterfactual_root_transfer_count"] == 1
    # Manager-private element IDs must not be copied into public solver diagnostics.
    assert "root_transfers_in" not in result.solver
    assert "root_transfers_out" not in result.solver
    assert not any(isinstance(value, (tuple, list, set, dict)) for value in result.solver.values())


def test_counterfactual_rejects_illegal_root_action() -> None:
    official, team, surface = _fixture()
    with pytest.raises(PriceStateError, match="unowned"):
        optimise_stochastic_transfer_policy_for_root_action(
            official,
            surface,
            team,
            _stress_scenarios(),
            max_horizon=2,
            root_transfers_in=(18,),
            root_transfers_out=(21,),
        )

    with pytest.raises(PriceStateError, match="already-owned"):
        optimise_stochastic_transfer_policy_for_root_action(
            official,
            surface,
            team,
            _stress_scenarios(),
            max_horizon=2,
            root_transfers_in=(8,),
            root_transfers_out=(11,),
        )


def test_counterfactual_rejects_flat_tree_and_preserves_compatibility_path() -> None:
    official, team, surface = _fixture()
    with pytest.raises(PriceStateError, match="non-flat"):
        optimise_stochastic_transfer_policy_for_root_action(
            official,
            surface,
            team,
            (PriceScenario("flat", 1.0),),
            max_horizon=2,
            root_transfers_in=(),
            root_transfers_out=(),
        )


def test_counterfactual_executes_exactly_one_underlying_stochastic_milp(monkeypatch) -> None:
    official, team, surface = _fixture()
    from apex.decision import stochastic_transfers

    real_milp = stochastic_transfers.milp
    calls = []

    def counted_milp(*args, **kwargs):
        calls.append(1)
        return real_milp(*args, **kwargs)

    monkeypatch.setattr(stochastic_transfers, "milp", counted_milp)
    result = optimise_stochastic_transfer_policy_for_root_action(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
        root_transfers_in=(),
        root_transfers_out=(),
    )

    assert result.status == "OPTIMAL"
    assert len(calls) == 1
    assert stochastic_transfers.milp is counted_milp


def test_counterfactual_fails_closed_on_incomplete_exact_price_state(monkeypatch) -> None:
    official, team, surface = _fixture()
    purchase = dict(team.purchase_prices_tenths)
    del purchase[1]
    incomplete = replace(team, purchase_prices_tenths=purchase)

    from apex.decision import stochastic_transfers

    def forbidden(*args, **kwargs):
        raise AssertionError("no MILP may run with incomplete exact owner price state")

    monkeypatch.setattr(stochastic_transfers, "milp", forbidden)
    result = optimise_stochastic_transfer_policy_for_root_action(
        official,
        surface,
        incomplete,
        _stress_scenarios(),
        max_horizon=2,
        root_transfers_in=(),
        root_transfers_out=(),
    )

    assert result.status == "WITHHELD_TEAM_STATE_INCOMPLETE"
    assert result.solver["counterfactual_root_pinned"] is True
    assert result.solver["counterfactual_diagnostic_only"] is True
