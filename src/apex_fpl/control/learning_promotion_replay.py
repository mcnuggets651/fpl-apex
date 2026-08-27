"""Replay verification for forecast-model promotion authority.

The learning engine owns promotion semantics. This verifier consumes only retained
content-addressed outputs and re-derives the final promotion decision from the exact
candidate/incumbent evaluation rows, comparison rows and qualified champion learning
policy that were available when production champion authority was authorized.
"""

from __future__ import annotations

from fractions import Fraction

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.learning_policy_registry import (
    LearningPolicyRegistry,
    load_learning_policy_registry_bytes,
)
from apex_fpl.control.learning_store import StoredLearningObject, load_learning_object
from apex_fpl.core.learning_common import ModelPromotionDecision
from apex_fpl.core.learning_policy import LearningEvaluationPolicy, MetricPromotionRule


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _exact(value: object, *, label: str) -> Fraction:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be exact-value object")
    numerator = _strict_int(value.get("numerator"), label=f"{label} numerator")
    denominator = _strict_int(value.get("denominator"), label=f"{label} denominator")
    if denominator == 0:
        raise ValueError(f"{label} denominator cannot be zero")
    return Fraction(numerator, denominator)


def _rows(value: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be array of objects")
    return [dict(row) for row in value]


def _source_ids(
    stored: StoredLearningObject,
    *,
    label: str,
) -> tuple[str, ...]:
    raw = stored.payload.get("source_artifact_ids")
    if not isinstance(raw, list) or any(not isinstance(item, str) for item in raw):
        raise ValueError(f"{label} payload source artifacts must be string array")
    canonical = tuple(sorted(set(raw)))
    if len(canonical) != len(raw):
        raise ValueError(f"{label} payload source artifacts must be unique/canonical")
    if canonical != stored.source_artifact_ids:
        raise ValueError(f"{label} envelope/payload source artifacts disagree")
    return canonical


def _metric_key(row: dict[str, object], *, label: str) -> tuple[str, str, str]:
    metric = str(row.get("metric") or "").strip()
    target = str(row.get("target") or "").strip()
    cohort = str(row.get("cohort") or "").strip()
    if not all((metric, target, cohort)):
        raise ValueError(f"{label} metric key is incomplete")
    return metric, target, cohort


def _row_map(value: object, *, label: str) -> dict[tuple[str, str, str], dict[str, object]]:
    result: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in _rows(value, label=label):
        key = _metric_key(row, label=label)
        if key in result:
            raise ValueError(f"{label} contains duplicate metric key")
        result[key] = row
    if not result:
        raise ValueError(f"{label} cannot be empty")
    return result


def _find_learning_source(
    source_artifact_ids: tuple[str, ...],
    *,
    object_type: str,
    semantic_id: str,
    store: ArtifactStore,
    label: str,
) -> StoredLearningObject:
    matches: list[StoredLearningObject] = []
    for artifact_id in source_artifact_ids:
        try:
            value = load_learning_object(
                artifact_id,
                store=store,
                expected_object_type=object_type,
                expected_semantic_id=semantic_id,
            )
        except (FileNotFoundError, ValueError):
            continue
        matches.append(value)
    if len(matches) != 1:
        raise ValueError(f"{label} must replay exactly one retained {object_type}")
    return matches[0]


def _policy_authority(
    source_artifact_ids: tuple[str, ...],
    *,
    policy_id: str,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> tuple[LearningPolicyRegistry, LearningEvaluationPolicy, str]:
    matches: list[tuple[LearningPolicyRegistry, LearningEvaluationPolicy, str]] = []
    for artifact_id in source_artifact_ids:
        try:
            registry = load_learning_policy_registry_bytes(store.read_bytes(artifact_id))
        except (FileNotFoundError, TypeError, ValueError):
            continue
        policy = next(
            (item for item in registry.policies if str(item.policy_id) == policy_id),
            None,
        )
        if policy is not None:
            matches.append((registry, policy, artifact_id))
    if len(matches) != 1:
        raise ValueError(
            "forecast promotion must replay exactly one retained learning-policy registry"
        )
    registry, policy, artifact_id = matches[0]
    if registry.season != season:
        raise ValueError("forecast promotion learning-policy registry season mismatch")
    registry.verify_policy(
        policy,
        store=store,
        season=season,
        cutoff=as_of,
        production=True,
    )
    return registry, policy, artifact_id


def _interval(
    row: dict[str, object],
    *,
    label: str,
) -> tuple[Fraction, Fraction] | None:
    lower = row.get("interval_lower")
    upper = row.get("interval_upper")
    if lower is None and upper is None:
        return None
    if lower is None or upper is None:
        raise ValueError(f"{label} interval must provide both bounds")
    low = _exact(lower, label=f"{label} interval lower")
    high = _exact(upper, label=f"{label} interval upper")
    if low > high:
        raise ValueError(f"{label} interval lower exceeds upper")
    return low, high


def _expected_interval_superiority(
    rule: MetricPromotionRule,
    candidate: dict[str, object],
    incumbent: dict[str, object],
) -> bool | None:
    if not rule.require_interval_superiority:
        return None
    candidate_interval = _interval(candidate, label="candidate metric")
    incumbent_interval = _interval(incumbent, label="incumbent metric")
    if candidate_interval is None or incumbent_interval is None:
        return None
    c_low, c_high = candidate_interval
    i_low, i_high = incumbent_interval
    if rule.direction.value == "LOWER_IS_BETTER":
        return c_high < i_low
    if rule.direction.value == "HIGHER_IS_BETTER":
        return c_low > i_high
    if rule.direction.value == "CLOSER_TO_ZERO":
        candidate_max_abs = max(abs(c_low), abs(c_high))
        incumbent_min_abs = Fraction(0, 1) if i_low <= 0 <= i_high else min(abs(i_low), abs(i_high))
        return candidate_max_abs < incumbent_min_abs
    raise ValueError("forecast promotion rule has unknown direction")


def _expected_improvement(
    direction: str,
    candidate: Fraction,
    incumbent: Fraction,
) -> Fraction:
    if direction == "LOWER_IS_BETTER":
        return incumbent - candidate
    if direction == "HIGHER_IS_BETTER":
        return candidate - incumbent
    if direction == "CLOSER_TO_ZERO":
        return abs(incumbent) - abs(candidate)
    raise ValueError("forecast comparison has unknown direction")


def _require_complete_production_report(
    stored: StoredLearningObject,
    *,
    expected_model_id: str,
    expected_policy_id: str,
    label: str,
) -> dict[tuple[str, str, str], dict[str, object]]:
    payload = stored.payload
    if payload.get("schema_name") != "apex-model-evaluation-report":
        raise ValueError(f"{label} has wrong schema")
    if payload.get("candidate_model_id") != expected_model_id:
        raise ValueError(f"{label} model identity mismatch")
    if payload.get("policy_id") != expected_policy_id:
        raise ValueError(f"{label} policy identity mismatch")
    if payload.get("use_mode") != "PRODUCTION":
        raise ValueError(f"{label} is not PRODUCTION mode")
    if payload.get("status") != "COMPLETE" or payload.get("blockers") != []:
        raise ValueError(f"{label} is not COMPLETE")
    _source_ids(stored, label=label)
    return _row_map(payload.get("metrics"), label=f"{label} metrics")


def verify_model_promotion_replay(
    promotion_artifact_id: str,
    *,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> StoredLearningObject:
    """Re-derive one retained forecast promotion certificate at authorization time."""

    promotion = load_learning_object(
        promotion_artifact_id,
        store=store,
        expected_object_type="MODEL_PROMOTION_CERTIFICATE",
    )
    payload = promotion.payload
    if payload.get("schema_name") != "apex-model-promotion-certificate":
        raise ValueError("forecast promotion certificate has wrong schema")
    sources = _source_ids(promotion, label="forecast promotion certificate")
    candidate_model_id = str(payload.get("candidate_model_id") or "")
    incumbent_model_id = str(payload.get("incumbent_model_id") or "")
    candidate_evaluation_id = str(payload.get("candidate_evaluation_id") or "")
    incumbent_evaluation_id = str(payload.get("incumbent_evaluation_id") or "")
    comparison_id = str(payload.get("comparison_id") or "")
    policy_id = str(payload.get("policy_id") or "")
    if not all(
        (
            candidate_model_id,
            incumbent_model_id,
            candidate_evaluation_id,
            incumbent_evaluation_id,
            comparison_id,
            policy_id,
        )
    ):
        raise ValueError("forecast promotion certificate identities are incomplete")

    candidate = _find_learning_source(
        sources,
        object_type="MODEL_EVALUATION_REPORT",
        semantic_id=candidate_evaluation_id,
        store=store,
        label="forecast candidate evaluation",
    )
    incumbent = _find_learning_source(
        sources,
        object_type="MODEL_EVALUATION_REPORT",
        semantic_id=incumbent_evaluation_id,
        store=store,
        label="forecast incumbent evaluation",
    )
    comparison = _find_learning_source(
        sources,
        object_type="MODEL_COMPARISON_REPORT",
        semantic_id=comparison_id,
        store=store,
        label="forecast model comparison",
    )
    _, policy, policy_registry_artifact_id = _policy_authority(
        sources,
        policy_id=policy_id,
        season=season,
        as_of=as_of,
        store=store,
    )

    candidate_metrics = _require_complete_production_report(
        candidate,
        expected_model_id=candidate_model_id,
        expected_policy_id=policy_id,
        label="forecast candidate evaluation",
    )
    incumbent_metrics = _require_complete_production_report(
        incumbent,
        expected_model_id=incumbent_model_id,
        expected_policy_id=policy_id,
        label="forecast incumbent evaluation",
    )
    candidate_payload = candidate.payload
    incumbent_payload = incumbent.payload
    truth_fields = (
        "evaluation_truth_set_id",
        "evaluation_realized_truth_set_id",
    )
    for field in truth_fields:
        if candidate_payload.get(field) != incumbent_payload.get(field):
            raise ValueError("forecast promotion evaluations do not share exact truth")

    comparison_payload = comparison.payload
    if comparison_payload.get("schema_name") != "apex-model-comparison-report":
        raise ValueError("forecast comparison has wrong schema")
    if comparison_payload.get("candidate_model_id") != candidate_model_id:
        raise ValueError("forecast comparison candidate model mismatch")
    if comparison_payload.get("incumbent_model_id") != incumbent_model_id:
        raise ValueError("forecast comparison incumbent model mismatch")
    if comparison_payload.get("candidate_evaluation_id") != candidate_evaluation_id:
        raise ValueError("forecast comparison candidate evaluation mismatch")
    if comparison_payload.get("incumbent_evaluation_id") != incumbent_evaluation_id:
        raise ValueError("forecast comparison incumbent evaluation mismatch")
    if comparison_payload.get("policy_id") != policy_id:
        raise ValueError("forecast comparison policy mismatch")
    if comparison_payload.get("use_mode") != "PRODUCTION":
        raise ValueError("forecast comparison is not PRODUCTION mode")
    if comparison_payload.get("status") != "COMPLETE" or comparison_payload.get("blockers") != []:
        raise ValueError("forecast comparison is not COMPLETE")
    for field in truth_fields:
        if comparison_payload.get(field) != candidate_payload.get(field):
            raise ValueError("forecast comparison truth identity mismatch")
    comparison_sources = _source_ids(comparison, label="forecast model comparison")
    required_comparison_sources = {
        candidate.artifact_id,
        incumbent.artifact_id,
        policy_registry_artifact_id,
    }
    if not required_comparison_sources.issubset(set(comparison_sources)):
        raise ValueError("forecast comparison is missing exact retained source artifacts")

    comparison_rows = _row_map(
        comparison_payload.get("comparisons"),
        label="forecast comparison rows",
    )
    rule_keys = {
        (rule.metric.value, rule.target.value, rule.cohort)
        for rule in policy.promotion_rules
    }
    if set(comparison_rows) != rule_keys:
        raise ValueError("forecast comparison rows do not equal predeclared promotion rules")

    failed: list[str] = []
    inconclusive: list[str] = []
    for rule in policy.promotion_rules:
        key = (rule.metric.value, rule.target.value, rule.cohort)
        candidate_row = candidate_metrics.get(key)
        incumbent_row = incumbent_metrics.get(key)
        comparison_row = comparison_rows[key]
        if candidate_row is None or incumbent_row is None:
            raise ValueError("forecast evaluation lacks metric required by promotion rule")
        if candidate_row.get("direction") != rule.direction.value:
            raise ValueError("forecast candidate metric direction mismatch")
        if incumbent_row.get("direction") != rule.direction.value:
            raise ValueError("forecast incumbent metric direction mismatch")
        if comparison_row.get("direction") != rule.direction.value:
            raise ValueError("forecast comparison metric direction mismatch")

        candidate_value = _exact(candidate_row.get("value"), label="candidate metric value")
        incumbent_value = _exact(incumbent_row.get("value"), label="incumbent metric value")
        if _exact(comparison_row.get("candidate_value"), label="comparison candidate value") != candidate_value:
            raise ValueError("forecast comparison candidate value disagrees with evaluation")
        if _exact(comparison_row.get("incumbent_value"), label="comparison incumbent value") != incumbent_value:
            raise ValueError("forecast comparison incumbent value disagrees with evaluation")
        candidate_count = _strict_int(
            candidate_row.get("sample_count"),
            label="candidate sample count",
        )
        incumbent_count = _strict_int(
            incumbent_row.get("sample_count"),
            label="incumbent sample count",
        )
        if comparison_row.get("candidate_sample_count") != candidate_count:
            raise ValueError("forecast comparison candidate sample count mismatch")
        if comparison_row.get("incumbent_sample_count") != incumbent_count:
            raise ValueError("forecast comparison incumbent sample count mismatch")

        improvement = _expected_improvement(
            rule.direction.value,
            candidate_value,
            incumbent_value,
        )
        if _exact(comparison_row.get("improvement"), label="comparison improvement") != improvement:
            raise ValueError("forecast comparison improvement does not re-derive")
        interval_superiority = _expected_interval_superiority(
            rule,
            candidate_row,
            incumbent_row,
        )
        if comparison_row.get("interval_superiority") != interval_superiority:
            raise ValueError("forecast comparison interval superiority does not re-derive")
        if improvement < rule.minimum_improvement.as_fraction():
            failed.append(
                f"{rule.metric.value}/{rule.target.value}/{rule.cohort} improvement below threshold"
            )
        if rule.require_interval_superiority:
            if interval_superiority is None:
                inconclusive.append(
                    f"{rule.metric.value}/{rule.target.value}/{rule.cohort} interval evidence missing"
                )
            elif interval_superiority is False:
                failed.append(
                    f"{rule.metric.value}/{rule.target.value}/{rule.cohort} interval superiority failed"
                )

    if inconclusive:
        expected_decision = ModelPromotionDecision.INCONCLUSIVE
        expected_reason = "; ".join(inconclusive + failed)
    elif failed:
        expected_decision = ModelPromotionDecision.RETAIN
        expected_reason = "; ".join(failed)
    else:
        expected_decision = ModelPromotionDecision.PROMOTE
        expected_reason = "all predeclared promotion rules passed"
    if payload.get("decision") != expected_decision.value:
        raise ValueError("forecast promotion decision does not re-derive from retained evidence")
    if payload.get("reason") != expected_reason:
        raise ValueError("forecast promotion reason does not re-derive from retained evidence")
    if expected_decision is not ModelPromotionDecision.PROMOTE:
        raise ValueError("forecast champion evidence does not re-derive PROMOTE")

    required_promotion_sources = {
        candidate.artifact_id,
        incumbent.artifact_id,
        comparison.artifact_id,
        policy_registry_artifact_id,
    }
    if policy.qualification_artifact_id is not None:
        required_promotion_sources.add(policy.qualification_artifact_id)
    if policy.promotion_rule_artifact_id is not None:
        required_promotion_sources.add(policy.promotion_rule_artifact_id)
    if not required_promotion_sources.issubset(set(sources)):
        raise ValueError("forecast promotion certificate is missing exact retained authority sources")
    return promotion
