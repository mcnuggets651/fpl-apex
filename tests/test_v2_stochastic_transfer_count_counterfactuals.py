from __future__ import annotations

from dataclasses import replace

import pytest

from apex.decision.price_scenarios import PriceScenario
from apex.decision.price_transitions import DeterministicMarketPricePath, PriceStateError
from apex.decision.stochastic_transfer_count_counterfactuals import (
    optimise_stochastic_transfer_policy_for_root_transfer_count,
)
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
        2,
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
                points = 8.0
            elif player.element_id == 18:
                points = 20.0 if horizon == 1 else 4.0
            elif player.element_id == 20:
                points = 17.0 if horizon == 1 else 15.0
            elif player.element_id == 21:
                points = 4.0 if horizon == 1 else 18.0
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
    rows = [node for node in result.node_decisions if node.horizon == 1]
    assert len(rows) == 1
    return rows[0]


def test_count_counterfactual_finds_best_legal_root_at_exact_count() -> None:
    official, team, surface = _fixture()
    one = optimise_stochastic_transfer_policy_for_root_transfer_count(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
        root_transfer_count=1,
    )
    two = optimise_stochastic_transfer_policy_for_root_transfer_count(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
        root_transfer_count=2,
    )

    assert one.status == two.status == "OPTIMAL"
    assert len(_root(one).transfers_in) == len(_root(one).transfers_out) == 1
    assert len(_root(two).transfers_in) == len(_root(two).transfers_out) == 2
    assert one.decision is not None and two.decision is not None
    assert len(one.decision.transfers_in) == 1
    assert len(two.decision.transfers_in) == 2
    assert one.solver["counterfactual_root_transfer_count_pinned"] is True
    assert two.solver["counterfactual_root_transfer_count"] == 2
    assert one.solver["counterfactual_diagnostic_only"] is True
    assert "root_transfers_in" not in one.solver
    assert "root_transfers_out" not in one.solver


def test_count_counterfactual_can_pin_roll_without_player_enumeration() -> None:
    official, team, surface = _fixture()
    roll = optimise_stochastic_transfer_policy_for_root_transfer_count(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
        root_transfer_count=0,
    )

    assert roll.status == "OPTIMAL"
    assert _root(roll).transfers_in == ()
    assert _root(roll).transfers_out == ()
    assert roll.decision is not None
    assert roll.decision.transfers_in == ()
    assert roll.decision.transfers_out == ()


def test_count_counterfactual_executes_exactly_one_underlying_milp(monkeypatch) -> None:
    official, team, surface = _fixture()
    from apex.decision import stochastic_transfers

    real_milp = stochastic_transfers.milp
    calls = []

    def counted_milp(*args, **kwargs):
        calls.append(1)
        return real_milp(*args, **kwargs)

    monkeypatch.setattr(stochastic_transfers, "milp", counted_milp)
    result = optimise_stochastic_transfer_policy_for_root_transfer_count(
        official,
        surface,
        team,
        _stress_scenarios(),
        max_horizon=2,
        root_transfer_count=1,
    )

    assert result.status == "OPTIMAL"
    assert len(calls) == 1
    assert stochastic_transfers.milp is counted_milp


def test_count_counterfactual_rejects_flat_tree_and_invalid_count() -> None:
    official, team, surface = _fixture()
    with pytest.raises(PriceStateError, match="non-flat"):
        optimise_stochastic_transfer_policy_for_root_transfer_count(
            official,
            surface,
            team,
            (PriceScenario("flat", 1.0),),
            max_horizon=2,
            root_transfer_count=0,
        )
    with pytest.raises(PriceStateError, match="integer"):
        optimise_stochastic_transfer_policy_for_root_transfer_count(
            official,
            surface,
            team,
            _stress_scenarios(),
            max_horizon=2,
            root_transfer_count=True,
        )
    with pytest.raises(PriceStateError, match="between 0 and 15"):
        optimise_stochastic_transfer_policy_for_root_transfer_count(
            official,
            surface,
            team,
            _stress_scenarios(),
            max_horizon=2,
            root_transfer_count=16,
        )


def test_count_counterfactual_fails_closed_on_incomplete_exact_price_state(monkeypatch) -> None:
    official, team, surface = _fixture()
    purchase = dict(team.purchase_prices_tenths)
    del purchase[1]
    incomplete = replace(team, purchase_prices_tenths=purchase)

    from apex.decision import stochastic_transfers

    def forbidden(*args, **kwargs):
        raise AssertionError("no MILP may run with incomplete exact owner price state")

    monkeypatch.setattr(stochastic_transfers, "milp", forbidden)
    with pytest.raises(PriceStateError, match="TeamState is incomplete"):
        optimise_stochastic_transfer_policy_for_root_transfer_count(
            official,
            surface,
            incomplete,
            _stress_scenarios(),
            max_horizon=2,
            root_transfer_count=1,
        )
    assert stochastic_transfers.milp is forbidden
