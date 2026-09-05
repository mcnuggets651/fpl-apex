from __future__ import annotations

from dataclasses import dataclass
from math import isclose

from .price_transitions import PriceStateError


@dataclass(frozen=True)
class ScenarioActionValue:
    """Continuation value for one root action under one price scenario.

    `expected_points` must already include the legal continuation policy and hit
    costs for this action/scenario. Price/bank fields are diagnostics only and
    never enter the objective inside this module.
    """

    action_id: str
    scenario_id: str
    probability: float
    expected_points: float
    route_survives: bool
    end_bank_tenths: int | None


@dataclass(frozen=True)
class TransferPolicyActionSummary:
    action_id: str
    expected_points: float
    p10_expected_points: float
    p50_expected_points: float
    p90_expected_points: float
    probability_optimal: float
    priced_out_probability: float
    expected_end_bank_tenths_given_survival: float | None
    minimum_end_bank_tenths_given_survival: int | None
    expected_points_regret: float


@dataclass(frozen=True)
class TransferPolicySummary:
    selected_action_id: str
    actions: tuple[TransferPolicyActionSummary, ...]


def _weighted_quantile(
    values: list[tuple[float, float]],
    quantile: float,
) -> float:
    if not values:
        raise PriceStateError("cannot calculate policy quantile without values")
    ordered = sorted((float(value), float(weight)) for value, weight in values)
    threshold = float(quantile)
    cumulative = 0.0
    for value, weight in ordered:
        cumulative += weight
        if cumulative + 1e-12 >= threshold:
            return value
    return ordered[-1][0]


def summarise_transfer_policy(
    values: tuple[ScenarioActionValue, ...],
) -> TransferPolicySummary:
    """Select the max expected-FPL-points root action across sealed scenarios.

    Every action must have one continuation value for every scenario. This is a
    deliberate fail-closed boundary: callers may not omit an unaffordable branch
    and thereby make an action look better. If a preferred route is priced out,
    the caller must provide the legal fallback/re-optimised continuation value.
    """
    if not values:
        raise PriceStateError("transfer policy requires scenario action values")

    actions = sorted({row.action_id for row in values})
    scenarios = sorted({row.scenario_id for row in values})
    if any(not action.strip() for action in actions):
        raise PriceStateError("transfer action IDs must be non-empty")
    if any(not scenario.strip() for scenario in scenarios):
        raise PriceStateError("price scenario IDs must be non-empty")

    by_pair: dict[tuple[str, str], ScenarioActionValue] = {}
    scenario_probability: dict[str, float] = {}
    for row in values:
        key = (row.action_id, row.scenario_id)
        if key in by_pair:
            raise PriceStateError(
                f"duplicate transfer-policy value for action/scenario {key}"
            )
        probability = float(row.probability)
        if not 0.0 <= probability <= 1.0:
            raise PriceStateError("scenario probabilities must be between 0 and 1")
        previous = scenario_probability.setdefault(row.scenario_id, probability)
        if not isclose(previous, probability, rel_tol=0.0, abs_tol=1e-12):
            raise PriceStateError(
                f"scenario probability disagrees across actions: {row.scenario_id}"
            )
        if row.route_survives and row.end_bank_tenths is None:
            raise PriceStateError(
                "surviving transfer route must report its exact end bank"
            )
        by_pair[key] = row

    expected_pairs = {(action, scenario) for action in actions for scenario in scenarios}
    missing = sorted(expected_pairs - set(by_pair))
    if missing:
        raise PriceStateError(
            "every action requires a value for every price scenario; missing="
            f"{missing}"
        )
    probability_sum = sum(scenario_probability.values())
    if not isclose(probability_sum, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise PriceStateError(
            f"price scenario probabilities must sum to 1; observed={probability_sum}"
        )

    optimal_actions_by_scenario: dict[str, set[str]] = {}
    for scenario in scenarios:
        best = max(by_pair[(action, scenario)].expected_points for action in actions)
        optimal_actions_by_scenario[scenario] = {
            action
            for action in actions
            if isclose(
                by_pair[(action, scenario)].expected_points,
                best,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
        }

    provisional: list[dict] = []
    for action in actions:
        rows = [by_pair[(action, scenario)] for scenario in scenarios]
        expected_points = sum(
            scenario_probability[row.scenario_id] * float(row.expected_points)
            for row in rows
        )
        point_distribution = [
            (float(row.expected_points), scenario_probability[row.scenario_id])
            for row in rows
        ]
        priced_out_probability = sum(
            scenario_probability[row.scenario_id]
            for row in rows
            if not row.route_survives
        )
        probability_optimal = sum(
            scenario_probability[scenario]
            for scenario in scenarios
            if action in optimal_actions_by_scenario[scenario]
        )
        surviving = [row for row in rows if row.route_survives]
        survival_probability = 1.0 - priced_out_probability
        if survival_probability > 0.0:
            expected_bank = sum(
                scenario_probability[row.scenario_id] * int(row.end_bank_tenths)
                for row in surviving
                if row.end_bank_tenths is not None
            ) / survival_probability
            minimum_bank = min(
                int(row.end_bank_tenths)
                for row in surviving
                if row.end_bank_tenths is not None
            )
        else:
            expected_bank = None
            minimum_bank = None
        provisional.append(
            {
                "action_id": action,
                "expected_points": expected_points,
                "p10": _weighted_quantile(point_distribution, 0.10),
                "p50": _weighted_quantile(point_distribution, 0.50),
                "p90": _weighted_quantile(point_distribution, 0.90),
                "probability_optimal": probability_optimal,
                "priced_out_probability": priced_out_probability,
                "expected_bank": expected_bank,
                "minimum_bank": minimum_bank,
            }
        )

    best_expected_points = max(row["expected_points"] for row in provisional)
    selected_action = min(
        row["action_id"]
        for row in provisional
        if isclose(
            row["expected_points"],
            best_expected_points,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
    )
    summaries = tuple(
        TransferPolicyActionSummary(
            action_id=row["action_id"],
            expected_points=float(row["expected_points"]),
            p10_expected_points=float(row["p10"]),
            p50_expected_points=float(row["p50"]),
            p90_expected_points=float(row["p90"]),
            probability_optimal=float(row["probability_optimal"]),
            priced_out_probability=float(row["priced_out_probability"]),
            expected_end_bank_tenths_given_survival=(
                None if row["expected_bank"] is None else float(row["expected_bank"])
            ),
            minimum_end_bank_tenths_given_survival=row["minimum_bank"],
            expected_points_regret=float(best_expected_points - row["expected_points"]),
        )
        for row in sorted(provisional, key=lambda item: item["action_id"])
    )
    return TransferPolicySummary(selected_action, summaries)
