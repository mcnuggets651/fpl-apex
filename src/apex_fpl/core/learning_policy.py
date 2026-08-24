"""Qualified evaluation and promotion policy contracts for Apex V2 Slice 11."""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .ids import LearningPolicyId
from .learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningPolicyQualification,
    MetricDirection,
    artifact_id,
    aware_iso,
    positive_int,
)
from .outcome_truth import OutcomeTarget


def _metric_target_allowed(metric: EvaluationMetric, target: OutcomeTarget) -> bool:
    fixed = {
        EvaluationMetric.START_BRIER: OutcomeTarget.START,
        EvaluationMetric.MINUTES_MAE: OutcomeTarget.MINUTES,
        EvaluationMetric.MINUTES_MSE: OutcomeTarget.MINUTES,
        EvaluationMetric.POINTS_MAE: OutcomeTarget.FPL_POINTS,
        EvaluationMetric.POINTS_MEAN_BIAS: OutcomeTarget.FPL_POINTS,
        EvaluationMetric.DECISION_REALIZED_POINTS_DELTA: OutcomeTarget.FPL_POINTS,
    }
    expected = fixed.get(metric)
    return expected is None or target is expected


@dataclass(frozen=True, slots=True)
class MetricRequirement:
    metric: EvaluationMetric
    target: OutcomeTarget
    cohort: str
    minimum_cases: int
    require_interval: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.metric, EvaluationMetric) or not isinstance(self.target, OutcomeTarget):
            raise ValueError("metric requirement requires typed metric and target")
        if not _metric_target_allowed(self.metric, self.target):
            raise ValueError(f"{self.metric.value} cannot evaluate target {self.target.value}")
        cohort = str(self.cohort).strip()
        if not cohort:
            raise ValueError("metric requirement cohort cannot be empty")
        positive_int(self.minimum_cases, label="metric requirement minimum_cases")
        if not isinstance(self.require_interval, bool):
            raise ValueError("metric requirement require_interval must be boolean")
        if self.metric is EvaluationMetric.INTERVAL_COVERAGE and not self.require_interval:
            raise ValueError("INTERVAL_COVERAGE requires interval observations")
        object.__setattr__(self, "cohort", cohort)

    @property
    def key(self) -> tuple[EvaluationMetric, OutcomeTarget, str]:
        return self.metric, self.target, self.cohort

    def semantic_payload(self) -> dict[str, object]:
        return {
            "metric": self.metric.value,
            "target": self.target.value,
            "cohort": self.cohort,
            "minimum_cases": self.minimum_cases,
            "require_interval": self.require_interval,
        }


@dataclass(frozen=True, slots=True)
class MetricPromotionRule:
    metric: EvaluationMetric
    target: OutcomeTarget
    cohort: str
    direction: MetricDirection
    minimum_improvement: ExactMetricValue
    require_interval_superiority: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.metric, EvaluationMetric) or not isinstance(self.target, OutcomeTarget):
            raise ValueError("promotion rule requires typed metric and target")
        if not _metric_target_allowed(self.metric, self.target):
            raise ValueError(f"{self.metric.value} cannot govern target {self.target.value}")
        if not isinstance(self.direction, MetricDirection):
            raise ValueError("promotion rule direction must be typed")
        if not isinstance(self.minimum_improvement, ExactMetricValue):
            raise ValueError("promotion minimum improvement must be ExactMetricValue")
        cohort = str(self.cohort).strip()
        if not cohort:
            raise ValueError("promotion rule cohort cannot be empty")
        if self.minimum_improvement.numerator < 0:
            raise ValueError("promotion minimum improvement cannot be negative")
        if not isinstance(self.require_interval_superiority, bool):
            raise ValueError("promotion interval-superiority flag must be boolean")
        object.__setattr__(self, "cohort", cohort)

    @property
    def key(self) -> tuple[EvaluationMetric, OutcomeTarget, str]:
        return self.metric, self.target, self.cohort

    def semantic_payload(self) -> dict[str, object]:
        return {
            "metric": self.metric.value,
            "target": self.target.value,
            "cohort": self.cohort,
            "direction": self.direction.value,
            "minimum_improvement": self.minimum_improvement.semantic_payload(),
            "require_interval_superiority": self.require_interval_superiority,
        }


