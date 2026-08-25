from __future__ import annotations

from pathlib import Path

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.decision_policy_support import (
    load_candidate_policy,
    load_chip_option_value_policy,
    load_continuation_value_policy,
    load_price_policy,
)
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from apex_fpl.core.reference_solver_planning_io import (
    REFERENCE_SOLVER_PLANNING_CONTRACT,
    PlanningReferenceSolverRequest,
    PlanningReferenceSolverStatus,
)
from apex_fpl.workers.reference_solver_planning import solve_planning_reference_request

from production_planning_bundle_helpers import synthetic_production_planning_bundle


def _request(store, *, max_search_nodes: int) -> tuple[PlanningReferenceSolverRequest, object]:
    fixture = synthetic_production_planning_bundle(store=store)
    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)
    policy = verified.decision_policy
    assert policy.continuation_value_artifact_id is not None
    assert policy.chip_option_value_artifact_id is not None
    assert policy.price_policy_artifact_id is not None
    assert policy.candidate_policy_artifact_id is not None
    continuation = load_continuation_value_policy(
        policy.continuation_value_artifact_id,
        store=store,
    )
    chip_option = load_chip_option_value_policy(
        policy.chip_option_value_artifact_id,
        store=store,
    )
    price = load_price_policy(policy.price_policy_artifact_id, store=store)
    candidate = load_candidate_policy(policy.candidate_policy_artifact_id, store=store)
    request = PlanningReferenceSolverRequest.from_semantic_documents(
        decision_input=verified.decision.decision_input.semantic_payload(),
        manager_state=verified.manager_state.semantic_payload(),
        forecast=verified.forecast.semantic_payload(),
        candidate_universe=verified.candidate_universe.semantic_payload(),
        ruleset=verified.ruleset.semantic_payload(),
        decision_policy=policy.semantic_payload(),
        continuation_policy=continuation.semantic_payload(),
        chip_option_policy=chip_option.semantic_payload(),
        price_policy=price.semantic_payload(),
        candidate_policy=candidate.semantic_payload(),
        max_search_nodes=max_search_nodes,
    )
    return request, verified.decision


def test_planning_reference_contract_is_distinct_from_tactical_v1(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    request, _ = _request(store, max_search_nodes=5_000)
    assert request.solver_contract == REFERENCE_SOLVER_PLANNING_CONTRACT
    assert request.solver_contract != "apex-v2-exact-decision-parity-v1"
    assert request.horizon_gameweeks == 2


def test_independent_planning_worker_matches_complete_main_planner_trajectory(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    request, expected = _request(store, max_search_nodes=5_000)
    run = solve_planning_reference_request(request)

    assert run.solver_status is PlanningReferenceSolverStatus.OPTIMAL
    assert run.search_complete is True
    assert run.gap is not None and run.gap.numerator == 0
    assert run.best_objective is not None
    assert (
        run.best_objective.numerator,
        run.best_objective.denominator,
    ) == (
        expected.selection_objective.numerator,
        expected.selection_objective.denominator,
    )
    assert run.selected_action_id == expected.selected_action.action_id
    assert run.selected_trajectory_id == expected.selected_trajectory.trajectory_id
    assert run.selected_trajectory_json is not None


def test_planning_reference_worker_node_limit_never_claims_optimality(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    request, _ = _request(store, max_search_nodes=1)
    run = solve_planning_reference_request(request)

    assert run.solver_status is PlanningReferenceSolverStatus.SOLVER_LIMIT
    assert run.search_complete is False
    assert run.limit_reason is not None
    assert run.best_objective is not None
    assert run.best_bound is not None
    assert run.gap is not None and run.gap.numerator >= 0
    assert run.selected_action_id is not None
    assert run.selected_trajectory_id is not None
