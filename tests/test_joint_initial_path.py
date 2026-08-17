from types import SimpleNamespace

import pandas as pd

import apex_fpl.services.joint_initial_path as joint
from apex_fpl.services.joint_initial_path import (
    JointPathCandidate,
    select_best_joint_candidate,
)


def candidate(
    future: float,
    ids: tuple[int, ...],
    *,
    gw1: float = 55.0,
    regret: float = 0.0,
    within: bool = True,
    bank: float = 0.0,
    source_rank: int = 1,
) -> JointPathCandidate:
    return JointPathCandidate(
        source_rank=source_rank,
        squad_ids=ids,
        squad_names=tuple(str(pid) for pid in ids),
        starting_cost=100.0 - bank,
        starting_bank=bank,
        gw1_expected_points=gw1,
        gw1_regret=regret,
        within_gw1_band=within,
        future_objective=future,
        total_hit_cost=0,
        weeks=tuple(),
    )


def test_future_path_cannot_override_the_gw1_floor() -> None:
    legal_launch = candidate(250.0, tuple(range(1, 16)), gw1=55.0, regret=0.0, within=True)
    frozen_horizon_star = candidate(
        999.0,
        tuple(range(2, 17)),
        gw1=54.6,
        regret=0.4,
        within=False,
    )
    selected = select_best_joint_candidate([frozen_horizon_star, legal_launch])
    assert selected == legal_launch


def test_future_option_value_breaks_ties_inside_the_gw1_band() -> None:
    better_future = candidate(260.0, tuple(range(1, 16)), gw1=54.80, regret=0.20, within=True)
    better_gw1 = candidate(250.0, tuple(range(2, 17)), gw1=55.0, regret=0.0, within=True)
    selected = select_best_joint_candidate([better_gw1, better_future])
    assert selected == better_future


def test_equal_future_value_prefers_more_gw1_points_then_bank() -> None:
    lower_gw1 = candidate(250.0, tuple(range(1, 16)), gw1=54.9, regret=0.1, within=True, bank=1.0)
    higher_gw1 = candidate(250.0, tuple(range(2, 17)), gw1=55.0, regret=0.0, within=True, bank=0.0)
    assert select_best_joint_candidate([lower_gw1, higher_gw1]) == higher_gw1

    same_gw1_more_bank = candidate(250.0, tuple(range(3, 18)), gw1=55.0, regret=0.0, within=True, bank=0.5)
    assert select_best_joint_candidate([higher_gw1, same_gw1_more_bank]) == same_gw1_more_bank


def test_expanded_launch_pool_converges_when_rank_18_improves_the_first_16(monkeypatch) -> None:
    """Regression for the live failure where a rank-18 launch beat rank <=16.

    The production selector should evaluate the expanded shortlist once, use the
    first 32 as its convergence prefix, and remain stable when ranks 33-64 do not
    displace the rank-18 winner. This preserves the GW1 floor while avoiding the old
    false failure caused by comparing only 16 candidates against 32.
    """
    first_16_winner = candidate(
        250.0,
        tuple(range(1, 16)),
        gw1=57.78,
        regret=0.0,
        source_rank=1,
    )
    rank_18_winner = candidate(
        260.0,
        tuple(range(2, 17)),
        gw1=57.73,
        regret=0.05,
        source_rank=18,
    )
    later_candidate = candidate(
        255.0,
        tuple(range(3, 18)),
        gw1=57.74,
        regret=0.04,
        source_rank=33,
    )
    evaluated = [first_16_winner, rank_18_winner, later_candidate]

    exact_calls: list[tuple[tuple[int, ...], int]] = []
    evaluation_calls = 0

    def fake_exact(players, projections, gameweeks, **kwargs):
        exact_calls.append((tuple(int(gw) for gw in gameweeks), int(kwargs["candidate_limit"])))
        if len(gameweeks) > 1:
            return SimpleNamespace(
                status="Optimal",
                objective=355.0,
                solution=SimpleNamespace(squad=pd.DataFrame({"player_id": range(1, 16)})),
            )
        return SimpleNamespace(
            status="Optimal",
            objective=57.78,
            shortlist_complete=False,
            candidates=tuple(),
        )

    def fake_evaluate(*args, **kwargs):
        nonlocal evaluation_calls
        evaluation_calls += 1
        return list(evaluated)

    def fake_baseline(*args, **kwargs):
        return first_16_winner

    monkeypatch.setattr(joint, "optimise_exact_horizon_decision", fake_exact)
    monkeypatch.setattr(joint, "_evaluate_exact_candidates", fake_evaluate)
    monkeypatch.setattr(joint, "_evaluate_starting_squad", fake_baseline)

    result = joint.optimise_joint_initial_path(
        pd.DataFrame({"player_id": range(1, 20)}),
        pd.DataFrame(),
        [1, 2],
        exact_candidate_limit=16,
        gw1_regret_tolerance=0.25,
    )

    assert exact_calls == [((1, 2), 16), ((1,), 64)]
    assert evaluation_calls == 1
    assert result.selected == rank_18_winner
    assert result.small_pool_selected_ids == rank_18_winner.squad_ids
    assert result.full_pool_selected_ids == rank_18_winner.squad_ids
    assert result.candidate_pool_stable is True
