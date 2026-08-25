from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.experiment_registry import (
    ExperimentRegistration,
    ExperimentRegistry,
    derive_empirical_qualification_certificate,
    load_empirical_qualification_certificate,
    store_empirical_qualification_certificate,
    store_experiment_definition,
    store_experiment_registry,
    store_experiment_result,
)
from apex_fpl.core.experiments import (
    EmpiricalQualificationDecision,
    ExactQualificationValue,
    ExperimentDefinition,
    ExperimentResult,
    QualificationMetricDirection,
    QualificationMetricResult,
    QualificationMetricRule,
)


def _artifact(store: FileSystemArtifactStore, value: str) -> str:
    return store.put_bytes(value.encode("utf-8")).artifact_id


def _definition(store: FileSystemArtifactStore) -> ExperimentDefinition:
    return ExperimentDefinition(
        proof_id="PO-FORECAST-QUALIFICATION-001",
        subject_kind="apex.forecast-model",
        subject_id="subject-a",
        season="2026-2027",
        evaluator_artifact_id=_artifact(store, "evaluator"),
        policy_artifact_id=_artifact(store, "policy"),
        declared_at="2026-08-01T00:00:00Z",
        evaluation_window_start="2026-08-02T00:00:00Z",
        evaluation_window_end="2026-08-20T00:00:00Z",
        minimum_sample_size=20,
        metric_rules=(
            QualificationMetricRule(
                "score",
                QualificationMetricDirection.AT_LEAST,
                ExactQualificationValue(1, 2),
            ),
        ),
        valid_until="2026-09-01T00:00:00Z",
    )


def _seal(store: FileSystemArtifactStore, result: ExperimentResult):
    definition = _definition(store)
    definition_ref = store_experiment_definition(definition, store=store)
    result_ref = store_experiment_result(result, store=store)
    registry_ref = store_experiment_registry(
        ExperimentRegistry(
            season="2026-2027",
            registrations=(
                ExperimentRegistration(definition.experiment_id, definition_ref.artifact_id),
            ),
        ),
        store=store,
    )
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=definition_ref.artifact_id,
        result_artifact_id=result_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        store=store,
    )
    certificate_ref = store_empirical_qualification_certificate(certificate, store=store)
    return certificate, certificate_ref.artifact_id


def test_structural_mismatch_is_rejected_even_when_sample_is_also_incomplete(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    definition = _definition(store)
    result = ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=definition.proof_id,
        subject_kind=definition.subject_kind,
        subject_id="different-subject",
        season=definition.season,
        evaluator_artifact_id=definition.evaluator_artifact_id,
        evaluated_at="2026-08-20T00:00:00Z",
        sample_size=1,
        metrics=(
            QualificationMetricResult("score", ExactQualificationValue(1, 2)),
        ),
        source_artifact_ids=(_artifact(store, "source"),),
    )
    certificate, _ = _seal(store, result)
    assert certificate.decision is EmpiricalQualificationDecision.REJECTED
    assert any("subject_id mismatch" in blocker for blocker in certificate.blockers)
    assert any("insufficient sample" in blocker for blocker in certificate.blockers)


def test_qualification_expires_at_exact_valid_until_boundary(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    definition = _definition(store)
    result = ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=definition.proof_id,
        subject_kind=definition.subject_kind,
        subject_id=definition.subject_id,
        season=definition.season,
        evaluator_artifact_id=definition.evaluator_artifact_id,
        evaluated_at="2026-08-20T00:00:00Z",
        sample_size=20,
        metrics=(
            QualificationMetricResult("score", ExactQualificationValue(1, 2)),
        ),
        source_artifact_ids=(_artifact(store, "source"),),
    )
    certificate, artifact_id = _seal(store, result)
    assert certificate.decision is EmpiricalQualificationDecision.SUPPORTED
    with pytest.raises(ValueError, match="expired"):
        load_empirical_qualification_certificate(
            artifact_id,
            store=store,
            as_of="2026-09-01T00:00:00Z",
        )
