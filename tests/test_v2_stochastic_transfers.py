from __future__ import annotations

from dataclasses import replace

import pytest

from apex.decision.price_scenarios import PriceScenario
from apex.decision.price_transitions import DeterministicMarketPricePath
from apex.decision.stochastic_transfers import optimise_stochastic_transfer_policy
from apex.decision.transfers import optimise_transfer_horizon
from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProductionProjectionSurface,
    ProjectionRow,
    TeamState,
)


def _fixture(*, max_horizon: int = 2) -> tuple[
    OfficialSnapshot,
    TeamState,
    ProductionProjectionSurface,
]:
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
    players = tuple(
        OfficialPlayer(
            element_id,
            f"P{element_id}",
            element_id,
            position,
            50,
            "a",
            True,
        )
        for element_id, position in positions.items()
    )
    deadlines = {
        4 + offset: f"2026-09-{12 + 7 * offset:02d}T10:00:00Z"
        for offset in range(max_horizon)
    }
    official = OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-05T08:00:00Z",
        "official",
        players,
        (),
        deadlines,
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
        for horizon in range(1, max_horizon + 1):
            points = 3.0
            if player.element_id == 18:
                points = 20.0 if horizon == 1 else 0.0
            elif player.element_id == 20:
                points = 0.0 if horizon == 1 else 20.0
            elif player.element_id == 21:
                # Deliberately useful as an H2 fallback, but not valuable enough
                # to justify paying an H1 hit merely to pre-own it. This keeps
                # the adaptation test focused on information timing rather than
                # accidentally rewarding a rational early-buy policy.
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
        tuple(range(1, max_horizon + 1)),
        tuple(rows),
    )
    return official, team, surface


def _node_for_price(result, *, horizon: int, element_id: int, price: int):
    tree = result.information_tree
    assert tree is not None
    node = next(
        node
        for node in tree.nodes_for_horizon(horizon)
        if node.market_price_map()[element_id] == price
    )
    return next(
        decision
        for decision in result.node_decisions
        if decision.node_id == node.node_id
    )


def test_flat_price_tree_reproduces_current_deterministic_decision_exactly(
    monkeypatch,
) -> None:
    official, team, surface = _fixture()
    baseline = optimise_transfer_horizon(
        official,
        surface,
        team,
        max_horizon=2,
        candidate_limit=1,
    )

    from apex.decision import transfers

    real_milp = transfers.milp
    calls = []

    def counted_milp(*args, **kwargs):
        calls.append(1)
        return real_milp(*args, **kwargs)

    monkeypatch.setattr(transfers, "milp", counted_milp)
    stochastic = optimise_stochastic_transfer_policy(
        official,
        surface,
        team,
        (PriceScenario("flat", 1.0),),
        max_horizon=2,
    )

    assert stochastic.status == baseline.status == "OPTIMAL"
    assert stochastic.decision == baseline.decision
    assert stochastic.solver["mode"] == "DETERMINISTIC_COMPATIBILITY"
    assert stochastic.solver["single_milp"] is True
    assert len(calls) == 1


def test_nonflat_policy_executes_exactly_one_stochastic_milp(monkeypatch) -> None:
    official, team, surface = _fixture()
    from apex.decision import stochastic_transfers

    real_milp = stochastic_transfers.milp
    calls = []

    def counted_milp(*args, **kwargs):
        calls.append(1)
        return real_milp(*args, **kwargs)

    monkeypatch.setattr(stochastic_transfers, "milp", counted_milp)
    scenarios = (
        PriceScenario("flat", 0.5),
        PriceScenario(
            "target-rises",
            0.5,
            DeterministicMarketPricePath.from_mapping({2: {20: 51}}),
        ),
    )
    result = optimise_stochastic_transfer_policy(
        official,
        surface,
        team,
        scenarios,
        max_horizon=2,
    )

    assert result.status == "OPTIMAL"
    assert result.solver["mode"] == "STOCHASTIC_PRICE_TREE"
    assert result.solver["single_milp"] is True
    assert len(calls) == 1


