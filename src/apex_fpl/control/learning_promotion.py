"""Governed comparison, promotion and registry transition for Apex V2 Slice 11."""

from __future__ import annotations

from fractions import Fraction

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.learning_policy_registry import (
    LearningPolicyRegistry,
    load_learning_policy_registry_bytes,
)
from apex_fpl.core.learning_common import (
    ExactMetricValue,
    LearningEvaluationStatus,
    LearningUseMode,
    MetricDirection,
    ModelPromotionDecision,
)
from apex_fpl.core.learning_evaluation import (
    MetricComparisonResult,
    ModelComparisonReport,
    ModelEvaluationReport,
)
from apex_fpl.core.learning_policy import LearningEvaluationPolicy, MetricPromotionRule
from apex_fpl.core.learning_promotion import ModelPromotionCertificate, ModelRegistryGeneration


def _verify(store: ArtifactStore, artifact_ids: tuple[str, ...], *, label: str) -> None:
    for artifact_id in artifact_ids:
        if not store.verify(artifact_id):
            raise ValueError(f"{label} artifact missing/corrupt: {artifact_id}")


def _improvement(direction: MetricDirection, candidate: Fraction, incumbent: Fraction) -> Fraction:
    if direction is MetricDirection.LOWER_IS_BETTER:
        return incumbent - candidate
    if direction is MetricDirection.HIGHER_IS_BETTER:
        return candidate - incumbent
    if direction is MetricDirection.CLOSER_TO_ZERO:
        return abs(incumbent) - abs(candidate)
    raise ValueError("unknown metric direction")


def _interval_superiority(rule: MetricPromotionRule, candidate, incumbent) -> bool | None:
    if not rule.require_interval_superiority:
        return None
    if (
        candidate.interval_lower is None
        or candidate.interval_upper is None
        or incumbent.interval_lower is None
        or incumbent.interval_upper is None
    ):
        return None
    c_low = candidate.interval_lower.as_fraction()
    c_high = candidate.interval_upper.as_fraction()
    i_low = incumbent.interval_lower.as_fraction()
    i_high = incumbent.interval_upper.as_fraction()
    if rule.direction is MetricDirection.LOWER_IS_BETTER:
        return c_high < i_low
    if rule.direction is MetricDirection.HIGHER_IS_BETTER:
        return c_low > i_high
    if rule.direction is MetricDirection.CLOSER_TO_ZERO:
        candidate_max_abs = max(abs(c_low), abs(c_high))
        incumbent_min_abs = Fraction(0, 1) if i_low <= 0 <= i_high else min(abs(i_low), abs(i_high))
        return candidate_max_abs < incumbent_min_abs
    return None


def _replay_policy_registry(
    *,
    registry: LearningPolicyRegistry,
    registry_artifact_id: str,
    store: ArtifactStore,
) -> None:
    retained = load_learning_policy_registry_bytes(store.read_bytes(registry_artifact_id))
    if retained.semantic_payload() != registry.semantic_payload():
        raise ValueError("learning policy registry object does not match retained registry artifact")


