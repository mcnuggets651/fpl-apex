from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.empirical_qualification_admission import (
    verify_typed_empirical_qualification,
)
from apex_fpl.control.experiment_registry import (
    ExperimentRegistration,
    ExperimentRegistry,
    derive_empirical_qualification_certificate,
    load_empirical_qualification_certificate,
    load_experiment_registry,
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
    qualification_subject_id,
)
from apex_fpl.core.production import MANDATORY_PRODUCTION_PROOF_IDS
from apex_fpl.core.production_proof_contract import (
    EMPIRICAL_PRODUCTION_PROOF_IDS,
    PRODUCTION_PROOF_CLASSES,
)
from apex_fpl.core.proofs import ProofClass


SEASON = "2026-2027"
PROOF_ID = "PO-FORECAST-QUALIFICATION-001"
SUBJECT_KIND = "apex.forecast-model"
SUBJECT_PAYLOAD = {
    "schema_name": "synthetic-model",
    "model_name": "candidate",
    "model_version": "1",
    "qualification_state": "QUALIFIED",
    "qualification_artifact_id": "sha256:" + "0" * 64,
    "feature_contract": "v1",
}


def _artifact(store: FileSystemArtifactStore, value: str) -> str:
    return store.put_bytes(value.encode("utf-8")).artifact_id


def _definition(store: FileSystemArtifactStore) -> ExperimentDefinition:
    return ExperimentDefinition(
        proof_id=PROOF_ID,
        subject_kind=SUBJECT_KIND,
        subject_id=qualification_subject_id(SUBJECT_PAYLOAD),
        season=SEASON,
        evaluator_artifact_id=_artifact(store, "evaluator"),
        policy_artifact_id=_artifact(store, "policy"),
        declared_at="2026-08-01T00:00:00Z",
        evaluation_window_start="2026-08-02T00:00:00Z",
        evaluation_window_end="2026-08-20T00:00:00Z",
        minimum_sample_size=20,
        metric_rules=(
            QualificationMetricRule(
                metric_id="brier",
                direction=QualificationMetricDirection.AT_MOST,
                threshold=ExactQualificationValue(1, 4),
            ),
            QualificationMetricRule(
                metric_id="mean-bias",
                direction=QualificationMetricDirection.ABS_AT_MOST,
                threshold=ExactQualificationValue(1, 10),
            ),
        ),
        valid_until="2026-09-01T00:00:00Z",
    )


def _result(
    store: FileSystemArtifactStore,
    definition: ExperimentDefinition,
    *,
    sample_size: int = 20,
    proof_id: str = PROOF_ID,
    subject_id: str | None = None,
    brier: ExactQualificationValue = ExactQualificationValue(1, 5),
) -> ExperimentResult:
    return ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=proof_id,
        subject_kind=definition.subject_kind,
        subject_id=definition.subject_id if subject_id is None else subject_id,
        season=SEASON,
        evaluator_artifact_id=definition.evaluator_artifact_id,
        evaluated_at="2026-08-20T00:00:00Z",
        sample_size=sample_size,
        metrics=(
            QualificationMetricResult("brier", brier),
            QualificationMetricResult("mean-bias", ExactQualificationValue(-1, 20)),
        ),
        source_artifact_ids=(_artifact(store, f"source:{sample_size}:{proof_id}:{subject_id}"),),
    )


def _seal(
    store: FileSystemArtifactStore,
    definition: ExperimentDefinition,
    result: ExperimentResult,
):
    definition_ref = store_experiment_definition(definition, store=store)
    result_ref = store_experiment_result(result, store=store)
    registry = ExperimentRegistry(
        season=SEASON,
        registrations=(
            ExperimentRegistration(definition.experiment_id, definition_ref.artifact_id),
        ),
    )
    registry_ref = store_experiment_registry(registry, store=store)
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=definition_ref.artifact_id,
        result_artifact_id=result_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        store=store,
    )
    certificate_ref = store_empirical_qualification_certificate(certificate, store=store)
    return certificate, certificate_ref.artifact_id


def test_qualification_subject_identity_ignores_only_qualification_attachment() -> None:
    baseline = qualification_subject_id(SUBJECT_PAYLOAD)
    reattached = dict(SUBJECT_PAYLOAD)
    reattached["qualification_state"] = "SHADOW"
    reattached["qualification_artifact_id"] = None
    assert qualification_subject_id(reattached) == baseline

    changed_semantics = dict(SUBJECT_PAYLOAD)
    changed_semantics["feature_contract"] = "v2"
    assert qualification_subject_id(changed_semantics) != baseline


