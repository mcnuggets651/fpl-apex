"""Truth-governed exact offline evaluator for Apex V2 Slice 11."""

from __future__ import annotations

from fractions import Fraction

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.learning_policy_registry import (
    LearningPolicyRegistry,
    load_learning_policy_registry_bytes,
)
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry_bytes
from apex_fpl.core.learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningEvaluationStatus,
    LearningUseMode,
    MetricDirection,
    instant,
)
from apex_fpl.core.learning_dataset import EvaluationDataset
from apex_fpl.core.learning_evaluation import EvaluationMetricResult, ModelEvaluationReport
from apex_fpl.core.learning_observations import EvaluationObservation, EvaluationObservationSet
from apex_fpl.core.learning_policy import LearningEvaluationPolicy, MetricRequirement
from apex_fpl.core.learning_training import ModelTrainingRun
from apex_fpl.core.outcome_truth import OutcomeTruthRegistry, TruthAuthorityStatus


_DIRECTION = {
    EvaluationMetric.START_BRIER: MetricDirection.LOWER_IS_BETTER,
    EvaluationMetric.MINUTES_MAE: MetricDirection.LOWER_IS_BETTER,
    EvaluationMetric.MINUTES_MSE: MetricDirection.LOWER_IS_BETTER,
    EvaluationMetric.POINTS_MAE: MetricDirection.LOWER_IS_BETTER,
    EvaluationMetric.POINTS_MEAN_BIAS: MetricDirection.CLOSER_TO_ZERO,
    EvaluationMetric.INTERVAL_COVERAGE: MetricDirection.HIGHER_IS_BETTER,
    EvaluationMetric.PREDICTION_COVERAGE: MetricDirection.HIGHER_IS_BETTER,
    EvaluationMetric.DECISION_REALIZED_POINTS_DELTA: MetricDirection.HIGHER_IS_BETTER,
}


def _mean(values: list[Fraction]) -> Fraction:
    if not values:
        raise ValueError("cannot compute mean of empty metric sample")
    return sum(values, Fraction(0, 1)) / len(values)


def _metric_value(value: Fraction) -> ExactMetricValue:
    return ExactMetricValue.from_fraction(value)


def _verify_artifacts(store: ArtifactStore, artifact_ids: tuple[str, ...], *, label: str) -> None:
    for artifact_id in artifact_ids:
        if not store.verify(artifact_id):
            raise ValueError(f"{label} artifact missing/corrupt: {artifact_id}")


def _validate_start_probability(observation: EvaluationObservation) -> tuple[Fraction, Fraction]:
    predicted = observation.predicted_value.as_fraction()
    actual = observation.actual_value.as_fraction()
    if predicted < 0 or predicted > 1:
        raise ValueError("START_BRIER prediction must be a probability in [0,1]")
    if actual not in {Fraction(0, 1), Fraction(1, 1)}:
        raise ValueError("START_BRIER actual value must be exactly 0 or 1")
    return predicted, actual