def compare_model_evaluations(
    *,
    candidate: ModelEvaluationReport,
    incumbent: ModelEvaluationReport,
    candidate_report_artifact_id: str,
    incumbent_report_artifact_id: str,
    policy: LearningEvaluationPolicy,
    policy_registry: LearningPolicyRegistry,
    policy_registry_artifact_id: str,
    policy_cutoff: str,
    store: ArtifactStore,
    production: bool,
) -> ModelComparisonReport:
    """Compare two complete reports under one retained predeclared policy authority."""

    if not isinstance(production, bool):
        raise ValueError("production flag must be boolean")
    _verify(store, (candidate_report_artifact_id, incumbent_report_artifact_id), label="evaluation report")
    _replay_policy_registry(
        registry=policy_registry,
        registry_artifact_id=policy_registry_artifact_id,
        store=store,
    )
    if candidate.candidate_model_id == incumbent.candidate_model_id:
        raise ValueError("candidate and incumbent evaluations name the same model")
    if candidate.policy_id != policy.policy_id or incumbent.policy_id != policy.policy_id:
        raise ValueError("candidate/incumbent evaluations do not use the comparison policy")

    expected_mode = LearningUseMode.PRODUCTION if production else LearningUseMode.SHADOW
    blockers: list[str] = []
    if candidate.use_mode is not expected_mode or incumbent.use_mode is not expected_mode:
        blockers.append("candidate/incumbent evaluation mode does not match comparison mode")
    if candidate.status is not LearningEvaluationStatus.COMPLETE:
        blockers.append("candidate evaluation is not COMPLETE")
    if incumbent.status is not LearningEvaluationStatus.COMPLETE:
        blockers.append("incumbent evaluation is not COMPLETE")
    try:
        policy_registry.verify_policy(
            policy,
            store=store,
            season=policy_registry.season,
            cutoff=policy_cutoff,
            production=production,
        )
    except ValueError as exc:
        blockers.append(f"learning policy authority: {exc}")

    candidate_metrics = {row.key: row for row in candidate.metrics}
    incumbent_metrics = {row.key: row for row in incumbent.metrics}
    comparisons: list[MetricComparisonResult] = []
    for rule in policy.promotion_rules:
        candidate_metric = candidate_metrics.get(rule.key)
        incumbent_metric = incumbent_metrics.get(rule.key)
        if candidate_metric is None or incumbent_metric is None:
            blockers.append(
                f"{rule.metric.value}/{rule.target.value}/{rule.cohort}: required comparison metric missing"
            )
            continue
        if candidate_metric.direction is not rule.direction or incumbent_metric.direction is not rule.direction:
            raise ValueError("metric result direction disagrees with semantic promotion rule")
        improvement = _improvement(
            rule.direction,
            candidate_metric.value.as_fraction(),
            incumbent_metric.value.as_fraction(),
        )
        comparisons.append(
            MetricComparisonResult(
                metric=rule.metric,
                target=rule.target,
                cohort=rule.cohort,
                direction=rule.direction,
                candidate_value=candidate_metric.value,
                incumbent_value=incumbent_metric.value,
                improvement=ExactMetricValue.from_fraction(improvement),
                candidate_sample_count=candidate_metric.sample_count,
                incumbent_sample_count=incumbent_metric.sample_count,
                interval_superiority=_interval_superiority(rule, candidate_metric, incumbent_metric),
            )
        )

    if len(comparisons) != len(policy.promotion_rules) and not blockers:
        blockers.append("comparison did not produce every required promotion-rule row")
    status = LearningEvaluationStatus.COMPLETE if not blockers else LearningEvaluationStatus.INCONCLUSIVE
    sources = tuple(
        sorted(
            set(candidate.source_artifact_ids)
            | set(incumbent.source_artifact_ids)
            | {candidate_report_artifact_id, incumbent_report_artifact_id, policy_registry_artifact_id}
            | {
                item
                for item in (policy.qualification_artifact_id, policy.promotion_rule_artifact_id)
                if item is not None
            }
        )
    )
    _verify(store, sources, label="comparison source")
    return ModelComparisonReport(
        candidate_model_id=candidate.candidate_model_id,
        incumbent_model_id=incumbent.candidate_model_id,
        candidate_evaluation_id=candidate.evaluation_id,
        incumbent_evaluation_id=incumbent.evaluation_id,
        policy_id=policy.policy_id,
        use_mode=expected_mode,
        comparisons=tuple(comparisons),
        status=status,
        blockers=tuple(blockers),
        source_artifact_ids=sources,
    )


