from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite

from apex.domain.models import OfficialSnapshot

from .price_scenarios import PriceScenario
from .price_transitions import PriceStateError


@dataclass(frozen=True)
class PriceInformationNode:
    """One price-information state at a transfer decision horizon.

    `probability` is unconditional probability mass. `market_prices_tenths`
    contains only prices observable at this node; future scenario states are not
    embedded in the node. Distinct past price histories remain distinct nodes
    even if their current market-price vectors later reconverge.
    """

    node_id: str
    horizon: int
    probability: float
    parent_id: str | None
    scenario_ids: tuple[str, ...]
    market_prices_tenths: tuple[tuple[int, int], ...]

    def market_price_map(self) -> dict[int, int]:
        return dict(self.market_prices_tenths)


@dataclass(frozen=True)
class PriceInformationTree:
    root_id: str
    max_horizon: int
    relevant_element_ids: tuple[int, ...]
    nodes: tuple[PriceInformationNode, ...]
    scenario_leaf_node_ids: tuple[tuple[str, str], ...]
    non_anticipative_by_construction: bool = True

    def node_map(self) -> dict[str, PriceInformationNode]:
        return {node.node_id: node for node in self.nodes}

    def nodes_for_horizon(self, horizon: int) -> tuple[PriceInformationNode, ...]:
        return tuple(node for node in self.nodes if node.horizon == int(horizon))

    def children_of(self, node_id: str) -> tuple[PriceInformationNode, ...]:
        return tuple(node for node in self.nodes if node.parent_id == node_id)


