from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from apex.domain.models import TeamState


class PriceStateError(ValueError):
    """Raised when a future transfer-price state cannot be certified exactly."""


class InsufficientBudgetError(PriceStateError):
    """Raised when a transfer route is unaffordable under a market-price state."""


def _price_tenths(value: int, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise PriceStateError(f"{field} must be an integer number of £0.1 units")
    if value < 0:
        raise PriceStateError(f"{field} must be non-negative")
    return value


def fpl_selling_price_tenths(
    purchase_price_tenths: int,
    market_price_tenths: int,
) -> int:
    """Return exact FPL sale proceeds in £0.1 units.

    Losses are realised in full. On a gain, the manager receives the purchase
    price plus half of the gain, rounded down to the nearest £0.1.
    """
    purchase = _price_tenths(purchase_price_tenths, field="purchase price")
    market = _price_tenths(market_price_tenths, field="market price")
    if market <= purchase:
        return market
    return purchase + (market - purchase) // 2


@dataclass(frozen=True)
class DeterministicMarketPricePath:
    """Sparse deterministic future market-price path used for replay/scenarios.

    Horizon overrides are immutable state transitions. Once a player's price is
    overridden, that market price carries forward through later horizons until a
    later override changes it again. Players never overridden keep the supplied
    current market price. An empty path is therefore exactly equivalent to
    today's deterministic-price production semantics.
    """

    overrides: tuple[tuple[int, tuple[tuple[int, int], ...]], ...] = ()

    @classmethod
    def from_mapping(
        cls,
        overrides: Mapping[int, Mapping[int, int]] | None,
    ) -> DeterministicMarketPricePath:
        if not overrides:
            return cls()
        normalised: list[tuple[int, tuple[tuple[int, int], ...]]] = []
        for raw_horizon, raw_prices in overrides.items():
            horizon = int(raw_horizon)
            if horizon < 1:
                raise PriceStateError("price-path horizons must be positive")
            prices: list[tuple[int, int]] = []
            for raw_element_id, raw_price in raw_prices.items():
                element_id = int(raw_element_id)
                if element_id < 1:
                    raise PriceStateError("price-path element IDs must be positive")
                price = _price_tenths(int(raw_price), field="market price")
                prices.append((element_id, price))
            normalised.append((horizon, tuple(sorted(prices))))
        horizons = [horizon for horizon, _ in normalised]
        if len(horizons) != len(set(horizons)):
            raise PriceStateError("price-path horizons must be unique")
        return cls(tuple(sorted(normalised)))

    def market_price_tenths(
        self,
        element_id: int,
        horizon: int,
        current_market_prices_tenths: Mapping[int, int],
    ) -> int:
        element_id = int(element_id)
        horizon = int(horizon)
        if horizon < 1:
            raise PriceStateError("price-path horizons must be positive")
        try:
            price = _price_tenths(
                int(current_market_prices_tenths[element_id]),
                field="current market price",
            )
        except KeyError as exc:
            raise PriceStateError(
                f"current market price missing for element {element_id}"
            ) from exc
        for candidate_horizon, pairs in self.overrides:
            if candidate_horizon > horizon:
                break
            candidate_prices = dict(pairs)
            if element_id in candidate_prices:
                price = candidate_prices[element_id]
        return price

    def materialise_horizon(
        self,
        horizon: int,
        current_market_prices_tenths: Mapping[int, int],
    ) -> dict[int, int]:
        return {
            int(element_id): self.market_price_tenths(
                int(element_id),
                int(horizon),
                current_market_prices_tenths,
            )
            for element_id in current_market_prices_tenths
        }


@dataclass(frozen=True)
class TransferPriceState:
    """Exact route-specific bank and purchase-price basis.

    `purchase_prices_tenths` contains only currently owned players. Future
    market prices are deliberately not stored here: they are scenario inputs at
    each transition. A newly bought player's market price becomes their purchase
    basis for every later sale in that route.
    """

    bank_tenths: int
    purchase_prices_tenths: tuple[tuple[int, int], ...]

    @classmethod
    def from_team_state(
        cls,
        team: TeamState,
        current_market_prices_tenths: Mapping[int, int],
        *,
        verify_observed_selling_prices: bool = True,
    ) -> TransferPriceState:
        if not team.state_complete_for_transfers:
            raise PriceStateError("exact TeamState is incomplete for transfers")
        owned = tuple(map(int, team.squad_ids))
        if len(owned) != 15 or len(set(owned)) != 15:
            raise PriceStateError("exact TeamState must contain 15 unique players")
        if set(team.purchase_prices_tenths) != set(owned):
            raise PriceStateError("purchase-price state must cover the exact squad")
        if set(team.selling_prices_tenths) != set(owned):
            raise PriceStateError("selling-price state must cover the exact squad")

        purchase_pairs = []
        for element_id in owned:
            try:
                market = _price_tenths(
                    int(current_market_prices_tenths[element_id]),
                    field="current market price",
                )
            except KeyError as exc:
                raise PriceStateError(
                    f"current market price missing for owned element {element_id}"
                ) from exc
            purchase = _price_tenths(
                int(team.purchase_prices_tenths[element_id]),
                field="purchase price",
            )
            observed_sell = _price_tenths(
                int(team.selling_prices_tenths[element_id]),
                field="observed selling price",
            )
            if verify_observed_selling_prices:
                expected_sell = fpl_selling_price_tenths(purchase, market)
                if observed_sell != expected_sell:
                    raise PriceStateError(
                        "observed selling price disagrees with exact FPL mechanics "
                        f"for element {element_id}: observed={observed_sell}, "
                        f"expected={expected_sell}"
                    )
            purchase_pairs.append((element_id, purchase))

        return cls(
            _price_tenths(int(team.bank_tenths), field="bank"),
            tuple(sorted(purchase_pairs)),
        )

    @property
    def owned_ids(self) -> tuple[int, ...]:
        return tuple(element_id for element_id, _ in self.purchase_prices_tenths)

    def purchase_price_map(self) -> dict[int, int]:
        return dict(self.purchase_prices_tenths)

    def selling_price_tenths(
        self,
        element_id: int,
        market_prices_tenths: Mapping[int, int],
    ) -> int:
        purchase_prices = self.purchase_price_map()
        element_id = int(element_id)
        if element_id not in purchase_prices:
            raise PriceStateError(f"element {element_id} is not owned")
        try:
            market = _price_tenths(
                int(market_prices_tenths[element_id]),
                field="market price",
            )
        except KeyError as exc:
            raise PriceStateError(
                f"market price missing for element {element_id}"
            ) from exc
        return fpl_selling_price_tenths(purchase_prices[element_id], market)


@dataclass(frozen=True)
class TransferPriceTransition:
    state: TransferPriceState
    sale_proceeds_tenths: int
    purchase_cost_tenths: int


def apply_transfer_price_transition(
    state: TransferPriceState,
    *,
    transfers_in: tuple[int, ...],
    transfers_out: tuple[int, ...],
    market_prices_tenths: Mapping[int, int],
) -> TransferPriceTransition:
    """Apply one route step using exact FPL purchase/selling-price mechanics."""
    incoming = tuple(sorted(map(int, transfers_in)))
    outgoing = tuple(sorted(map(int, transfers_out)))
    if len(incoming) != len(outgoing):
        raise PriceStateError("transfer-in and transfer-out counts must match")
    if len(incoming) != len(set(incoming)) or len(outgoing) != len(set(outgoing)):
        raise PriceStateError("transfer IDs must be unique within a route step")
    if set(incoming) & set(outgoing):
        raise PriceStateError("the same element cannot be transferred in and out")

    purchase_prices = state.purchase_price_map()
    owned = set(purchase_prices)
    if not set(outgoing).issubset(owned):
        missing = sorted(set(outgoing) - owned)
        raise PriceStateError(f"cannot sell unowned elements: {missing}")
    if set(incoming) & owned:
        duplicates = sorted(set(incoming) & owned)
        raise PriceStateError(f"cannot buy already-owned elements: {duplicates}")

    sale_proceeds = sum(
        state.selling_price_tenths(element_id, market_prices_tenths)
        for element_id in outgoing
    )
    purchase_cost = 0
    for element_id in incoming:
        try:
            purchase_cost += _price_tenths(
                int(market_prices_tenths[element_id]),
                field="market price",
            )
        except KeyError as exc:
            raise PriceStateError(
                f"market price missing for element {element_id}"
            ) from exc

    bank_after = state.bank_tenths + sale_proceeds - purchase_cost
    if bank_after < 0:
        raise InsufficientBudgetError(
            "transfer route is unaffordable under this market-price state: "
            f"bank_after={bank_after}"
        )

    for element_id in outgoing:
        del purchase_prices[element_id]
    for element_id in incoming:
        # The actual market price paid in this route becomes the future purchase
        # basis. This is what makes later sell-on proceeds route-dependent.
        purchase_prices[element_id] = int(market_prices_tenths[element_id])

    next_state = TransferPriceState(
        bank_tenths=bank_after,
        purchase_prices_tenths=tuple(sorted(purchase_prices.items())),
    )
    return TransferPriceTransition(
        state=next_state,
        sale_proceeds_tenths=sale_proceeds,
        purchase_cost_tenths=purchase_cost,
    )