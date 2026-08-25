from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from apex_fpl.assurance.reference_solver_planning_exchange import (
    build_planning_reference_solver_certificate,
    build_planning_reference_solver_request,
    load_planning_reference_solver_certificate,
    store_planning_reference_solver_certificate,
    store_planning_reference_solver_request,
    store_planning_reference_solver_run,
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
    derive_planning_reference_solver_algorithmic_qualification,
    store_planning_reference_solver_algorithmic_qualification,
    store_planning_reference_solver_qualification_case,
    store_planning_reference_solver_qualification_corpus,
    verify_planning_reference_solver_algorithmic_qualification,
)
from apex_fpl.core.reference_solver_planning_io import REFERENCE_SOLVER_PLANNING_CONTRACT
from apex_fpl.core.reference_solver_planning_qualification import (
    PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE,
    PlanningReferenceSolverQualificationCase,
    PlanningReferenceSolverQualificationCorpus,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)
from apex_fpl.decision.planning_store import load_planning_state
from apex_fpl.workers.reference_solver_planning import solve_planning_reference_request

from production_planning_bundle_helpers import synthetic_production_planning_bundle


SEASON = "2026-2027"


def test_planning_qualification_replays_executed_finance_banking_and_reserve(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_planning_bundle(store=store, season=SEASON)
    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)
    result = verified.decision
    trajectory = result.selected_trajectory

    assert len(trajectory.steps) == 2
    first, second = trajectory.steps
    assert first.action.transfers == ()
    assert first.action.chip.value not in {"WILDCARD", "FREE_HIT"}
    banked_state = load_planning_state(first.state_after_id, store=store)
    assert banked_state.free_transfers == 2
    assert len(second.action.transfers) == 1
    transfer = second.action.transfers[0]
    assert int(transfer.incoming_player_id) == 16
    assert second.action.bank_after_tenths == 0
    assert second.action.mechanics.hit_points == 0
    assert trajectory.terminal_chip_reserve.numerator > 0

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
    request = build_planning_reference_solver_request(
        result=result,
        manager_state=verified.manager_state,
        forecast=verified.forecast,
        candidate_universe=verified.candidate_universe,
        ruleset=verified.ruleset,
        decision_policy=policy,
        continuation_policy=continuation,
        chip_option_policy=chip_option,
        price_policy=price,
        candidate_policy=candidate,
        max_search_nodes=5_000,
    )
    stored_request = store_planning_reference_solver_request(request, store=store)
    case = PlanningReferenceSolverQualificationCase(
        request_artifact_id=stored_request.artifact_id,
        expected_planning_result_artifact_id=fixture.bundle.planning_result_artifact_id,
        candidate_universe_artifact_id=fixture.bundle.candidate_universe_artifact_id,
    )
    case_artifact = store_planning_reference_solver_qualification_case(case, store=store)
    corpus = PlanningReferenceSolverQualificationCorpus(
        season=SEASON,
        max_horizon_gameweeks=2,
        case_artifact_ids=(case_artifact,),
    )
    corpus_artifact = store_planning_reference_solver_qualification_corpus(
        corpus,
        store=store,
    )

    worker_code = store.put_bytes(b"synthetic planning reference worker v2").artifact_id
    shadow_worker = ReferenceSolverWorkerArtifact(
        worker_name="synthetic-planning-reference-worker",
        worker_version="2",
        solver_contract=REFERENCE_SOLVER_PLANNING_CONTRACT,
        code_artifact_id=worker_code,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
        valid_seasons=(SEASON,),
        first_available_at="2026-08-01T00:00:00Z",
        max_horizon_gameweeks=2,
    )
    qualification = derive_planning_reference_solver_algorithmic_qualification(
        shadow_worker,
        corpus_artifact_id=corpus_artifact,
        store=store,
    )
    assert set(qualification.coverage_tags) == set(
        PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE
    )
    qualification_artifact = store_planning_reference_solver_algorithmic_qualification(
        qualification,
        store=store,
    )
    qualified_worker = replace(
        shadow_worker,
        qualification_state=ReferenceSolverWorkerQualification.QUALIFIED,
        qualification_artifact_id=qualification_artifact,
    )
    replayed = verify_planning_reference_solver_algorithmic_qualification(
        qualified_worker,
        qualification_artifact_id=qualification_artifact,
        store=store,
        season=SEASON,
        horizon_gameweeks=2,
    )
    assert replayed.semantic_payload() == qualification.semantic_payload()

    run = solve_planning_reference_request(request)
    stored_run = store_planning_reference_solver_run(run, store=store)
    certificate = build_planning_reference_solver_certificate(
        request_artifact_id=stored_request.artifact_id,
        run_artifact_id=stored_run.artifact_id,
        worker_name=qualified_worker.worker_name,
        worker_version=qualified_worker.worker_version,
        worker_code_artifact_id=qualified_worker.code_artifact_id,
        store=store,
    )
    stored_certificate = store_planning_reference_solver_certificate(
        certificate,
        store=store,
    )
    loaded_certificate = load_planning_reference_solver_certificate(
        stored_certificate.artifact_id,
        store=store,
    )
    assert loaded_certificate.certificate.semantic_payload() == certificate.semantic_payload()
    assert certificate.selected_action_id == result.selected_action.action_id
    assert certificate.selected_trajectory_id == result.selected_trajectory.trajectory_id