def build_price_information_tree(
    official: OfficialSnapshot,
    scenarios: tuple[PriceScenario, ...],
    *,
    max_horizon: int,
    relevant_element_ids: tuple[int, ...] | None = None,
) -> PriceInformationTree:
    """Collapse full price paths into a no-hindsight decision information tree.

    Horizon 1 is the current action and therefore uses the already-known Official
    market prices. This first serving successor deliberately does not treat an
    unknown pre-execution H1 price as if it were observable; same-GW execution
    timing / wait-vs-act uncertainty belongs to the later timing-regret layer.

    For H2+, scenarios that share the same complete observed price history share
    one node and therefore one future decision state. Once histories diverge they
    never merge again merely because current prices reconverge. A stochastic MILP
    can index decisions by these nodes and obtain non-anticipativity without
    pairwise equality constraints between full-path scenarios.
    """
    if isinstance(max_horizon, bool) or not isinstance(max_horizon, int):
        raise PriceStateError("max_horizon must be an integer")
    if max_horizon < 1:
        raise PriceStateError("max_horizon must be positive")
    if not scenarios:
        raise PriceStateError("price information tree requires price scenarios")

    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise PriceStateError("price scenario IDs must be unique")
    probabilities = [float(scenario.probability) for scenario in scenarios]
    if any(
        not isfinite(probability) or not 0.0 < probability <= 1.0
        for probability in probabilities
    ):
        raise PriceStateError(
            "price information tree requires finite positive scenario probabilities"
        )
    if not isclose(sum(probabilities), 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise PriceStateError("price scenario probabilities must sum to 1")

    current_prices = {
        int(player.element_id): int(player.price_tenths)
        for player in official.players
    }
    if not current_prices:
        raise PriceStateError("Official snapshot has no players")

    if relevant_element_ids is None:
        relevant = tuple(sorted(current_prices))
    else:
        relevant = tuple(sorted(map(int, relevant_element_ids)))
        if not relevant or len(relevant) != len(set(relevant)):
            raise PriceStateError(
                "relevant price-tree element IDs must be non-empty and unique"
            )
        unknown = sorted(set(relevant) - set(current_prices))
        if unknown:
            raise PriceStateError(
                f"price-tree elements missing from Official snapshot: {unknown}"
            )

    official_ids = set(current_prices)
    for scenario in scenarios:
        for horizon, pairs in scenario.path.overrides:
            if int(horizon) == 1:
                raise PriceStateError(
                    "H1 price uncertainty is not observable at the current root action; "
                    "model execution timing separately"
                )
            unknown = sorted(
                int(element_id)
                for element_id, _ in pairs
                if int(element_id) not in official_ids
            )
            if unknown:
                raise PriceStateError(
                    f"price scenario {scenario.scenario_id} references unknown elements: "
                    f"{unknown}"
                )

    scenarios_by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    probability_by_id = {
        scenario.scenario_id: float(scenario.probability) for scenario in scenarios
    }
    ordered_ids = tuple(sorted(scenarios_by_id))
    root_prices = tuple((element_id, current_prices[element_id]) for element_id in relevant)
    root = PriceInformationNode(
        node_id="H1_ROOT",
        horizon=1,
        probability=1.0,
        parent_id=None,
        scenario_ids=ordered_ids,
        market_prices_tenths=root_prices,
    )
    nodes: list[PriceInformationNode] = [root]

    # Histories contain only observations available through the current horizon.
    # The root history is intentionally empty because H1 prices are already known
    # and identical for every scenario.
    history_by_scenario: dict[str, tuple] = {scenario_id: () for scenario_id in ordered_ids}
    node_for_history: dict[tuple, str] = {(): root.node_id}

    for horizon in range(2, max_horizon + 1):
        grouped: dict[tuple, list[str]] = {}
        current_vector_by_history: dict[tuple, tuple[tuple[int, int], ...]] = {}
        parent_history_by_history: dict[tuple, tuple] = {}

        for scenario_id in ordered_ids:
            scenario = scenarios_by_id[scenario_id]
            materialised = scenario.path.materialise_horizon(horizon, current_prices)
            vector = tuple((element_id, int(materialised[element_id])) for element_id in relevant)
            parent_history = history_by_scenario[scenario_id]
            history = parent_history + ((horizon, vector),)
            grouped.setdefault(history, []).append(scenario_id)
            current_vector_by_history[history] = vector
            parent_history_by_history[history] = parent_history
            history_by_scenario[scenario_id] = history

        next_node_for_history: dict[tuple, str] = {}
        for index, history in enumerate(sorted(grouped), start=1):
            scenario_group = tuple(sorted(grouped[history]))
            parent_history = parent_history_by_history[history]
            try:
                parent_id = node_for_history[parent_history]
            except KeyError as exc:
                raise PriceStateError(
                    "price information tree lost a parent history"
                ) from exc
            probability = sum(probability_by_id[scenario_id] for scenario_id in scenario_group)
            node_id = f"H{horizon}_N{index}"
            node = PriceInformationNode(
                node_id=node_id,
                horizon=horizon,
                probability=float(probability),
                parent_id=parent_id,
                scenario_ids=scenario_group,
                market_prices_tenths=current_vector_by_history[history],
            )
            nodes.append(node)
            next_node_for_history[history] = node_id
        node_for_history = next_node_for_history

    node_map = {node.node_id: node for node in nodes}
    for horizon in range(2, max_horizon + 1):
        for parent in (node for node in nodes if node.horizon == horizon - 1):
            children = [node for node in nodes if node.parent_id == parent.node_id]
            if not children:
                raise PriceStateError(
                    f"price information node {parent.node_id} has no children"
                )
            child_probability = sum(child.probability for child in children)
            if not isclose(
                child_probability,
                parent.probability,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise PriceStateError(
                    f"child probability mass disagrees for {parent.node_id}"
                )
            child_scenarios = sorted(
                scenario_id
                for child in children
                for scenario_id in child.scenario_ids
            )
            if child_scenarios != sorted(parent.scenario_ids):
                raise PriceStateError(
                    f"child scenario partition disagrees for {parent.node_id}"
                )

    leaf_pairs: list[tuple[str, str]] = []
    if max_horizon == 1:
        leaf_pairs = [(scenario_id, root.node_id) for scenario_id in ordered_ids]
    else:
        for scenario_id in ordered_ids:
            leaf_id = node_for_history[history_by_scenario[scenario_id]]
            if node_map[leaf_id].horizon != max_horizon:
                raise PriceStateError("price information tree leaf horizon mismatch")
            leaf_pairs.append((scenario_id, leaf_id))

    return PriceInformationTree(
        root_id=root.node_id,
        max_horizon=max_horizon,
        relevant_element_ids=relevant,
        nodes=tuple(nodes),
        scenario_leaf_node_ids=tuple(leaf_pairs),
    )
