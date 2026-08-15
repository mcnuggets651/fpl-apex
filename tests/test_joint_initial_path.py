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
) -> JointPathCandidate:
    return JointPathCandidate(
        source_rank=1,
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
