from __future__ import annotations

from pathlib import Path

from apex_fpl.assurance.reference_solver_planning_exchange import (
    load_planning_reference_solver_request,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.decision_policy_support import (
    load_candidate_policy,
    load_chip_option_value_policy,
    load_continuation_value_policy,
    load_price_policy,
)
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from apex_fpl.control.reference_solver_planning_qualification import (
    load_planning_reference_solver_qualification_case,
)
from apex_fpl.decision.store import load_candidate_universe
from apex_fpl.core.decision import CandidateUniverseScope
from apex_fpl.core.reference_solver_planning_io import PlanningReferenceSolverStatus
from apex_fpl.workers.reference_solver_planning import solve_planning_reference_request

from production_planning_bundle_helpers import synthetic_production_planning_bundle
from reference_solver_planning_surface_case import store_full_surface_qualification_case


def test_full_surface_qualification_is_distinct_bounded_exact_world(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
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

    case_id = store_full_surface_qualification_case(
        store=store,
        verified=verified,
        continuation=continuation,
        chip_option=chip_option,
        price_policy=price,
        candidate_policy=candidate,
        max_search_nodes=500,
    )
    case = load_planning_reference_solver_qualification_case(case_id, store=store)
    request = load_planning_reference_solver_request(
        case.request_artifact_id,
        store=store,
    ).request
    universe = load_candidate_universe(
        case.candidate_universe_artifact_id,
        store=store,
    ).universe

    assert universe.scope is CandidateUniverseScope.FULL_OFFICIAL
    assert universe.official_player_count == 15
    assert len(universe.players) == 15
    assert universe.global_world_id != verified.candidate_universe.global_world_id
    assert request.candidate_universe["global_world_id"] == str(universe.global_world_id)
    assert request.max_search_nodes == 500

    run = solve_planning_reference_request(request)
    assert run.solver_status is PlanningReferenceSolverStatus.OPTIMAL
    assert run.search_complete is True
    assert run.gap is not None and run.gap.numerator == 0
    assert run.nodes_evaluated <= 500