def test_experiment_must_be_predeclared_before_evaluation_window() -> None:
    with pytest.raises(ValueError, match="predeclared"):
        ExperimentDefinition(
            proof_id=PROOF_ID,
            subject_kind=SUBJECT_KIND,
            subject_id="subject",
            season=SEASON,
            evaluator_artifact_id="sha256:" + "1" * 64,
            policy_artifact_id="sha256:" + "2" * 64,
            declared_at="2026-08-03T00:00:00Z",
            evaluation_window_start="2026-08-02T00:00:00Z",
            evaluation_window_end="2026-08-20T00:00:00Z",
            minimum_sample_size=1,
            metric_rules=(
                QualificationMetricRule(
                    "metric",
                    QualificationMetricDirection.AT_LEAST,
                    ExactQualificationValue(0, 1),
                ),
            ),
            valid_until="2026-09-01T00:00:00Z",
        )


def test_supported_certificate_replays_from_registered_immutable_evidence(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    definition = _definition(store)
    certificate, artifact_id = _seal(store, definition, _result(store, definition))
    assert certificate.decision is EmpiricalQualificationDecision.SUPPORTED
    replayed = load_empirical_qualification_certificate(
        artifact_id,
        store=store,
        as_of="2026-08-25T00:00:00Z",
    )
    assert replayed.certificate_id == certificate.certificate_id


def test_insufficient_sample_is_inconclusive_not_supported(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    definition = _definition(store)
    certificate, _ = _seal(store, definition, _result(store, definition, sample_size=19))
    assert certificate.decision is EmpiricalQualificationDecision.INCONCLUSIVE
    assert any("insufficient sample" in blocker for blocker in certificate.blockers)


def test_failed_metric_threshold_is_rejected(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    definition = _definition(store)
    certificate, _ = _seal(
        store,
        definition,
        _result(store, definition, brier=ExactQualificationValue(1, 2)),
    )
    assert certificate.decision is EmpiricalQualificationDecision.REJECTED


def test_structural_identity_mismatch_is_rejected(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    definition = _definition(store)
    certificate, _ = _seal(
        store,
        definition,
        _result(store, definition, subject_id="different-subject"),
    )
    assert certificate.decision is EmpiricalQualificationDecision.REJECTED
    assert any("subject_id mismatch" in blocker for blocker in certificate.blockers)


def test_typed_admission_rejects_wrong_subject_future_and_expired_certificate(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    definition = _definition(store)
    _, artifact_id = _seal(store, definition, _result(store, definition))

    verify_typed_empirical_qualification(
        qualification_artifact_id=artifact_id,
        subject_payload=SUBJECT_PAYLOAD,
        subject_kind=SUBJECT_KIND,
        proof_id=PROOF_ID,
        season=SEASON,
        as_of="2026-08-25T00:00:00Z",
        store=store,
    )
    with pytest.raises(ValueError, match="not yet available"):
        verify_typed_empirical_qualification(
            qualification_artifact_id=artifact_id,
            subject_payload=SUBJECT_PAYLOAD,
            subject_kind=SUBJECT_KIND,
            proof_id=PROOF_ID,
            season=SEASON,
            as_of="2026-08-19T23:59:59Z",
            store=store,
        )
    with pytest.raises(ValueError, match="expired"):
        verify_typed_empirical_qualification(
            qualification_artifact_id=artifact_id,
            subject_payload=SUBJECT_PAYLOAD,
            subject_kind=SUBJECT_KIND,
            proof_id=PROOF_ID,
            season=SEASON,
            as_of="2026-09-02T00:00:00Z",
            store=store,
        )
    changed = dict(SUBJECT_PAYLOAD)
    changed["feature_contract"] = "wrong"
    with pytest.raises(ValueError, match="subject identity"):
        verify_typed_empirical_qualification(
            qualification_artifact_id=artifact_id,
            subject_payload=changed,
            subject_kind=SUBJECT_KIND,
            proof_id=PROOF_ID,
            season=SEASON,
            as_of="2026-08-25T00:00:00Z",
            store=store,
        )


def test_default_experiment_registry_is_empty_and_fail_closed() -> None:
    registry = load_experiment_registry("config/experiments_v2.yaml")
    assert registry.season == SEASON
    assert registry.registrations == ()


def test_production_proof_class_contract_exactly_matches_required_yaml() -> None:
    payload = yaml.safe_load(Path("config/proof_obligations.yaml").read_text(encoding="utf-8"))
    required = {
        row["proof_id"]: ProofClass(row["proof_class"])
        for row in payload["proof_obligations"]
        if row["release_policy"] == "REQUIRED"
    }
    assert set(PRODUCTION_PROOF_CLASSES) == set(MANDATORY_PRODUCTION_PROOF_IDS)
    assert PRODUCTION_PROOF_CLASSES == required
    assert EMPIRICAL_PRODUCTION_PROOF_IDS == {
        proof_id
        for proof_id, proof_class in required.items()
        if proof_class is ProofClass.EMPIRICAL_QUALIFICATION
    }
