from apex_fpl.services.joint_initial_path import (
    JointPathCandidate,
    select_best_joint_candidate,
)


def candidate(objective: float, ids: tuple[int, ...], hits: int = 0) -> JointPathCandidate:
    return JointPathCandidate(
        source_horizon=8,
        source_rank=1,
        squad_ids=ids,
        squad_names=tuple(str(pid) for pid in ids),
        starting_cost=100.0,
        starting_bank=0.0,
        gw1_expected_points=50.0,
        future_objective=objective - 50.0,
        total_objective=objective,
        total_hit_cost=hits,
        weeks=tuple(),
    )


def test_select_best_joint_candidate_uses_total_path_objective() -> None:
    lower_static_but_better_path = candidate(341.2, tuple(range(1, 16)))
    higher_static_but_worse_path = candidate(340.8, tuple(range(2, 17)))
    selected = select_best_joint_candidate(
        [higher_static_but_worse_path, lower_static_but_better_path]
    )
    assert selected == lower_static_but_better_path


def test_select_best_joint_candidate_has_deterministic_tiebreak() -> None:
    left = candidate(341.0, tuple(range(1, 16)))
    right = candidate(341.0, tuple(range(2, 17)))
    assert select_best_joint_candidate([right, left]) == left


def test_joint_candidate_preserves_reported_hit_cost() -> None:
    row = candidate(337.0, tuple(range(1, 16)), hits=4)
    payload = row.to_dict()
    assert payload["total_hit_cost"] == 4
    assert payload["total_objective"] == 337.0
