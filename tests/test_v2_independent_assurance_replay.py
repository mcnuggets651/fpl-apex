from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.assurance.store import (
    load_independent_assurance_report,
    load_reference_mechanics_certificate,
    store_independent_assurance_report,
    store_reference_mechanics_certificate,
    store_reference_solver_certificate,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.core.assurance import (
    AssuranceParityStatus,
    IndependentAssuranceReport,
    ReferenceCheckResult,
    ReferenceMechanicsCertificate,
    ReferenceMechanicsCheck,
    ReferenceSolverCertificate,
    ReferenceSolverStatus,
)
from apex_fpl.core.canonical import canonical_json_bytes
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
        decision_id=DecisionId("assurance-decision"),
        decision_input_id=DecisionInputId("assurance-input"),
        manager_state_id=ManagerStateId("assurance-manager"),
        forecast_id=ForecastId("assurance-forecast"),
        ruleset_id=RuleSetId("assurance-rules"),
        candidate_universe_id=CandidateUniverseId("assurance-universe"),
        action_id="assurance-action",
        recomputed_bank_after_tenths=1,
        recomputed_hit_points=0,
        recomputed_mechanics=_mechanics(),
        checks=tuple(
            ReferenceCheckResult(check, True, f"{check.value} independently reconciled")
            for check in ReferenceMechanicsCheck
        ),
        algorithm_id="reference-mechanics-exhaustive-appearance-v1",
        source_artifact_ids=(source,),
    )


def _solver_certificate(store: FileSystemArtifactStore) -> ReferenceSolverCertificate:
    solver_input = store.put_bytes(b"sealed-reference-solver-input").artifact_id
    solver_output = store.put_bytes(b"sealed-reference-solver-output").artifact_id
    worker = store.put_bytes(b"pinned-reference-solver-worker").artifact_id
    return ReferenceSolverCertificate(
        decision_input_id=DecisionInputId("assurance-input"),
        candidate_universe_id=CandidateUniverseId("assurance-universe"),
        decision_policy_id=DecisionPolicyId("assurance-policy"),
        worker_name="reference-worker",
        worker_version="1",
        solver_status=ReferenceSolverStatus.OPTIMAL,
        best_objective=RationalValue(57, 1),
        best_bound=RationalValue(57, 1),
        gap=RationalValue.zero(),
        selected_action_id="assurance-action",
        action_surface_complete=True,
        tie_break_policy_id="lexicographic-official-id-v1",
        solver_input_artifact_id=solver_input,
        solver_output_artifact_id=solver_output,
        worker_artifact_id=worker,
    )


def test_assurance_certificates_and_report_replay_with_same_semantic_identity(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    source = store.put_bytes(b"reference-mechanics-source").artifact_id
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
                set(mechanics.source_artifact_ids)
                | {
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
    assert replayed.report.report_id == report.report_id
    assert replayed.report.publication_eligible is True
    assert replayed.mechanics_certificate_artifact_id == stored_mechanics.artifact_id
    assert replayed.solver_certificate_artifact_id == stored_solver.artifact_id


def test_reference_mechanics_replay_requires_retained_source_artifact(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    missing_source = "sha256:" + "a" * 64
    certificate = _mechanics_certificate(missing_source)
    envelope = {
        "schema_name": "apex-stored-reference-mechanics-certificate",
        "schema_version": 1,
        "certificate_id": str(certificate.certificate_id),
        "certificate": certificate.semantic_payload(),
    }
    forged = store.put_bytes(canonical_json_bytes(envelope)).artifact_id
    with pytest.raises(FileNotFoundError):
        load_reference_mechanics_certificate(forged, store=store)


def test_reference_mechanics_replay_rejects_declared_identity_tamper(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    source = store.put_bytes(b"reference-mechanics-source").artifact_id
    certificate = _mechanics_certificate(source)
    envelope = {
        "schema_name": "apex-stored-reference-mechanics-certificate",
        "schema_version": 1,
        "certificate_id": "wrong-certificate-id",
        "certificate": certificate.semantic_payload(),
    }
    forged = store.put_bytes(canonical_json_bytes(envelope)).artifact_id
    with pytest.raises(ValueError, match="semantic identity mismatch"):
        load_reference_mechanics_certificate(forged, store=store)