def _compute_metric(
    requirement: MetricRequirement,
    *,
    observations: tuple[EvaluationObservation, ...],
    total_cases: int,
    source_artifact_ids: tuple[str, ...],
) -> EvaluationMetricResult:
    metric = requirement.metric
    direction = _DIRECTION[metric]
    values: list[Fraction]
    if metric is EvaluationMetric.PREDICTION_COVERAGE:
        value = Fraction(len(observations), total_cases)
        sample_count = total_cases
    elif metric is EvaluationMetric.START_BRIER:
        values = []
        for row in observations:
            predicted, actual = _validate_start_probability(row)
            values.append((predicted - actual) ** 2)
        value = _mean(values)
        sample_count = len(observations)
    elif metric in {EvaluationMetric.MINUTES_MAE, EvaluationMetric.POINTS_MAE}:
        values = [abs(row.predicted_value.as_fraction() - row.actual_value.as_fraction()) for row in observations]
        value = _mean(values)
        sample_count = len(observations)
    elif metric is EvaluationMetric.MINUTES_MSE:
        values = [(row.predicted_value.as_fraction() - row.actual_value.as_fraction()) ** 2 for row in observations]
        value = _mean(values)
        sample_count = len(observations)
    elif metric is EvaluationMetric.POINTS_MEAN_BIAS:
        values = [row.predicted_value.as_fraction() - row.actual_value.as_fraction() for row in observations]
        value = _mean(values)
        sample_count = len(observations)
    elif metric is EvaluationMetric.INTERVAL_COVERAGE:
        values = []
        for row in observations:
            if row.interval_lower is None or row.interval_upper is None:
                raise ValueError("INTERVAL_COVERAGE observation lacks interval")
            actual = row.actual_value.as_fraction()
            inside = row.interval_lower.as_fraction() <= actual <= row.interval_upper.as_fraction()
            values.append(Fraction(int(inside), 1))
        value = _mean(values)
        sample_count = len(observations)
    elif metric is EvaluationMetric.DECISION_REALIZED_POINTS_DELTA:
        raise ValueError("decision-realized points delta requires separate sealed decision-impact evidence")
    else:  # pragma: no cover
        raise ValueError(f"unsupported evaluation metric: {metric.value}")
    return EvaluationMetricResult(
        metric=metric,
        target=requirement.target,
        cohort=requirement.cohort,
        direction=direction,
        sample_count=sample_count,
        value=_metric_value(value),
        interval_lower=None,
        interval_upper=None,
        source_artifact_ids=source_artifact_ids,
    )


