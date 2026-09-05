from __future__ import annotations

import pytest

from apex.decision.price_scenarios import (
    PriceScenario,
    evaluate_transfer_route_price_scenarios,
    evaluate_transfer_route_prices,
)
from apex.decision.price_transitions import DeterministicMarketPricePath, PriceStateError
from apex.decision.transfers import TransferWeek
from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position, TeamState


def _fixture() -> tuple[OfficialSnapshot, TeamState]:
    players = tuple(
        OfficialPlayer(
            element_id,
            f"P{element_id}",
            element_id,
            Position.MID,
            50,
            "a",
            True,
        )
        for element_id in range(1, 21)
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
    return official, team


def _two_week_route(*, second_out: int = 2) -> tuple[TransferWeek, ...]:
    return (
        TransferWeek(
            horizon=1,
            gameweek=4,
            squad_ids=tuple(range(2, 17)),
            transfers_in=(16,),
            transfers_out=(1,),
            bank_tenths=0,
            free_transfers=2,
            hits=0,
            submitted_ev=60.0,
        ),
        TransferWeek(
            horizon=2,
            gameweek=5,
            squad_ids=tuple(
                sorted((set(range(2, 17)) - {second_out}) | {17})
            ),
            transfers_in=(17,),
            transfers_out=(second_out,),
            bank_tenths=0,
            free_transfers=1,
            hits=0,
            submitted_ev=61.0,
        ),
    )


def test_empty_price_path_reproduces_existing_route_bank_exactly() -> None:
    official, team = _fixture()
    scenario = PriceScenario("baseline", 1.0, DeterministicMarketPricePath())

    evaluation = evaluate_transfer_route_prices(
        official,
        team,
        _two_week_route(),
        scenario=scenario,
        require_baseline_bank_match=True,
    )

    assert evaluation.feasible is True
    assert evaluation.end_bank_tenths == 0
    assert tuple(step.bank_after_tenths for step in evaluation.steps) == (0, 0)


def test_target_rise_can_price_out_a_future_route() -> None:
    official, team = _fixture()
    scenario = PriceScenario(
        "target-rises",
        1.0,
        DeterministicMarketPricePath.from_mapping({2: {17: 51}}),
    )

    evaluation = evaluate_transfer_route_prices(
        official,
        team,
        _two_week_route(),
        scenario=scenario,
    )

    assert evaluation.feasible is False
    assert evaluation.failure_horizon == 2
    assert evaluation.end_bank_tenths is None
    assert "unaffordable" in str(evaluation.reason)


def test_route_specific_sell_on_gain_can_fund_later_move() -> None:
    official, team = _fixture()
    scenario = PriceScenario(
        "new-signing-rises",
        1.0,
        DeterministicMarketPricePath.from_mapping({2: {16: 53}}),
    )

    evaluation = evaluate_transfer_route_prices(
        official,
        team,
        _two_week_route(second_out=16),
        scenario=scenario,
    )

    assert evaluation.feasible is True
    # Element 16 was bought at 50 in H1. At 53 in H2 it sells for 51.
    assert evaluation.steps[1].sale_proceeds_tenths == 51
    assert evaluation.end_bank_tenths == 1


def test_scenario_summary_reports_route_survival_and_price_out_probability() -> None:
    official, team = _fixture()
    scenarios = (
        PriceScenario("flat", 0.6, DeterministicMarketPricePath()),
        PriceScenario(
            "rise",
            0.4,
            DeterministicMarketPricePath.from_mapping({2: {17: 51}}),
        ),
    )

    summary = evaluate_transfer_route_price_scenarios(
        official,
        team,
        _two_week_route(),
        scenarios,
    )

    assert summary.route_survival_probability == pytest.approx(0.6)
    assert summary.priced_out_probability == pytest.approx(0.4)
    assert summary.expected_end_bank_tenths_given_survival == pytest.approx(0.0)
    assert summary.minimum_end_bank_tenths_given_survival == 0


def test_scenario_probabilities_must_sum_to_one() -> None:
    official, team = _fixture()
    scenarios = (
        PriceScenario("a", 0.4),
        PriceScenario("b", 0.4),
    )

    with pytest.raises(PriceStateError, match="sum to 1"):
        evaluate_transfer_route_price_scenarios(
            official,
            team,
            _two_week_route(),
            scenarios,
        )