@dataclass(frozen=True, slots=True)
class LearningEvaluationPolicy:
    policy_name: str
    policy_version: str
    qualification_state: LearningPolicyQualification
    qualification_artifact_id: str | None
    promotion_rule_artifact_id: str | None
    first_available_at: str
    valid_seasons: tuple[str, ...]
    requirements: tuple[MetricRequirement, ...]
    promotion_rules: tuple[MetricPromotionRule, ...]
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported LearningEvaluationPolicy schema_version")
        for label in ("policy_name", "policy_version"):
            text = str(getattr(self, label)).strip()
            if not text:
                raise ValueError(f"learning policy {label} cannot be empty")
            object.__setattr__(self, label, text)
        if not isinstance(self.qualification_state, LearningPolicyQualification):
            raise ValueError("learning policy qualification must be typed")
        if any(not isinstance(row, MetricRequirement) for row in self.requirements):
            raise ValueError("learning policy requirements must be typed MetricRequirement rows")
        if any(not isinstance(row, MetricPromotionRule) for row in self.promotion_rules):
            raise ValueError("learning policy promotion rules must be typed MetricPromotionRule rows")
        available = aware_iso(self.first_available_at, label="learning policy first_available_at")
        seasons = tuple(sorted({str(item).strip() for item in self.valid_seasons if str(item).strip()}))
        if not seasons:
            raise ValueError("learning policy requires at least one valid season")
        requirements = tuple(
            sorted(self.requirements, key=lambda row: (row.metric.value, row.target.value, row.cohort))
        )
        rules = tuple(
            sorted(self.promotion_rules, key=lambda row: (row.metric.value, row.target.value, row.cohort))
        )
        if not requirements:
            raise ValueError("learning policy requires at least one metric requirement")
        if len({row.key for row in requirements}) != len(requirements):
            raise ValueError("learning policy contains duplicate metric requirements")
        if len({row.key for row in rules}) != len(rules):
            raise ValueError("learning policy contains duplicate promotion rules")
        qualification = self.qualification_artifact_id
        if qualification is not None:
            qualification = artifact_id(qualification, label="learning policy qualification artifact")
        rule_artifact = self.promotion_rule_artifact_id
        if rule_artifact is not None:
            rule_artifact = artifact_id(rule_artifact, label="learning promotion rule artifact")
        if self.qualification_state is LearningPolicyQualification.QUALIFIED:
            if qualification is None or rule_artifact is None:
                raise ValueError("qualified learning policy requires qualification and promotion-rule artifacts")
            requirement_keys = {row.key for row in requirements}
            if {row.key for row in rules} != requirement_keys:
                raise ValueError("qualified learning policy requires one promotion rule per metric requirement")
        object.__setattr__(self, "first_available_at", available)
        object.__setattr__(self, "valid_seasons", seasons)
        object.__setattr__(self, "requirements", requirements)
        object.__setattr__(self, "promotion_rules", rules)
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "promotion_rule_artifact_id", rule_artifact)

    @property
    def production_qualified(self) -> bool:
        return (
            self.qualification_state is LearningPolicyQualification.QUALIFIED
            and self.qualification_artifact_id is not None
            and self.promotion_rule_artifact_id is not None
            and len(self.requirements) == len(self.promotion_rules)
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-learning-evaluation-policy",
            "schema_version": self.schema_version,
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "qualification_state": self.qualification_state.value,
            "qualification_artifact_id": self.qualification_artifact_id,
            "promotion_rule_artifact_id": self.promotion_rule_artifact_id,
            "first_available_at": self.first_available_at,
            "valid_seasons": list(self.valid_seasons),
            "requirements": [row.semantic_payload() for row in self.requirements],
            "promotion_rules": [row.semantic_payload() for row in self.promotion_rules],
        }

    @property
    def policy_id(self) -> LearningPolicyId:
        return LearningPolicyId(canonical_sha256(self.semantic_payload()))
