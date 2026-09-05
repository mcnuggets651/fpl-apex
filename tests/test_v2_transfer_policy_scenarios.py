from __future__ import annotations

import pytest

from apex.decision.price_transitions import PriceStateError
from apex.decision.transfer_policy import ScenarioActionValue, summarise_transfer_policy


def test_policy_selects_expected_fpl_points_not_team_value() -> None:
    values = (
        ScenarioActionValue("ROLL", "flat", 0.5, 12.0, True, 10),
        ScenarioActionValue("ROLL", "rise", 0.5, 12.0, True, 10),
        # BUY has less bank in every state but more expected FPL points.
        ScenarioActionValue("BUY", "flat", 0.5, 13.0, True, 0),
        ScenarioActionValue("BUY", "rise", 0.5, 13.0, True, 0),
    )

    summary = summarise_transfer_policy(values)

    assert summary.selected_action_id == "BUY"
    buy = next(action for action in summary.actions if action.action_id == "BUY")
    roll = next(action for action in summary.actions if action.action_id == "ROLL")
    assert buy.expected_points == pytest.approx(13.0)
    assert buy.expected_points_regret == pytest.approx(0.0)
    assert roll.expected_points_regret == pytest.approx(1.0)
    assert buy.expected_end_bank_tenths_given_survival == pytest.approx(0.0)
    assert roll.expected_end_bank_tenths_given_survival == pytest.approx(10.0)


def test_policy_reports_probability_optimal_price_out_and_quantiles() -> None:
    values = (
        ScenarioActionValue("ROLL", "flat", 0.6, 10.0, True, 5),
        ScenarioActionValue("ROLL", "rise", 0.4, 9.0, True, 5),
        ScenarioActionValue("BUY", "flat", 0.6, 9.0, True, 1),
        # Caller supplies the legal fallback continuation value if the preferred
        # BUY route is priced out. The policy layer never invents a penalty.
        ScenarioActionValue("BUY", "rise", 0.4, 12.0, False, None),
    )

    summary = summarise_transfer_policy(values)

    assert summary.selected_action_id == "BUY"
    buy = next(action for action in summary.actions if action.action_id == "BUY")
    roll = next(action for action in summary.actions if action.action_id == "ROLL")
    assert buy.expected_points == pytest.approx(10.2)
    assert roll.expected_points == pytest.approx(9.6)
    assert buy.probability_optimal == pytest.approx(0.4)
    assert roll.probability_optimal == pytest.approx(0.6)
    assert buy.priced_out_probability == pytest.approx(0.4)
    assert buy.p10_expected_points == pytest.approx(9.0)
    assert buy.p50_expected_points == pytest.approx(9.0)
    assert buy.p90_expected_points == pytest.approx(12.0)


def test_policy_requires_every_action_in_every_scenario() -> None:
    values = (
        ScenarioActionValue("ROLL", "flat", 0.5, 10.0, True, 5),
        ScenarioActionValue("ROLL", "rise", 0.5, 10.0, True, 5),
        ScenarioActionValue("BUY", "flat", 0.5, 11.0, True, 0),
    )

    with pytest.raises(PriceStateError, match="every action requires"):
        summarise_transfer_policy(values)


def test_policy_requires_probabilities_to_sum_to_one() -> None:
    values = (
        ScenarioActionValue("ROLL", "a", 0.4, 10.0, True, 5),
        ScenarioActionValue("ROLL", "b", 0.4, 10.0, True, 5),
    )

    with pytest.raises(PriceStateError, match="sum to 1"):
        summarise_transfer_policy(values)


def test_policy_rejects_surviving_route_without_exact_bank() -> None:
    values = (ScenarioActionValue("ROLL", "flat", 1.0, 10.0, True, None),)

    with pytest.raises(PriceStateError, match="must report its exact end bank"):
        summarise_transfer_policy(values)