def issue_model_promotion_certificate(
    *,
    comparison: ModelComparisonReport,
    comparison_artifact_id: str,
    candidate_report_artifact_id: str,
    incumbent_report_artifact_id: str,
    policy: LearningEvaluationPolicy,
    policy_registry: LearningPolicyRegistry,
    policy_registry_artifact_id: str,
    promotion_cutoff: str,
    store: ArtifactStore,
) -> ModelPromotionCertificate:
    """Issue a production promotion decision; comparison alone cannot mutate registry state."""

    _replay_policy_registry(
        registry=policy_registry,
        registry_artifact_id=policy_registry_artifact_id,
        store=store,
    )
    sources = tuple(
        sorted(
            set(comparison.source_artifact_ids)
            | {
                comparison_artifact_id,
                candidate_report_artifact_id,
                incumbent_report_artifact_id,
                policy_registry_artifact_id,
            }
            | {
                item
                for item in (policy.qualification_artifact_id, policy.promotion_rule_artifact_id)
                if item is not None
            }
        )
    )
    _verify(store, sources, label="promotion source")
    if comparison.policy_id != policy.policy_id:
        raise ValueError("comparison does not use promotion policy")

    authority_blocker: str | None = None
    try:
        policy_registry.verify_policy(
            policy,
            store=store,
            season=policy_registry.season,
            cutoff=promotion_cutoff,
            production=True,
        )
    except ValueError as exc:
        authority_blocker = str(exc)

    if (
        comparison.use_mode is not LearningUseMode.PRODUCTION
        or comparison.status is not LearningEvaluationStatus.COMPLETE
        or authority_blocker is not None
    ):
        decision = ModelPromotionDecision.INCONCLUSIVE
        reason = (
            f"learning policy authority: {authority_blocker}"
            if authority_blocker is not None
            else "comparison is not a COMPLETE production-mode comparison"
        )
    else:
        rows = {row.key: row for row in comparison.comparisons}
        failed: list[str] = []
        inconclusive: list[str] = []
        for rule in policy.promotion_rules:
            row = rows.get(rule.key)
            if row is None:
                inconclusive.append(f"missing {rule.metric.value}/{rule.target.value}/{rule.cohort}")
                continue
            if row.improvement.as_fraction() < rule.minimum_improvement.as_fraction():
                failed.append(
                    f"{rule.metric.value}/{rule.target.value}/{rule.cohort} improvement below threshold"
                )
            if rule.require_interval_superiority:
                if row.interval_superiority is None:
                    inconclusive.append(
                        f"{rule.metric.value}/{rule.target.value}/{rule.cohort} interval evidence missing"
                    )
                elif row.interval_superiority is False:
                    failed.append(
                        f"{rule.metric.value}/{rule.target.value}/{rule.cohort} interval superiority failed"
                    )
        if inconclusive:
            decision = ModelPromotionDecision.INCONCLUSIVE
            reason = "; ".join(inconclusive + failed)
        elif failed:
            decision = ModelPromotionDecision.RETAIN
            reason = "; ".join(failed)
        else:
            decision = ModelPromotionDecision.PROMOTE
            reason = "all predeclared promotion rules passed"

    return ModelPromotionCertificate(
        candidate_model_id=comparison.candidate_model_id,
        incumbent_model_id=comparison.incumbent_model_id,
        candidate_evaluation_id=comparison.candidate_evaluation_id,
        incumbent_evaluation_id=comparison.incumbent_evaluation_id,
        comparison_id=comparison.comparison_id,
        policy_id=policy.policy_id,
        decision=decision,
        reason=reason,
        source_artifact_ids=sources,
    )


def apply_model_promotion(
    *,
    current: ModelRegistryGeneration,
    promotion: ModelPromotionCertificate,
    expected_parent_generation_id,
    current_generation_artifact_id: str,
    promotion_artifact_id: str,
    store: ArtifactStore,
) -> ModelRegistryGeneration:
    """CAS-style registry transition; stale writers and non-PROMOTE certificates fail."""

    _verify(store, (current_generation_artifact_id, promotion_artifact_id), label="registry transition")
    if expected_parent_generation_id != current.generation_id:
        raise ValueError("stale model-registry writer: expected parent identity does not match current")
    if promotion.decision is not ModelPromotionDecision.PROMOTE:
        raise ValueError("only PROMOTE certificates may change model-registry champion")
    if promotion.candidate_model_id not in current.registered_model_ids:
        raise ValueError("promotion candidate is not registered in current model registry")
    if promotion.incumbent_model_id not in current.registered_model_ids:
        raise ValueError("promotion incumbent/baseline is not registered in current model registry")
    if current.champion_model_id is not None and promotion.incumbent_model_id != current.champion_model_id:
        raise ValueError("promotion incumbent does not match current champion")
    sources = tuple(
        sorted(
            set(current.source_artifact_ids)
            | set(promotion.source_artifact_ids)
            | {current_generation_artifact_id, promotion_artifact_id}
        )
    )
    _verify(store, sources, label="next registry generation source")
    return ModelRegistryGeneration(
        season=current.season,
        generation=current.generation + 1,
        parent_generation_id=current.generation_id,
        registered_model_ids=current.registered_model_ids,
        champion_model_id=promotion.candidate_model_id,
        promotion_id=promotion.promotion_id,
        source_artifact_ids=sources,
    )
