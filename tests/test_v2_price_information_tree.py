from __future__ import annotations

import pytest

from apex.decision.price_information_tree import build_price_information_tree
from apex.decision.price_scenarios import PriceScenario
from apex.decision.price_transitions import DeterministicMarketPricePath, PriceStateError
from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position


def _official() -> OfficialSnapshot:
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
        for element_id in range(1, 5)
    )
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-09-05T08:00:00Z",
        "official",
        players,
        (),
        {
            4: "2026-09-12T10:00:00Z",
            5: "2026-09-19T10:00:00Z",
            6: "2026-09-26T10:00:00Z",
        },
    )


def test_scenarios_share_decision_node_until_observed_price_histories_diverge() -> None:
    scenarios = (
        PriceScenario(
            "a",
            0.6,
            DeterministicMarketPricePath.from_mapping(
                {2: {1: 51}, 3: {1: 52}}
            ),
        ),
        PriceScenario(
            "b",
            0.4,
            DeterministicMarketPricePath.from_mapping(
                {2: {1: 51}, 3: {1: 50}}
            ),
        ),
    )

    tree = build_price_information_tree(
        _official(),
        scenarios,
        max_horizon=3,
        relevant_element_ids=(1, 2),
    )

    assert tree.non_anticipative_by_construction is True
    assert tree.root_id == "H1_ROOT"
    assert len(tree.nodes_for_horizon(1)) == 1

    h2 = tree.nodes_for_horizon(2)
    assert len(h2) == 1
    assert h2[0].scenario_ids == ("a", "b")
    assert h2[0].probability == pytest.approx(1.0)
    assert h2[0].market_price_map() == {1: 51, 2: 50}

    h3 = tree.nodes_for_horizon(3)
    assert len(h3) == 2
    assert {node.scenario_ids for node in h3} == {("a",), ("b",)}
    assert {node.parent_id for node in h3} == {h2[0].node_id}
    assert sorted(node.probability for node in h3) == pytest.approx([0.4, 0.6])


def test_reconverged_current_prices_do_not_erase_different_observed_histories() -> None:
    scenarios = (
        PriceScenario(
            "rise-then-flat",
            0.5,
            DeterministicMarketPricePath.from_mapping(
                {2: {1: 51}, 3: {1: 50}}
            ),
        ),
        PriceScenario(
            "fall-then-flat",
            0.5,
            DeterministicMarketPricePath.from_mapping(
                {2: {1: 49}, 3: {1: 50}}
            ),
        ),
    )

    tree = build_price_information_tree(
        _official(),
        scenarios,
        max_horizon=3,
        relevant_element_ids=(1,),
    )

    h2 = tree.nodes_for_horizon(2)
    h3 = tree.nodes_for_horizon(3)
    assert len(h2) == 2
    assert len(h3) == 2
    assert {tuple(node.market_price_map().values()) for node in h3} == {(50,)}
    assert len({node.parent_id for node in h3}) == 2


def test_tree_probability_mass_and_child_partitions_are_exact() -> None:
    scenarios = (
        PriceScenario("flat", 0.5),
        PriceScenario(
            "rise",
            0.3,
            DeterministicMarketPricePath.from_mapping({2: {1: 51}}),
        ),
        PriceScenario(
            "fall",
            0.2,
            DeterministicMarketPricePath.from_mapping({2: {1: 49}}),
        ),
    )
    tree = build_price_information_tree(
        _official(),
        scenarios,
        max_horizon=3,
        relevant_element_ids=(1,),
    )

    for horizon in range(1, 4):
        assert sum(node.probability for node in tree.nodes_for_horizon(horizon)) == pytest.approx(
            1.0
        )
    for parent in tree.nodes_for_horizon(1) + tree.nodes_for_horizon(2):
        children = tree.children_of(parent.node_id)
        assert sum(child.probability for child in children) == pytest.approx(
            parent.probability
        )
        assert sorted(
            scenario_id for child in children for scenario_id in child.scenario_ids
        ) == sorted(parent.scenario_ids)


def test_tree_is_deterministic_under_scenario_input_order() -> None:
    scenarios = (
        PriceScenario(
            "z",
            0.4,
            DeterministicMarketPricePath.from_mapping({2: {1: 51}}),
        ),
        PriceScenario("a", 0.6),
    )

    forward = build_price_information_tree(
        _official(),
        scenarios,
        max_horizon=3,
        relevant_element_ids=(1, 2),
    )
    reversed_tree = build_price_information_tree(
        _official(),
        tuple(reversed(scenarios)),
        max_horizon=3,
        relevant_element_ids=(1, 2),
    )

    assert forward == reversed_tree


def test_h1_price_override_is_rejected_as_execution_timing_uncertainty() -> None:
    scenario = PriceScenario(
        "unknown-root-price",
        1.0,
        DeterministicMarketPricePath.from_mapping({1: {1: 51}}),
    )

    with pytest.raises(PriceStateError, match="H1 price uncertainty"):
        build_price_information_tree(
            _official(),
            (scenario,),
            max_horizon=2,
            relevant_element_ids=(1,),
        )


def test_unknown_official_element_in_scenario_fails_closed() -> None:
    scenario = PriceScenario(
        "bad-element",
        1.0,
        DeterministicMarketPricePath.from_mapping({2: {99: 51}}),
    )

    with pytest.raises(PriceStateError, match="unknown elements"):
        build_price_information_tree(
            _official(),
            (scenario,),
            max_horizon=2,
            relevant_element_ids=(1,),
        )


def test_zero_probability_scenario_is_not_a_decision_tree_branch() -> None:
    scenarios = (
        PriceScenario("live", 1.0),
        PriceScenario("zero", 0.0),
    )

    with pytest.raises(PriceStateError, match="positive scenario probabilities"):
        build_price_information_tree(
            _official(),
            scenarios,
            max_horizon=2,
            relevant_element_ids=(1,),
        )


def test_one_horizon_tree_maps_every_scenario_to_known_root() -> None:
    scenarios = (
        PriceScenario("a", 0.7),
        PriceScenario("b", 0.3),
    )
    tree = build_price_information_tree(
        _official(),
        scenarios,
        max_horizon=1,
        relevant_element_ids=(1,),
    )

    assert tree.nodes == (tree.node_map()[tree.root_id],)
    assert tree.scenario_leaf_node_ids == (
        ("a", "H1_ROOT"),
        ("b", "H1_ROOT"),
    )
