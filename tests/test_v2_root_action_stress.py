from __future__ import annotations

import pytest

from apex.decision.price_scenarios import PriceScenario
from apex.decision.price_transitions import DeterministicMarketPricePath, PriceStateError
from apex.decision.root_action_stress import stress_candidate_routes_by_root_action
from apex.decision.transfers import TransferCandidateRoute, TransferWeek
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
        for element_id in range(1, 25)
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


def _candidate_a(*, selected: bool = True) -> TransferCandidateRoute:
    return TransferCandidateRoute(
        generation_rank=1,
        approximate_objective=20.2,
        exact_objective=20.0,
        weeks=(
            TransferWeek(
                1,
                4,
                tuple(range(2, 17)),
                (16,),
                (1,),
                0,
                2,
                0,
                10.0,
            ),
            TransferWeek(
                2,
                5,
                tuple(range(3, 18)),
                (17,),
                (2,),
                0,
                1,
                0,
                10.0,
            ),
        ),
        baseline_selected=selected,
    )


def _candidate_b() -> TransferCandidateRoute:
    # Same H1/root action as candidate A, but a different H2 continuation.
    return TransferCandidateRoute(
        generation_rank=2,
        approximate_objective=19.4,
        exact_objective=19.0,
        weeks=(
            TransferWeek(
                1,
                4,
                tuple(range(2, 17)),
                (16,),
                (1,),
                0,
                2,
                0,
                10.0,
            ),
            TransferWeek(
                2,
                5,
                tuple(list(range(2, 16)) + [18]),
                (18,),
                (16,),
                0,
                1,
                0,
                9.0,
            ),
        ),
    )


def _candidate_c() -> TransferCandidateRoute:
    # Different current/root action: sell 2 for 19, then roll H2.
    return TransferCandidateRoute(
        generation_rank=3,
        approximate_objective=18.3,
        exact_objective=18.0,
        weeks=(
            TransferWeek(
                1,
                4,
                tuple(sorted((set(range(1, 16)) - {2}) | {19})),
                (19,),
                (2,),
                0,
                2,
                0,
                9.0,
            ),
            TransferWeek(
                2,
                5,
                tuple(sorted((set(range(1, 16)) - {2}) | {19})),
                (),
                (),
                0,
                1,
                0,
                9.0,
            ),
        ),
    )


def test_fixed_route_stress_groups_continuations_by_current_root_action() -> None:
    official, team = _fixture()
    scenarios = (
        PriceScenario("flat", 0.6, DeterministicMarketPricePath()),
        PriceScenario(
            "rise",
            0.4,
            DeterministicMarketPricePath.from_mapping({2: {16: 53, 17: 51}}),
        ),
    )

    matrix = stress_candidate_routes_by_root_action(
        official,
        team,
        (_candidate_a(), _candidate_b(), _candidate_c()),
        scenarios,
    )

    assert len(matrix.actions) == 2
    root = next(
        action
        for action in matrix.actions
        if action.action.transfers_in == (16,)
    )
    assert root.candidate_route_count == 2
    assert root.contains_baseline_selected_route is True

    flat, rise = root.scenario_results
    assert flat.scenario_id == "flat"
    assert flat.surviving_generation_ranks == (1, 2)
    assert flat.best_surviving_generation_rank == 1
    assert flat.best_surviving_exact_objective == pytest.approx(20.0)
    assert flat.best_surviving_end_bank_tenths == 0

    # A is priced out because target 17 rises. B survives because the H1 buy 16
    # was acquired at 50, rises to 53, and therefore sells for 51 to fund 18.
    assert rise.scenario_id == "rise"
    assert rise.surviving_generation_ranks == (2,)
    assert rise.best_surviving_generation_rank == 2
    assert rise.best_surviving_end_bank_tenths == 1
    assert rise.all_baseline_continuations_priced_out is False
    assert root.probability_any_baseline_continuation_survives == pytest.approx(1.0)
    assert root.probability_all_baseline_continuations_priced_out == pytest.approx(0.0)


def test_all_baseline_continuations_priced_out_does_not_claim_action_impossible() -> None:
    official, team = _fixture()
    scenario = PriceScenario(
        "targets-rise",
        1.0,
        DeterministicMarketPricePath.from_mapping({2: {17: 51, 18: 51}}),
    )

    matrix = stress_candidate_routes_by_root_action(
        official,
        team,
        (_candidate_a(), _candidate_b()),
        (scenario,),
    )

    root = matrix.actions[0]
    result = root.scenario_results[0]
    assert result.surviving_candidate_count == 0
    assert result.all_baseline_continuations_priced_out is True
    assert result.best_surviving_generation_rank is None
    assert root.probability_all_baseline_continuations_priced_out == pytest.approx(1.0)

    # This is deliberately diagnostic only. A changed-price scenario can unlock
    # a continuation that was infeasible and absent from the baseline shortlist.
    assert matrix.diagnostic_only is True
    assert matrix.can_select_serving_action is False
    assert matrix.requires_scenario_reoptimisation is True
    assert root.requires_scenario_reoptimisation is True
    assert not hasattr(matrix, "selected_action_id")


def test_fixed_route_stress_fails_closed_on_invalid_candidate_mechanics() -> None:
    official, team = _fixture()
    candidate = _candidate_a()
    invalid_week = TransferWeek(
        2,
        5,
        candidate.weeks[1].squad_ids,
        (17,),
        (24,),
        0,
        1,
        0,
        10.0,
    )
    invalid = TransferCandidateRoute(
        candidate.generation_rank,
        candidate.approximate_objective,
        candidate.exact_objective,
        (candidate.weeks[0], invalid_week),
        True,
    )

    with pytest.raises(PriceStateError, match="cannot sell unowned"):
        stress_candidate_routes_by_root_action(
            official,
            team,
            (invalid,),
            (PriceScenario("flat", 1.0),),
        )


def test_fixed_route_stress_requires_one_baseline_selected_candidate() -> None:
    official, team = _fixture()

    with pytest.raises(PriceStateError, match="exactly one baseline-selected"):
        stress_candidate_routes_by_root_action(
            official,
            team,
            (_candidate_a(selected=False), _candidate_b()),
            (PriceScenario("flat", 1.0),),
        )


def test_fixed_route_stress_requires_complete_scenario_probabilities() -> None:
    official, team = _fixture()

    with pytest.raises(PriceStateError, match="sum to 1"):
        stress_candidate_routes_by_root_action(
            official,
            team,
            (_candidate_a(),),
            (PriceScenario("partial", 0.8),),
        )