def evaluate_model(
    *,
    training_run: ModelTrainingRun,
    dataset: EvaluationDataset,
    observation_set: EvaluationObservationSet,
    truth_registry: OutcomeTruthRegistry,
    truth_registry_artifact_id: str,
    policy: LearningEvaluationPolicy,
    policy_registry: LearningPolicyRegistry,
    policy_registry_artifact_id: str,
    store: ArtifactStore,
    production: bool,
) -> ModelEvaluationReport:
    """Evaluate one sealed model without hindsight or implicit authority substitution."""
    if not isinstance(production, bool):
        raise ValueError("production flag must be boolean")
    if training_run.model_artifact_id != dataset.model_artifact_id:
        raise ValueError("training run model does not match evaluation dataset model")
    if observation_set.evaluation_dataset_id != dataset.dataset_id:
        raise ValueError("observation set does not name the exact evaluation dataset")
    if dataset.truth_registry_id != truth_registry.truth_registry_id:
        raise ValueError("evaluation dataset truth-registry identity mismatch")
    retained_truth = load_outcome_truth_registry_bytes(store.read_bytes(truth_registry_artifact_id))
    if retained_truth.truth_registry_id != truth_registry.truth_registry_id:
        raise ValueError("truth registry object does not match retained registry artifact")
    retained_policy_registry = load_learning_policy_registry_bytes(store.read_bytes(policy_registry_artifact_id))
    if retained_policy_registry.semantic_payload() != policy_registry.semantic_payload():
        raise ValueError("learning policy registry object does not match retained registry artifact")
    _verify_artifacts(store, training_run.source_artifact_ids, label="training")
    _verify_artifacts(store, dataset.source_artifact_ids, label="evaluation dataset")
    policy_artifacts = tuple(
        item for item in (policy.qualification_artifact_id, policy.promotion_rule_artifact_id) if item is not None
    )
    _verify_artifacts(store, policy_artifacts, label="learning policy")
    for case in dataset.cases:
        if instant(training_run.first_available_at) > instant(case.prediction_sealed_at):
            raise ValueError("model training run was not available when evaluation prediction was sealed")
        if instant(training_run.training_cutoff) > instant(case.prediction_sealed_at):
            raise ValueError("model training cutoff is after an evaluation prediction seal")
    cases_by_id = {row.case_id: row for row in dataset.cases}
    observations_by_id = {row.case_id: row for row in observation_set.observations}
    if set(observations_by_id) - set(cases_by_id):
        raise ValueError("observation set contains case IDs outside the sealed evaluation dataset")
    for case_id, observation in observations_by_id.items():
        if observation.target is not cases_by_id[case_id].target:
            raise ValueError("evaluation observation target does not match its sealed case")
    blockers: list[str] = []
    metrics: list[EvaluationMetricResult] = []
    try:
        policy_registry.verify_policy(
            policy,
            store=store,
            season=dataset.season,
            cutoff=dataset.first_outcome_available_at,
            production=production,
        )
    except ValueError as exc:
        blockers.append(f"learning policy authority: {exc}")
    for requirement in policy.requirements:
        if requirement.cohort != "ALL":
            blockers.append(
                f"{requirement.metric.value}/{requirement.target.value}/{requirement.cohort}: "
                "cohort membership evidence is not present in the sealed observation contract"
            )
            continue
        authority = truth_registry.authority_for(requirement.target)
        if authority.status is not TruthAuthorityStatus.VERIFIED:
            blockers.append(
                f"{requirement.metric.value}/{requirement.target.value}: outcome truth authority is UNRESOLVED"
            )
            continue
        target_cases = tuple(row for row in dataset.cases if row.target is requirement.target)
        target_observations = tuple(
            observations_by_id[row.case_id] for row in target_cases if row.case_id in observations_by_id
        )
        if not target_cases:
            blockers.append(f"{requirement.metric.value}/{requirement.target.value}: evaluation dataset has no target cases")
            continue
        count_for_gate = len(target_cases) if requirement.metric is EvaluationMetric.PREDICTION_COVERAGE else len(target_observations)
        if count_for_gate < requirement.minimum_cases:
            blockers.append(
                f"{requirement.metric.value}/{requirement.target.value}: sample_count {count_for_gate} "
                f"below required {requirement.minimum_cases}"
            )
            continue
        if requirement.require_interval and any(
            row.interval_lower is None or row.interval_upper is None for row in target_observations
        ):
            blockers.append(
                f"{requirement.metric.value}/{requirement.target.value}: required prediction intervals are incomplete"
            )
            continue
        if requirement.metric is EvaluationMetric.DECISION_REALIZED_POINTS_DELTA:
            blockers.append("DECISION_REALIZED_POINTS_DELTA requires a separate sealed decision-impact evaluator")
            continue
        metric_sources = tuple(
            sorted(
                {truth_registry_artifact_id, policy_registry_artifact_id}
                | {
                    artifact
                    for row in target_cases
                    for artifact in (row.prediction_artifact_id, row.outcome_artifact_id)
                }
            )
        )
        metrics.append(
            _compute_metric(
                requirement,
                observations=target_observations,
                total_cases=len(target_cases),
                source_artifact_ids=metric_sources,
            )
        )
    required_keys = {row.key for row in policy.requirements}
    if required_keys - {row.key for row in metrics} and not blockers:
        blockers.append("required evaluation metrics are incomplete")
    status = LearningEvaluationStatus.COMPLETE if not blockers else LearningEvaluationStatus.INCONCLUSIVE
    report_sources = tuple(
        sorted(
            set(training_run.source_artifact_ids)
            | set(dataset.source_artifact_ids)
            | {truth_registry_artifact_id, policy_registry_artifact_id}
            | set(policy_artifacts)
        )
    )
    return ModelEvaluationReport(
        candidate_model_id=dataset.model_artifact_id,
        training_run_id=training_run.training_run_id,
        evaluation_dataset_id=dataset.dataset_id,
        observation_set_id=observation_set.observation_set_id,
        policy_id=policy.policy_id,
        use_mode=LearningUseMode.PRODUCTION if production else LearningUseMode.SHADOW,
        metrics=tuple(metrics),
        status=status,
        blockers=tuple(blockers),
        source_artifact_ids=report_sources,
    )
