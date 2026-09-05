from __future__ import annotations

import pytest

from apex.decision.price_transitions import (
    DeterministicMarketPricePath,
    InsufficientBudgetError,
    PriceStateError,
    TransferPriceState,
    apply_transfer_price_transition,
    fpl_selling_price_tenths,
)
from apex.domain.models import TeamState


def _team_state(*, bank_tenths: int = 10) -> TeamState:
    squad = tuple(range(1, 16))
    purchases = {element_id: 50 for element_id in squad}
    purchases[1] = 45
    purchases[2] = 55
    market = {element_id: 50 for element_id in squad}
    selling = {
        element_id: fpl_selling_price_tenths(purchases[element_id], market[element_id])
        for element_id in squad
    }
    return TeamState(
        1,
        63984,
        3,
        squad,
        bank_tenths,
        2,
        purchases,
        selling,
        None,
        True,
    )


def _current_prices() -> dict[int, int]:
    return {element_id: 50 for element_id in range(1, 40)}


@pytest.mark.parametrize(
    ("purchase", "market", "selling"),
    [
        (75, 74, 74),
        (75, 75, 75),
        (75, 76, 75),
        (75, 77, 76),
        (75, 78, 76),
        (75, 79, 77),
    ],
)
def test_fpl_selling_price_exact_half_profit_rounding(
    purchase: int,
    market: int,
    selling: int,
) -> None:
    assert fpl_selling_price_tenths(purchase, market) == selling


def test_price_path_empty_is_exact_current_price_fallback() -> None:
    current = _current_prices()
    path = DeterministicMarketPricePath.from_mapping(None)

    assert path.market_price_tenths(1, 1, current) == 50
    assert path.market_price_tenths(17, 8, current) == 50
    assert path.materialise_horizon(4, current) == current


def test_price_path_sparse_override_does_not_mutate_other_players() -> None:
    current = _current_prices()
    path = DeterministicMarketPricePath.from_mapping({1: {16: 51}, 2: {16: 52, 17: 49}})

    assert path.market_price_tenths(16, 1, current) == 51
    assert path.market_price_tenths(17, 1, current) == 50
    assert path.market_price_tenths(16, 2, current) == 52
    assert path.market_price_tenths(17, 2, current) == 49
    assert path.market_price_tenths(1, 2, current) == 50


def test_price_path_sparse_change_carries_forward_until_next_override() -> None:
    current = _current_prices()
    path = DeterministicMarketPricePath.from_mapping({1: {16: 51}, 4: {16: 52}})

    assert path.market_price_tenths(16, 1, current) == 51
    assert path.market_price_tenths(16, 2, current) == 51
    assert path.market_price_tenths(16, 3, current) == 51
    assert path.market_price_tenths(16, 4, current) == 52
    assert path.market_price_tenths(16, 8, current) == 52
    assert path.market_price_tenths(17, 8, current) == 50


def test_initial_price_state_verifies_exact_observed_selling_prices() -> None:
    team = _team_state()
    state = TransferPriceState.from_team_state(team, _current_prices())

    assert state.bank_tenths == 10
    assert state.owned_ids == tuple(range(1, 16))
    assert state.selling_price_tenths(1, _current_prices()) == 47
    assert state.selling_price_tenths(2, _current_prices()) == 50


def test_initial_price_state_fails_closed_on_inconsistent_observed_sale_price() -> None:
    team = _team_state()
    selling = dict(team.selling_prices_tenths)
    selling[1] += 1
    inconsistent = TeamState(
        team.schema_version,
        team.entry_id,
        team.published_gw,
        team.squad_ids,
        team.bank_tenths,
        team.free_transfers,
        dict(team.purchase_prices_tenths),
        selling,
        team.active_chip,
        team.state_complete_for_transfers,
    )

    with pytest.raises(PriceStateError, match="observed selling price disagrees"):
        TransferPriceState.from_team_state(inconsistent, _current_prices())


def test_future_sale_uses_route_specific_purchase_basis() -> None:
    current = _current_prices()
    team = _team_state(bank_tenths=10)
    state = TransferPriceState.from_team_state(team, current)

    first_market = dict(current)
    first_market[16] = 55
    first = apply_transfer_price_transition(
        state,
        transfers_in=(16,),
        transfers_out=(2,),
        market_prices_tenths=first_market,
    )

    # Sell element 2 for 50, buy element 16 at 55: bank 10 -> 5.
    assert first.sale_proceeds_tenths == 50
    assert first.purchase_cost_tenths == 55
    assert first.state.bank_tenths == 5
    assert first.state.purchase_price_map()[16] == 55

    second_market = dict(current)
    second_market[16] = 58
    second_market[17] = 50
    second = apply_transfer_price_transition(
        first.state,
        transfers_in=(17,),
        transfers_out=(16,),
        market_prices_tenths=second_market,
    )

    # The £5.5 route purchase is the basis: £5.8 market sells for £5.6.
    assert second.sale_proceeds_tenths == 56
    assert second.purchase_cost_tenths == 50
    assert second.state.bank_tenths == 11
    assert second.state.purchase_price_map()[17] == 50
    assert 16 not in second.state.purchase_price_map()


def test_future_price_drop_is_realised_in_full() -> None:
    current = _current_prices()
    state = TransferPriceState.from_team_state(_team_state(bank_tenths=10), current)
    buy_market = dict(current)
    buy_market[16] = 55
    bought = apply_transfer_price_transition(
        state,
        transfers_in=(16,),
        transfers_out=(2,),
        market_prices_tenths=buy_market,
    )

    sell_market = dict(current)
    sell_market[16] = 53
    assert bought.state.selling_price_tenths(16, sell_market) == 53


def test_price_transition_rejects_unaffordable_route() -> None:
    current = _current_prices()
    state = TransferPriceState.from_team_state(_team_state(bank_tenths=0), current)
    market = dict(current)
    market[16] = 60

    with pytest.raises(InsufficientBudgetError, match="unaffordable"):
        apply_transfer_price_transition(
            state,
            transfers_in=(16,),
            transfers_out=(2,),
            market_prices_tenths=market,
        )


def test_price_transition_rejects_illegal_ownership_changes() -> None:
    current = _current_prices()
    state = TransferPriceState.from_team_state(_team_state(), current)

    with pytest.raises(PriceStateError, match="unowned"):
        apply_transfer_price_transition(
            state,
            transfers_in=(16,),
            transfers_out=(30,),
            market_prices_tenths=current,
        )
    with pytest.raises(PriceStateError, match="already-owned"):
        apply_transfer_price_transition(
            state,
            transfers_in=(3,),
            transfers_out=(2,),
            market_prices_tenths=current,
        )