def test_future_action_adapts_only_after_target_price_is_observed() -> None:
    official, team, surface = _fixture()
    # The rise branch is intentionally low enough probability that paying an H1
    # hit to pre-buy P20 is inferior to waiting. Once H2 arrives, the realised
    # price state can legitimately change the optimal continuation.
    scenarios = (
        PriceScenario("flat", 0.8),
        PriceScenario(
            "target-rises",
            0.2,
            DeterministicMarketPricePath.from_mapping({2: {20: 51}}),
        ),
    )
    result = optimise_stochastic_transfer_policy(
        official,
        surface,
        team,
        scenarios,
        max_horizon=2,
    )

    assert result.status == "OPTIMAL"
    root = next(node for node in result.node_decisions if node.horizon == 1)
    assert root.transfers_in == (18,)
    assert root.transfers_out == (8,)

    flat_h2 = _node_for_price(result, horizon=2, element_id=20, price=50)
    rise_h2 = _node_for_price(result, horizon=2, element_id=20, price=51)
    assert flat_h2.transfers_in == (20,)
    assert flat_h2.transfers_out == (18,)
    assert rise_h2.transfers_in == (21,)
    assert rise_h2.transfers_out == (18,)


def test_future_sale_uses_actual_branch_purchase_basis_and_half_profit() -> None:
    official, team, surface = _fixture()
    scenario = PriceScenario(
        "sell-on-funds-target",
        1.0,
        DeterministicMarketPricePath.from_mapping(
            {2: {18: 52, 20: 51}}
        ),
    )
    result = optimise_stochastic_transfer_policy(
        official,
        surface,
        team,
        (scenario,),
        max_horizon=2,
    )

    assert result.status == "OPTIMAL"
    root = next(node for node in result.node_decisions if node.horizon == 1)
    h2 = next(node for node in result.node_decisions if node.horizon == 2)
    assert root.transfers_in == (18,)
    assert dict(root.purchase_prices_tenths)[18] == 50
    assert h2.transfers_in == (20,)
    assert h2.transfers_out == (18,)
    # Bought at 50, market 52 => exact FPL sale proceeds 51. Target costs 51.
    assert h2.bank_tenths == 0
    assert dict(h2.purchase_prices_tenths)[20] == 51


def test_h2_decision_cannot_see_h3_price_divergence() -> None:
    official, team, surface = _fixture(max_horizon=3)
    scenarios = (
        PriceScenario(
            "later-rise",
            0.5,
            DeterministicMarketPricePath.from_mapping(
                {2: {20: 51}, 3: {20: 52}}
            ),
        ),
        PriceScenario(
            "later-fall",
            0.5,
            DeterministicMarketPricePath.from_mapping(
                {2: {20: 51}, 3: {20: 50}}
            ),
        ),
    )
    result = optimise_stochastic_transfer_policy(
        official,
        surface,
        team,
        scenarios,
        max_horizon=3,
    )

    assert result.status == "OPTIMAL"
    assert result.information_tree is not None
    assert len(result.information_tree.nodes_for_horizon(2)) == 1
    assert len(result.information_tree.nodes_for_horizon(3)) == 2
    assert len([node for node in result.node_decisions if node.horizon == 2]) == 1
    assert len([node for node in result.node_decisions if node.horizon == 3]) == 2


def test_incomplete_purchase_price_state_withholds_without_any_milp(monkeypatch) -> None:
    official, team, surface = _fixture()
    purchase = dict(team.purchase_prices_tenths)
    del purchase[1]
    incomplete = replace(team, purchase_prices_tenths=purchase)

    from apex.decision import stochastic_transfers, transfers

    def forbidden(*args, **kwargs):
        raise AssertionError("no MILP may run with incomplete exact purchase-price state")

    monkeypatch.setattr(stochastic_transfers, "milp", forbidden)
    monkeypatch.setattr(transfers, "milp", forbidden)
    result = optimise_stochastic_transfer_policy(
        official,
        surface,
        incomplete,
        (PriceScenario("flat", 1.0),),
        max_horizon=2,
    )

    assert result.status == "WITHHELD_TEAM_STATE_INCOMPLETE"
    assert result.decision is not None
    assert result.decision.decision_mode == "HOLD_TEAM_STATE_INCOMPLETE"
    assert result.node_decisions == ()
    assert result.solver["single_milp"] is False
