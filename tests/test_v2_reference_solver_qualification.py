from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.reference_solver_qualification import (
    derive_reference_solver_algorithmic_qualification,
    load_reference_solver_qualification_corpus,
    store_reference_solver_qualification_corpus,
    verify_reference_solver_algorithmic_qualification,
)
from apex_fpl.core.reference_solver_qualification import (
    REFERENCE_SOLVER_REQUIRED_COVERAGE,
    ReferenceSolverQualificationCorpus,
    reference_solver_worker_subject_id,
)
from apex_fpl.core.reference_solver_worker import ReferenceSolverWorkerQualification

from reference_solver_qualification_helpers import build_qualified_reference_solver_bundle


def test_algorithmic_qualification_replays_exact_corpus_and_authorizes_registry(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bundle = build_qualified_reference_solver_bundle(store)
    certificate = verify_reference_solver_algorithmic_qualification(
        bundle.worker,
        qualification_artifact_id=bundle.qualification_artifact_id,
        store=store,
        season="2026-2027",
        horizon_gameweeks=1,
    )
    assert certificate.passed_case_count == 3
    assert certificate.coverage_tags == REFERENCE_SOLVER_REQUIRED_COVERAGE
    verified = bundle.registry.verify_certificate_worker(
        bundle.solver_certificate,
        store=store,
        season="2026-2027",
        cutoff=bundle.forecast.feature_cutoff,
        horizon_gameweeks=1,
        production=True,
    )
    assert verified.worker_id == bundle.worker.worker_id


def test_qualification_stable_subject_ignores_only_qualification_fields(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bundle = build_qualified_reference_solver_bundle(store)
    shadow = replace(
        bundle.worker,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
    )
    assert reference_solver_worker_subject_id(bundle.worker.semantic_payload()) == (
        reference_solver_worker_subject_id(shadow.semantic_payload())
    )
    different_code = store.put_bytes(b"different-worker-source").artifact_id
    changed = replace(shadow, code_artifact_id=different_code)
    assert reference_solver_worker_subject_id(changed.semantic_payload()) != (
        reference_solver_worker_subject_id(shadow.semantic_payload())
    )


def test_random_sha_cannot_replace_replay_derived_qualification(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bundle = build_qualified_reference_solver_bundle(store)
    fake = store.put_bytes(b"not-an-algorithmic-qualification").artifact_id
    forged = replace(bundle.worker, qualification_artifact_id=fake)
    with pytest.raises(ValueError, match="qualification"):
        bundle.registry.__class__(
            season="2026-2027",
            workers=(forged,),
            champion_worker_id=forged.worker_id,
        ).verify_certificate_worker(
            bundle.solver_certificate,
            store=store,
            season="2026-2027",
            cutoff=bundle.forecast.feature_cutoff,
            horizon_gameweeks=1,
            production=True,
        )


def test_qualification_scope_cannot_be_stretched_beyond_corpus(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bundle = build_qualified_reference_solver_bundle(store)
    with pytest.raises(ValueError, match="horizon"):
        verify_reference_solver_algorithmic_qualification(
            bundle.worker,
            qualification_artifact_id=bundle.qualification_artifact_id,
            store=store,
            season="2026-2027",
            horizon_gameweeks=2,
        )


def test_qualification_corpus_is_reexecuted_not_merely_hash_checked(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bundle = build_qualified_reference_solver_bundle(store)
    other_code = store.put_bytes(b"different-code-artifact").artifact_id
    changed_worker = replace(
        bundle.worker,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
        code_artifact_id=other_code,
    )
    derived = derive_reference_solver_algorithmic_qualification(
        changed_worker,
        corpus_artifact_id=bundle.corpus_artifact_id,
        store=store,
    )
    assert derived.worker_subject_id != reference_solver_worker_subject_id(
        bundle.worker.semantic_payload()
    )
    assert derived.worker_code_artifact_id == other_code


def test_trivial_replayable_corpus_cannot_self_qualify(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bundle = build_qualified_reference_solver_bundle(store)
    full = load_reference_solver_qualification_corpus(
        bundle.corpus_artifact_id,
        store=store,
    )
    weak = ReferenceSolverQualificationCorpus(
        season=full.season,
        horizon_gameweeks=full.horizon_gameweeks,
        solver_contract=full.solver_contract,
        case_artifact_ids=(bundle.case_artifact_ids[0],),
    )
    weak_artifact = store_reference_solver_qualification_corpus(weak, store=store)
    shadow = replace(
        bundle.worker,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
    )
    with pytest.raises(ValueError, match="mandatory derived coverage"):
        derive_reference_solver_algorithmic_qualification(
            shadow,
            corpus_artifact_id=weak_artifact,
            store=store,
        )