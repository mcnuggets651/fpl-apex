from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from apex.domain.models import OfficialSnapshot, TeamState

from .price_transitions import (
    DeterministicMarketPricePath,
    InsufficientBudgetError,
    PriceStateError,
    TransferPriceState,
    apply_transfer_price_transition,
)
from .transfers import TransferWeek


@dataclass(frozen=True)
class PriceScenario:
    scenario_id: str
    probability: float
    path: DeterministicMarketPricePath = DeterministicMarketPricePath()

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise PriceStateError("price scenario ID must be non-empty")
        probability = float(self.probability)
        if not 0.0 <= probability <= 1.0:
            raise PriceStateError("price scenario probability must be between 0 and 1")


@dataclass(frozen=True)
class RoutePriceStep:
    horizon: int
    gameweek: int
    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    bank_before_tenths: int
    bank_after_tenths: int
    sale_proceeds_tenths: int
    purchase_cost_tenths: int


@dataclass(frozen=True)
class RoutePriceEvaluation:
    scenario_id: str
    probability: float
    feasible: bool
    steps: tuple[RoutePriceStep, ...]
    end_bank_tenths: int | None
    failure_horizon: int | None = None
    reason: str | None = None


@dataclass(frozen=True)
class RoutePriceScenarioSummary:
    evaluations: tuple[RoutePriceEvaluation, ...]
    route_survival_probability: float
    priced_out_probability: float
    expected_end_bank_tenths_given_survival: float | None
    minimum_end_bank_tenths_given_survival: int | None


def _official_current_prices(official: OfficialSnapshot) -> dict[int, int]:
    return {
        int(player.element_id): int(player.price_tenths)
        for player in official.players
    }


def evaluate_transfer_route_prices(
    official: OfficialSnapshot,
    team: TeamState,
    weeks: tuple[TransferWeek, ...],
    *,
    scenario: PriceScenario,
    require_baseline_bank_match: bool = False,
) -> RoutePriceEvaluation:
    """Replay one candidate route under one deterministic future price path.

    Football expected points are intentionally absent. This evaluator only
    determines whether the already-generated legal route remains affordable and
    what exact bank/purchase-price state results under the scenario.
    """
    current_prices = _official_current_prices(official)
    try:
        state = TransferPriceState.from_team_state(team, current_prices)
    except PriceStateError as exc:
        return RoutePriceEvaluation(
            scenario.scenario_id,
            float(scenario.probability),
            False,
            (),
            None,
            None,
            str(exc),
        )

    observed_steps: list[RoutePriceStep] = []
    previous_horizon = 0
    for week in weeks:
        horizon = int(week.horizon)
        if horizon <= previous_horizon:
            return RoutePriceEvaluation(
                scenario.scenario_id,
                float(scenario.probability),
                False,
                tuple(observed_steps),
                None,
                horizon,
                "transfer route horizons must be strictly increasing",
            )
        previous_horizon = horizon
        market_prices = scenario.path.materialise_horizon(horizon, current_prices)
        bank_before = state.bank_tenths
        try:
            transition = apply_transfer_price_transition(
                state,
                transfers_in=tuple(map(int, week.transfers_in)),
                transfers_out=tuple(map(int, week.transfers_out)),
                market_prices_tenths=market_prices,
            )
        except InsufficientBudgetError as exc:
            return RoutePriceEvaluation(
                scenario.scenario_id,
                float(scenario.probability),
                False,
                tuple(observed_steps),
                None,
                horizon,
                str(exc),
            )
        except PriceStateError as exc:
            return RoutePriceEvaluation(
                scenario.scenario_id,
                float(scenario.probability),
                False,
                tuple(observed_steps),
                None,
                horizon,
                str(exc),
            )

        state = transition.state
        step = RoutePriceStep(
            horizon=horizon,
            gameweek=int(week.gameweek),
            transfers_in=tuple(map(int, week.transfers_in)),
            transfers_out=tuple(map(int, week.transfers_out)),
            bank_before_tenths=bank_before,
            bank_after_tenths=state.bank_tenths,
            sale_proceeds_tenths=transition.sale_proceeds_tenths,
            purchase_cost_tenths=transition.purchase_cost_tenths,
        )
        observed_steps.append(step)
        if require_baseline_bank_match and state.bank_tenths != int(week.bank_tenths):
            return RoutePriceEvaluation(
                scenario.scenario_id,
                float(scenario.probability),
                False,
                tuple(observed_steps),
                None,
                horizon,
                "empty/current-price route replay disagrees with optimiser bank: "
                f"replayed={state.bank_tenths}, optimiser={week.bank_tenths}",
            )

    return RoutePriceEvaluation(
        scenario.scenario_id,
        float(scenario.probability),
        True,
        tuple(observed_steps),
        state.bank_tenths,
    )


def evaluate_transfer_route_price_scenarios(
    official: OfficialSnapshot,
    team: TeamState,
    weeks: tuple[TransferWeek, ...],
    scenarios: tuple[PriceScenario, ...],
) -> RoutePriceScenarioSummary:
    if not scenarios:
        raise PriceStateError("at least one price scenario is required")
    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise PriceStateError("price scenario IDs must be unique")
    probability_sum = sum(float(scenario.probability) for scenario in scenarios)
    if not isclose(probability_sum, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise PriceStateError(
            f"price scenario probabilities must sum to 1; observed={probability_sum}"
        )

    evaluations = tuple(
        evaluate_transfer_route_prices(
            official,
            team,
            weeks,
            scenario=scenario,
            require_baseline_bank_match=(not scenario.path.overrides),
        )
        for scenario in scenarios
    )
    survival_probability = sum(
        evaluation.probability for evaluation in evaluations if evaluation.feasible
    )
    surviving = [evaluation for evaluation in evaluations if evaluation.feasible]
    if survival_probability > 0.0:
        expected_end_bank = sum(
            evaluation.probability * int(evaluation.end_bank_tenths)
            for evaluation in surviving
            if evaluation.end_bank_tenths is not None
        ) / survival_probability
        minimum_end_bank = min(
            int(evaluation.end_bank_tenths)
            for evaluation in surviving
            if evaluation.end_bank_tenths is not None
        )
    else:
        expected_end_bank = None
        minimum_end_bank = None

    return RoutePriceScenarioSummary(
        evaluations=evaluations,
        route_survival_probability=survival_probability,
        priced_out_probability=max(0.0, 1.0 - survival_probability),
        expected_end_bank_tenths_given_survival=expected_end_bank,
        minimum_end_bank_tenths_given_survival=minimum_end_bank,
    )
