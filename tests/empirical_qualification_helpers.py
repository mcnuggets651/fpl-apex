from __future__ import annotations

from apex_fpl.control.experiment_registry import (
    ExperimentRegistration,
    ExperimentRegistry,
    derive_empirical_qualification_certificate,
    store_empirical_qualification_certificate,
    store_experiment_definition,
    store_experiment_registry,
    store_experiment_result,
)
from apex_fpl.core.experiments import (
    ExactQualificationValue,
    ExperimentDefinition,
    ExperimentResult,
    QualificationMetricDirection,
    QualificationMetricResult,
    QualificationMetricRule,
    qualification_subject_id,
)


def synthetic_supported_qualification_artifact(
    *,
    store,
    subject_payload: dict[str, object],
    subject_kind: str,
    proof_id: str,
    season: str,
    declared_at: str = "2026-07-01T00:00:00Z",
    evaluation_window_start: str = "2026-07-02T00:00:00Z",
    evaluation_window_end: str = "2026-07-31T00:00:00Z",
    evaluated_at: str = "2026-07-31T00:00:00Z",
    valid_until: str = "2026-09-30T00:00:00Z",
) -> str:
    """Create supported typed evidence for mechanism tests only.

    This deliberately exercises the real immutable experiment/certificate path. The
    generated evidence is synthetic and must never be treated as a production
    qualification or registered in production configuration.
    """

    evaluator_artifact_id = store.put_bytes(
        f"synthetic-evaluator:{proof_id}:{subject_kind}".encode("utf-8")
    ).artifact_id
    policy_artifact_id = store.put_bytes(
        f"synthetic-qualification-policy:{proof_id}:{subject_kind}".encode("utf-8")
    ).artifact_id
    source_artifact_id = store.put_bytes(
        f"synthetic-qualification-source:{proof_id}:{subject_kind}".encode("utf-8")
    ).artifact_id
    definition = ExperimentDefinition(
        proof_id=proof_id,
        subject_kind=subject_kind,
        subject_id=qualification_subject_id(subject_payload),
        season=season,
        evaluator_artifact_id=evaluator_artifact_id,
        policy_artifact_id=policy_artifact_id,
        declared_at=declared_at,
        evaluation_window_start=evaluation_window_start,
        evaluation_window_end=evaluation_window_end,
        minimum_sample_size=1,
        metric_rules=(
            QualificationMetricRule(
                metric_id="synthetic-qualification-score",
                direction=QualificationMetricDirection.AT_LEAST,
                threshold=ExactQualificationValue(1, 1),
            ),
        ),
        valid_until=valid_until,
    )
    definition_ref = store_experiment_definition(definition, store=store)
    result = ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=proof_id,
        subject_kind=subject_kind,
        subject_id=definition.subject_id,
        season=season,
        evaluator_artifact_id=evaluator_artifact_id,
        evaluated_at=evaluated_at,
        sample_size=1,
        metrics=(
            QualificationMetricResult(
                metric_id="synthetic-qualification-score",
                value=ExactQualificationValue(1, 1),
            ),
        ),
        source_artifact_ids=(source_artifact_id,),
    )
    result_ref = store_experiment_result(result, store=store)
    registry = ExperimentRegistry(
        season=season,
        registrations=(
            ExperimentRegistration(
                experiment_id=definition.experiment_id,
                definition_artifact_id=definition_ref.artifact_id,
            ),
        ),
    )
    registry_ref = store_experiment_registry(registry, store=store)
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=definition_ref.artifact_id,
        result_artifact_id=result_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        store=store,
    )
    if not certificate.supported:
        raise AssertionError(f"synthetic qualification fixture was not supported: {certificate.blockers}")
    return store_empirical_qualification_certificate(certificate, store=store).artifact_id
