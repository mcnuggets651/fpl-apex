from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.reference_solver_registry import (
    ReferenceSolverRegistry,
    load_reference_solver_registry,
)
from apex_fpl.core.assurance import ReferenceSolverCertificate, ReferenceSolverStatus
from apex_fpl.core.decision import RationalValue
from apex_fpl.core.ids import CandidateUniverseId, DecisionInputId, DecisionPolicyId
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)


def _certificate(store: FileSystemArtifactStore) -> ReferenceSolverCertificate:
    worker = store.put_bytes(b"reference-worker-code").artifact_id
    solver_input = store.put_bytes(b"reference-input").artifact_id
    solver_output = store.put_bytes(b"reference-output").artifact_id
    return ReferenceSolverCertificate(
        decision_input_id=DecisionInputId("registry-input"),
        candidate_universe_id=CandidateUniverseId("registry-universe"),
        decision_policy_id=DecisionPolicyId("registry-policy"),
        worker_name="registry-worker",
        worker_version="1",
        solver_status=ReferenceSolverStatus.OPTIMAL,
        best_objective=RationalValue(50, 1),
        best_bound=RationalValue(50, 1),
        gap=RationalValue.zero(),
        selected_action_id="registry-action",
        action_surface_complete=True,
        tie_break_policy_id="registry-tie-v1",
        solver_input_artifact_id=solver_input,
        solver_output_artifact_id=solver_output,
        worker_artifact_id=worker,
    )


def _worker(
    store: FileSystemArtifactStore,
    certificate: ReferenceSolverCertificate,
    *,
    qualified: bool,
) -> ReferenceSolverWorkerArtifact:
    qualification = (
        store.put_bytes(b"reference-worker-qualification").artifact_id
        if qualified
        else None
    )
    return ReferenceSolverWorkerArtifact(
        worker_name=certificate.worker_name,
        worker_version=certificate.worker_version,
        solver_contract="apex-v2-exact-decision-parity-v1",
        code_artifact_id=certificate.worker_artifact_id,
        qualification_state=(
            ReferenceSolverWorkerQualification.QUALIFIED
            if qualified
            else ReferenceSolverWorkerQualification.SHADOW
        ),
        qualification_artifact_id=qualification,
        valid_seasons=("2026-2027",),
        first_available_at="2026-08-24T00:00:00Z",
        max_horizon_gameweeks=8,
    )


def test_reference_solver_registry_starts_with_no_fabricated_champion() -> None:
    registry = load_reference_solver_registry(Path("config/reference_solvers_v2.yaml"))
    assert registry.workers == ()
    assert registry.champion() is None


def test_production_reference_solver_requires_registered_qualified_champion(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    certificate = _certificate(store)
    worker = _worker(store, certificate, qualified=True)
    registry = ReferenceSolverRegistry(
        season="2026-2027",
        workers=(worker,),
        champion_worker_id=worker.worker_id,
    )
    verified = registry.verify_certificate_worker(
        certificate,
        store=store,
        season="2026-2027",
        cutoff="2026-08-24T06:00:00Z",
        horizon_gameweeks=1,
        production=True,
    )
    assert verified.worker_id == worker.worker_id

    shadow = _worker(store, certificate, qualified=False)
    shadow_registry = ReferenceSolverRegistry(
        season="2026-2027",
        workers=(shadow,),
    )
    with pytest.raises(ValueError, match="qualified"):
        shadow_registry.verify_certificate_worker(
            certificate,
            store=store,
            season="2026-2027",
            cutoff="2026-08-24T06:00:00Z",
            horizon_gameweeks=1,
            production=True,
        )


def test_reference_solver_registry_rejects_worker_code_identity_mismatch(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    certificate = _certificate(store)
    other_code = store.put_bytes(b"different-reference-worker-code").artifact_id
    qualification = store.put_bytes(b"reference-worker-qualification").artifact_id
    mismatched = ReferenceSolverWorkerArtifact(
        worker_name=certificate.worker_name,
        worker_version=certificate.worker_version,
        solver_contract="apex-v2-exact-decision-parity-v1",
        code_artifact_id=other_code,
        qualification_state=ReferenceSolverWorkerQualification.QUALIFIED,
        qualification_artifact_id=qualification,
        valid_seasons=("2026-2027",),
        first_available_at="2026-08-24T00:00:00Z",
        max_horizon_gameweeks=8,
    )
    registry = ReferenceSolverRegistry(
        season="2026-2027",
        workers=(mismatched,),
        champion_worker_id=mismatched.worker_id,
    )
    with pytest.raises(ValueError, match="not registered under exact identity"):
        registry.verify_certificate_worker(
            certificate,
            store=store,
            season="2026-2027",
            cutoff="2026-08-24T06:00:00Z",
            horizon_gameweeks=1,
            production=True,
        )


def test_reference_solver_registry_uses_calendar_horizon_and_no_future_worker(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    certificate = _certificate(store)
    qualification = store.put_bytes(b"reference-worker-qualification").artifact_id
    worker = ReferenceSolverWorkerArtifact(
        worker_name=certificate.worker_name,
        worker_version=certificate.worker_version,
        solver_contract="apex-v2-exact-decision-parity-v1",
        code_artifact_id=certificate.worker_artifact_id,
        qualification_state=ReferenceSolverWorkerQualification.QUALIFIED,
        qualification_artifact_id=qualification,
        valid_seasons=("2026-2027",),
        first_available_at="2026-08-25T00:00:00Z",
        max_horizon_gameweeks=2,
    )
    registry = ReferenceSolverRegistry(
        season="2026-2027",
        workers=(worker,),
        champion_worker_id=worker.worker_id,
    )
    with pytest.raises(ValueError, match="not available"):
        registry.verify_certificate_worker(
            certificate,
            store=store,
            season="2026-2027",
            cutoff="2026-08-24T06:00:00Z",
            horizon_gameweeks=1,
            production=True,
        )
    with pytest.raises(ValueError, match="horizon"):
        registry.verify_certificate_worker(
            certificate,
            store=store,
            season="2026-2027",
            cutoff="2026-08-26T06:00:00Z",
            horizon_gameweeks=3,
            production=True,
        )
