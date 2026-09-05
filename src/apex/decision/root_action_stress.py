from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from apex.domain.models import OfficialSnapshot, TeamState

from .price_scenarios import PriceScenario, evaluate_transfer_route_prices
from .price_transitions import PriceStateError
from .transfers import TransferCandidateRoute


@dataclass(frozen=True, order=True)
class RootTransferAction:
    """The current transfer action shared by one or more continuation routes."""

    transfers_in: tuple[int, ...]
    transfers_out: tuple[int, ...]
    hits: int

    def __post_init__(self) -> None:
        incoming = tuple(map(int, self.transfers_in))
        outgoing = tuple(map(int, self.transfers_out))
        if incoming != tuple(sorted(incoming)) or outgoing != tuple(sorted(outgoing)):
            raise PriceStateError("root transfer IDs must be sorted")
        if len(incoming) != len(set(incoming)) or len(outgoing) != len(set(outgoing)):
            raise PriceStateError("root transfer IDs must be unique")
        if len(incoming) != len(outgoing):
            raise PriceStateError("root transfer-in and transfer-out counts must match")
        if set(incoming) & set(outgoing):
            raise PriceStateError("root transfer cannot buy and sell the same element")
        if isinstance(self.hits, bool) or not isinstance(self.hits, int) or self.hits < 0:
            raise PriceStateError("root transfer hits must be a non-negative integer")

    @classmethod
    def from_candidate(cls, candidate: TransferCandidateRoute) -> RootTransferAction:
        incoming, outgoing, hits = candidate.root_action
        return cls(tuple(incoming), tuple(outgoing), int(hits))


@dataclass(frozen=True)
class FixedRouteScenarioStress:
    """Survival of baseline-generated continuations under one price scenario."""

    action: RootTransferAction
    scenario_id: str
    probability: float
    candidate_route_count: int
    surviving_candidate_count: int
    surviving_generation_ranks: tuple[int, ...]
    best_surviving_generation_rank: int | None
    best_surviving_exact_objective: float | None
    best_surviving_end_bank_tenths: int | None
    all_baseline_continuations_priced_out: bool


@dataclass(frozen=True)
class RootActionFixedRouteStress:
    action: RootTransferAction
    scenario_results: tuple[FixedRouteScenarioStress, ...]
    candidate_route_count: int
    contains_baseline_selected_route: bool
    probability_any_baseline_continuation_survives: float
    probability_all_baseline_continuations_priced_out: float
    diagnostic_only: bool = True
    requires_scenario_reoptimisation: bool = True


@dataclass(frozen=True)
class FixedRouteStressMatrix:
    """Diagnostic-only fixed-route price stress matrix.

    This object deliberately has no selected action. Baseline-price candidate
    routes are not a complete scenario action space: a price change can make a
    baseline route infeasible, but it can also unlock a route that the baseline
    optimiser could not generate. Therefore this matrix may diagnose route
    survival and price fragility only. Scenario-conditioned re-optimisation (or
    an equivalent certified stochastic solve) is required before any scenario
    values may drive a serving transfer-policy selector.
    """

    actions: tuple[RootActionFixedRouteStress, ...]
    scenario_ids: tuple[str, ...]
    diagnostic_only: bool = True
    can_select_serving_action: bool = False
    requires_scenario_reoptimisation: bool = True


def stress_candidate_routes_by_root_action(
    official: OfficialSnapshot,
    team: TeamState,
    candidate_routes: tuple[TransferCandidateRoute, ...],
    scenarios: tuple[PriceScenario, ...],
) -> FixedRouteStressMatrix:
    if not candidate_routes:
        raise PriceStateError("fixed-route stress requires transfer candidate routes")
    if not scenarios:
        raise PriceStateError("fixed-route stress requires price scenarios")

    scenario_ids = tuple(scenario.scenario_id for scenario in scenarios)
    if len(scenario_ids) != len(set(scenario_ids)):
        raise PriceStateError("price scenario IDs must be unique")
    probabilities = tuple(float(scenario.probability) for scenario in scenarios)
    if any(
        not isfinite(probability) or not 0.0 <= probability <= 1.0
        for probability in probabilities
    ):
        raise PriceStateError("price scenario probabilities must be finite values in [0, 1]")
    if not isclose(sum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise PriceStateError("price scenario probabilities must sum to 1")

    ranks = [int(candidate.generation_rank) for candidate in candidate_routes]
    if any(rank < 1 for rank in ranks) or len(ranks) != len(set(ranks)):
        raise PriceStateError("candidate generation ranks must be unique positive integers")
    if sum(bool(candidate.baseline_selected) for candidate in candidate_routes) != 1:
        raise PriceStateError("candidate routes must identify exactly one baseline-selected route")

    grouped: dict[RootTransferAction, list[TransferCandidateRoute]] = {}
    for candidate in candidate_routes:
        if not candidate.weeks:
            raise PriceStateError("transfer candidate route must contain at least one week")
        action = RootTransferAction.from_candidate(candidate)
        grouped.setdefault(action, []).append(candidate)

    action_summaries: list[RootActionFixedRouteStress] = []
    for action in sorted(grouped):
        routes = tuple(sorted(grouped[action], key=lambda route: route.generation_rank))
        scenario_results: list[FixedRouteScenarioStress] = []
        survival_probability = 0.0

        for scenario in scenarios:
            evaluated = []
            for route in routes:
                evaluation = evaluate_transfer_route_prices(
                    official,
                    team,
                    route.weeks,
                    scenario=scenario,
                    require_baseline_bank_match=(not scenario.path.overrides),
                )
                evaluated.append((route, evaluation))

            surviving = [
                (route, evaluation)
                for route, evaluation in evaluated
                if evaluation.feasible
            ]
            if surviving:
                survival_probability += float(scenario.probability)
                best_route, best_evaluation = min(
                    surviving,
                    key=lambda item: (
                        -float(item[0].exact_objective),
                        int(item[0].generation_rank),
                    ),
                )
                best_rank = int(best_route.generation_rank)
                best_objective = float(best_route.exact_objective)
                best_bank = (
                    None
                    if best_evaluation.end_bank_tenths is None
                    else int(best_evaluation.end_bank_tenths)
                )
            else:
                best_rank = None
                best_objective = None
                best_bank = None

            scenario_results.append(
                FixedRouteScenarioStress(
                    action=action,
                    scenario_id=scenario.scenario_id,
                    probability=float(scenario.probability),
                    candidate_route_count=len(routes),
                    surviving_candidate_count=len(surviving),
                    surviving_generation_ranks=tuple(
                        int(route.generation_rank) for route, _ in surviving
                    ),
                    best_surviving_generation_rank=best_rank,
                    best_surviving_exact_objective=best_objective,
                    best_surviving_end_bank_tenths=best_bank,
                    all_baseline_continuations_priced_out=(not surviving),
                )
            )

        action_summaries.append(
            RootActionFixedRouteStress(
                action=action,
                scenario_results=tuple(scenario_results),
                candidate_route_count=len(routes),
                contains_baseline_selected_route=any(
                    candidate.baseline_selected for candidate in routes
                ),
                probability_any_baseline_continuation_survives=survival_probability,
                probability_all_baseline_continuations_priced_out=max(
                    0.0,
                    1.0 - survival_probability,
                ),
            )
        )

    return FixedRouteStressMatrix(
        actions=tuple(action_summaries),
        scenario_ids=scenario_ids,
    )
