from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.assurance.replay_verification import verify_stored_independent_assurance
from apex_fpl.assurance.store import (
    load_independent_assurance_report,
    store_independent_assurance_report,
    store_reference_mechanics_certificate,
    store_reference_solver_certificate,
)
from apex_fpl.assurance.worker_authorization import (
    create_reference_solver_authorization,
    load_reference_solver_authorization,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.reference_solver_registry import ReferenceSolverRegistry
from apex_fpl.core.assurance import (
    AssuranceParityStatus,
    IndependentAssuranceReport,
    ReferenceCheckResult,
    ReferenceMechanicsCertificate,
    ReferenceMechanicsCheck,
    ReferenceSolverCertificate,
    ReferenceSolverStatus,
)
from apex_fpl.core.decision import DecisionMechanics, RationalValue
from apex_fpl.core.ids import (
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    DecisionPolicyId,
    ForecastId,
    ManagerStateId,
    RuleSetId,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)


def _mechanics() -> DecisionMechanics:
    return DecisionMechanics(
        xi_points=RationalValue(50, 1),
        autosub_points=RationalValue(2, 1),
        captain_bonus=RationalValue(5, 1),
        squad_points_if_bench_boost=RationalValue(60, 1),
        points_before_hits=RationalValue(57, 1),
        hit_points=0,
        objective_points=RationalValue(57, 1),
    )


def _mechanics_certificate(source: str) -> ReferenceMechanicsCertificate:
    return ReferenceMechanicsCertificate(
        decision_id=DecisionId("authorization-decision"),
        decision_input_id=DecisionInputId("authorization-input"),
        manager_state_id=ManagerStateId("authorization-manager"),
        forecast_id=ForecastId("authorization-forecast"),
        ruleset_id=RuleSetId("authorization-rules"),
        candidate_universe_id=CandidateUniverseId("authorization-universe"),
        action_id="authorization-action",
        recomputed_bank_after_tenths=0,
        recomputed_hit_points=0,
        recomputed_mechanics=_mechanics(),
        checks=tuple(
            ReferenceCheckResult(check, True, f"{check.value} reconciled")
            for check in ReferenceMechanicsCheck
        ),
        algorithm_id="reference-mechanics-exhaustive-appearance-v1",
        source_artifact_ids=(source,),
    )


def _solver_certificate(store: FileSystemArtifactStore) -> ReferenceSolverCertificate:
    worker_code = store.put_bytes(b"authorization-worker-code").artifact_id
    solver_input = store.put_bytes(b"authorization-solver-input").artifact_id
    solver_output = store.put_bytes(b"authorization-solver-output").artifact_id
    return ReferenceSolverCertificate(
        decision_input_id=DecisionInputId("authorization-input"),
        candidate_universe_id=CandidateUniverseId("authorization-universe"),
        decision_policy_id=DecisionPolicyId("authorization-policy"),
        worker_name="authorization-worker",
        worker_version="1",
        solver_status=ReferenceSolverStatus.OPTIMAL,
        best_objective=RationalValue(57, 1),
        best_bound=RationalValue(57, 1),
        gap=RationalValue.zero(),
        selected_action_id="authorization-action",
        action_surface_complete=True,
        tie_break_policy_id="lexicographic-official-id-v1",
        solver_input_artifact_id=solver_input,
        solver_output_artifact_id=solver_output,
        worker_artifact_id=worker_code,
    )


def _qualified_registry(
    store: FileSystemArtifactStore,
    solver: ReferenceSolverCertificate,
) -> ReferenceSolverRegistry:
    qualification = store.put_bytes(b"authorization-worker-qualification").artifact_id
    worker = ReferenceSolverWorkerArtifact(
        worker_name=solver.worker_name,
        worker_version=solver.worker_version,
        solver_contract="apex-v2-exact-decision-parity-v1",
        code_artifact_id=solver.worker_artifact_id,
        qualification_state=ReferenceSolverWorkerQualification.QUALIFIED,
        qualification_artifact_id=qualification,
        valid_seasons=("2026-2027",),
        first_available_at="2026-08-24T00:00:00Z",
        max_horizon_gameweeks=1,
    )
    return ReferenceSolverRegistry(
        season="2026-2027",
        workers=(worker,),
        champion_worker_id=worker.worker_id,
    )


def _stored_pass(store: FileSystemArtifactStore):
    source = store.put_bytes(b"authorization-mechanics-source").artifact_id
    mechanics = _mechanics_certificate(source)
    solver = _solver_certificate(store)
    registry = _qualified_registry(store, solver)
    authorization = create_reference_solver_authorization(
        solver,
        worker_registry=registry,
        registry_artifact_id=None,
        store=store,
        season="2026-2027",
        decision_cutoff="2026-08-24T06:00:00Z",
        horizon_gameweeks=1,
    )
    stored_mechanics = store_reference_mechanics_certificate(mechanics, store=store)
    stored_solver = store_reference_solver_certificate(solver, store=store)
    report = IndependentAssuranceReport(
        decision_id=mechanics.decision_id,
        mechanics_certificate_id=mechanics.certificate_id,
        mechanics_passed=True,
        solver_certificate_id=solver.certificate_id,
        solver_parity_status=AssuranceParityStatus.PASS,
        blockers=(),
        source_artifact_ids=tuple(
            sorted(
                {
                    *mechanics.source_artifact_ids,
                    solver.solver_input_artifact_id,
                    solver.solver_output_artifact_id,
                    solver.worker_artifact_id,
                    authorization.artifact_id,
                    authorization.authorization.registry_artifact_id,
                    authorization.authorization.worker_code_artifact_id,
                    authorization.authorization.qualification_artifact_id,
                }
            )
        ),
    )
    stored_report = store_independent_assurance_report(
        report,
        mechanics=stored_mechanics,
        solver=stored_solver,
        store=store,
    )
    return stored_report, authorization, solver


def test_publication_pass_replays_qualified_champion_authorization(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    stored_report, authorization, _ = _stored_pass(store)
    replayed = load_independent_assurance_report(stored_report.artifact_id, store=store)
    verified = verify_stored_independent_assurance(replayed, store=store)
    assert verified.stored_report.report.publication_eligible is True
    assert verified.solver_authorization is not None
    assert verified.solver_authorization.artifact_id == authorization.artifact_id


def test_pass_looking_report_without_authorization_is_rejected_on_verified_replay(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    source = store.put_bytes(b"missing-authorization-source").artifact_id
    mechanics = _mechanics_certificate(source)
    solver = _solver_certificate(store)
    stored_mechanics = store_reference_mechanics_certificate(mechanics, store=store)
    stored_solver = store_reference_solver_certificate(solver, store=store)
    report = IndependentAssuranceReport(
        decision_id=mechanics.decision_id,
        mechanics_certificate_id=mechanics.certificate_id,
        mechanics_passed=True,
        solver_certificate_id=solver.certificate_id,
        solver_parity_status=AssuranceParityStatus.PASS,
        blockers=(),
        source_artifact_ids=tuple(
            sorted(
                {
                    source,
                    solver.solver_input_artifact_id,
                    solver.solver_output_artifact_id,
                    solver.worker_artifact_id,
                }
            )
        ),
    )
    stored_report = store_independent_assurance_report(
        report,
        mechanics=stored_mechanics,
        solver=stored_solver,
        store=store,
    )
    replayed = load_independent_assurance_report(stored_report.artifact_id, store=store)
    with pytest.raises(ValueError, match="lacks replayable qualified solver authorization"):
        verify_stored_independent_assurance(replayed, store=store)


def test_authorization_replay_fails_if_qualification_artifact_is_missing(tmp_path: Path) -> None:
    source_store = FileSystemArtifactStore(tmp_path / "source")
    _, authorization, solver = _stored_pass(source_store)
    replay_store = FileSystemArtifactStore(tmp_path / "replay")
    for artifact_id in (
        authorization.artifact_id,
        authorization.authorization.registry_artifact_id,
        authorization.authorization.worker_code_artifact_id,
    ):
        replayed_id = replay_store.put_bytes(source_store.read_bytes(artifact_id)).artifact_id
        assert replayed_id == artifact_id
    with pytest.raises((FileNotFoundError, ValueError)):
        load_reference_solver_authorization(
            authorization.artifact_id,
            certificate=solver,
            store=replay_store,
        )
