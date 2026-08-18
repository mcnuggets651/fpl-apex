from apex_fpl.services.joint_initial_path import JointInitialPathResult
from scripts.apply_joint_path_promotion_rebased import reconcile_finalized_stability


def result(*, small, full, stable=False):
    return JointInitialPathResult(
        status="optimal",
        baseline=None,
        selected=None,
        candidates=tuple(),
        best_gw1_points=60.0,
        gw1_regret_tolerance=0.25,
        gw1_floor=59.75,
        small_pool_selected_ids=small,
        full_pool_selected_ids=full,
        candidate_pool_stable=stable,
        squad_overlap=None,
        gw1_delta_vs_static=None,
        future_delta_vs_static=None,
        projection_col="xp",
        note="test",
    )


def test_identical_finalized_prefix_squads_are_stable():
    ids = tuple(range(1, 16))
    out = reconcile_finalized_stability(result(small=ids, full=ids))
    assert out.small_pool_selected_ids == out.full_pool_selected_ids
    assert out.candidate_pool_stable is True


def test_different_finalized_prefix_squads_remain_unstable():
    small = tuple(range(1, 16))
    full = tuple(range(2, 17))
    out = reconcile_finalized_stability(result(small=small, full=full))
    assert out.candidate_pool_stable is False
