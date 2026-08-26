from __future__ import annotations

from pathlib import Path

from apex_fpl.assurance.reference_solver_planning_exchange import (
    load_planning_reference_solver_certificate,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.production_planning_bundle import load_production_planning_bundle
from apex_fpl.control.reference_solver_planning_qualification import (
    load_planning_reference_solver_qualification_corpus,
    verify_planning_reference_solver_algorithmic_qualification,
)
from apex_fpl.core.reference_solver_planning_io import REFERENCE_SOLVER_PLANNING_CONTRACT
from apex_fpl.core.reference_solver_planning_qualification import (
    PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)

from production_planning_bundle_helpers import synthetic_production_planning_bundle
from reference_solver_planning_helpers import synthetic_planning_parity_material


SEASON = "2026-2027"


def test_planning_qualification_replays_focused_chip_and_finance_cases(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    fixture = synthetic_production_planning_bundle(store=store, season=SEASON)
    verified = load_production_planning_bundle(fixture.bundle.bundle_id, store=store)
    material = synthetic_planning_parity_material(store=store, fixture=fixture)

    assert material.corpus_artifact_id is not None
    assert material.worker_code_artifact_id is not None
    corpus = load_planning_reference_solver_qualification_corpus(
        material.corpus_artifact_id,
        store=store,
    )
    # Qualification must combine independent retained cases rather than overloading one
    # combinatorial world: publication/chip semantics plus focused banking/finance semantics.
    assert len(corpus.case_artifact_ids) == 2
    assert len(set(corpus.case_artifact_ids)) == 2

    qualified_worker = ReferenceSolverWorkerArtifact(
        worker_name="synthetic-planning-reference-worker",
        worker_version="2",
        solver_contract=REFERENCE_SOLVER_PLANNING_CONTRACT,
        code_artifact_id=material.worker_code_artifact_id,
        qualification_state=ReferenceSolverWorkerQualification.QUALIFIED,
        qualification_artifact_id=material.qualification_artifact_id,
        valid_seasons=(SEASON,),
        first_available_at="2026-08-01T00:00:00Z",
        max_horizon_gameweeks=2,
    )
    replayed = verify_planning_reference_solver_algorithmic_qualification(
        qualified_worker,
        qualification_artifact_id=material.qualification_artifact_id,
        store=store,
        season=SEASON,
        horizon_gameweeks=2,
    )
    assert replayed.passed_case_count == 2
    assert set(replayed.coverage_tags) == set(PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE)

    loaded_certificate = load_planning_reference_solver_certificate(
        material.certificate_artifact_id,
        store=store,
    ).certificate
    assert loaded_certificate.selected_action_id == verified.decision.selected_action.action_id
    assert (
        loaded_certificate.selected_trajectory_id
        == verified.decision.selected_trajectory.trajectory_id
    )
    assert loaded_certificate.search_complete is True
    assert loaded_certificate.gap is not None and loaded_certificate.gap.numerator == 0
