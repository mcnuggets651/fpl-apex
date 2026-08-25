from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.assurance.reference_mechanics import certify_selected_action
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
from apex_fpl.core.assurance import AssuranceParityStatus, IndependentAssuranceReport

from reference_solver_qualification_helpers import (
    build_qualified_reference_solver_bundle,
    ruleset,
)


def _stored_pass(store: FileSystemArtifactStore):
    bundle = build_qualified_reference_solver_bundle(store)
    mechanics = certify_selected_action(
        bundle.result,
        state=bundle.state,
        forecast=bundle.forecast,
        universe=bundle.universe,
        ruleset=ruleset(),
    )
    solver = bundle.solver_certificate
    authorization = create_reference_solver_authorization(
        solver,
        worker_registry=bundle.registry,
        registry_artifact_id=None,
        store=store,
        season="2026-2027",
        decision_cutoff=bundle.forecast.feature_cutoff,
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
    return stored_report, authorization, solver, bundle


def test_publication_pass_replays_qualified_champion_authorization(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    stored_report, authorization, _, _ = _stored_pass(store)
    replayed = load_independent_assurance_report(stored_report.artifact_id, store=store)
    verified = verify_stored_independent_assurance(replayed, store=store)
    assert verified.stored_report.report.publication_eligible is True
    assert verified.solver_authorization is not None
    assert verified.solver_authorization.artifact_id == authorization.artifact_id


def test_pass_looking_report_without_authorization_is_rejected_on_verified_replay(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bundle = build_qualified_reference_solver_bundle(store)
    mechanics = certify_selected_action(
        bundle.result,
        state=bundle.state,
        forecast=bundle.forecast,
        universe=bundle.universe,
        ruleset=ruleset(),
    )
    solver = bundle.solver_certificate
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
    _, authorization, solver, _ = _stored_pass(source_store)
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
