"""Admission and replay registry for Apex V2 offline learning policies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.empirical_qualification_admission import (
    verify_typed_empirical_qualification,
)
from apex_fpl.core.ids import LearningPolicyId
from apex_fpl.core.learning_common import (
    EvaluationMetric,
    ExactMetricValue,
    LearningPolicyQualification,
    MetricDirection,
    instant,
)
from apex_fpl.core.learning_policy import (
    LearningEvaluationPolicy,
    MetricPromotionRule,
    MetricRequirement,
)
from apex_fpl.core.outcome_truth import OutcomeTarget


@dataclass(frozen=True, slots=True)
class LearningPolicyRegistry:
    season: str
    policies: tuple[LearningEvaluationPolicy, ...]
    champion_policy_id: LearningPolicyId | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported LearningPolicyRegistry schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("learning policy registry requires season")
        policies = tuple(sorted(self.policies, key=lambda row: str(row.policy_id)))
        ids = [row.policy_id for row in policies]
        if len(ids) != len(set(ids)):
            raise ValueError("learning policy registry contains duplicate policy identities")
        if any(season not in row.valid_seasons for row in policies):
            raise ValueError("learning policy registry contains policy outside registry season")
        if self.champion_policy_id is not None:
            champion = next((row for row in policies if row.policy_id == self.champion_policy_id), None)
            if champion is None:
                raise ValueError("learning champion policy is not registered")
            if not champion.production_qualified:
                raise ValueError("learning champion policy must be production qualified")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "policies", policies)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-learning-policy-registry",
            "schema_version": self.schema_version,
            "season": self.season,
            "champion_policy_id": None if self.champion_policy_id is None else str(self.champion_policy_id),
            "policies": [row.semantic_payload() for row in self.policies],
        }

    def get(self, policy_id: LearningPolicyId) -> LearningEvaluationPolicy | None:
        return next((row for row in self.policies if row.policy_id == policy_id), None)

    def champion(self) -> LearningEvaluationPolicy | None:
        if self.champion_policy_id is None:
            return None
        return self.get(self.champion_policy_id)

    def verify_policy(
        self,
        policy: LearningEvaluationPolicy,
        *,
        store: ArtifactStore,
        season: str,
        cutoff: str,
        production: bool,
    ) -> None:
        registered = self.get(policy.policy_id)
        if registered is None or registered.semantic_payload() != policy.semantic_payload():
            raise ValueError("learning policy is not registered under exact semantic identity")
        if season != self.season or season not in policy.valid_seasons:
            raise ValueError("learning policy is not valid for requested season")
        if instant(policy.first_available_at) > instant(cutoff):
            raise ValueError("learning policy was not available at evaluation cutoff")
        for artifact_id in (policy.qualification_artifact_id, policy.promotion_rule_artifact_id):
            if artifact_id is not None and not store.verify(artifact_id):
                raise ValueError("learning policy qualification/rule artifact is missing or corrupt")
        if policy.qualification_state is LearningPolicyQualification.SUSPENDED:
            raise ValueError("learning policy is suspended")
        if production:
            if not policy.production_qualified:
                raise ValueError("production learning requires qualified policy")
            if self.champion_policy_id != policy.policy_id:
                raise ValueError("production learning policy is not registered champion")
            verify_typed_empirical_qualification(
                qualification_artifact_id=policy.qualification_artifact_id,
                subject_payload=policy.semantic_payload(),
                subject_kind="apex.learning-policy",
                proof_id="PO-MODEL-EVALUATION-001",
                season=season,
                as_of=cutoff,
                store=store,
            )


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _strict_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _rows(value: object, *, label: str) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def _metric_value(value: object, *, label: str) -> ExactMetricValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    return ExactMetricValue(
        _strict_int(value.get("numerator"), label=f"{label} numerator"),
        _strict_int(value.get("denominator"), label=f"{label} denominator"),
    )


def _registry_from_raw(payload: object) -> LearningPolicyRegistry:
    if not isinstance(payload, dict) or _strict_int(payload.get("schema_version"), label="schema_version") != 1:
        raise ValueError("learning policy registry requires schema_version 1")
    season = str(payload.get("season") or "").strip()
    if not season:
        raise ValueError("learning policy registry requires season")
    policies: list[LearningEvaluationPolicy] = []
    for row in _rows(payload.get("policies"), label="learning policies"):
        requirements = tuple(
            MetricRequirement(
                metric=EvaluationMetric(str(item.get("metric") or "")),
                target=OutcomeTarget(str(item.get("target") or "")),
                cohort=str(item.get("cohort") or ""),
                minimum_cases=_strict_int(item.get("minimum_cases"), label="minimum_cases"),
                require_interval=_strict_bool(item.get("require_interval", False), label="require_interval"),
            )
            for item in _rows(row.get("requirements"), label="metric requirements")
        )
        rules = tuple(
            MetricPromotionRule(
                metric=EvaluationMetric(str(item.get("metric") or "")),
                target=OutcomeTarget(str(item.get("target") or "")),
                cohort=str(item.get("cohort") or ""),
                direction=MetricDirection(str(item.get("direction") or "")),
                minimum_improvement=_metric_value(item.get("minimum_improvement"), label="minimum_improvement"),
                require_interval_superiority=_strict_bool(
                    item.get("require_interval_superiority", False),
                    label="require_interval_superiority",
                ),
            )
            for item in _rows(row.get("promotion_rules"), label="promotion rules")
        )
        policies.append(
            LearningEvaluationPolicy(
                policy_name=str(row.get("policy_name") or ""),
                policy_version=str(row.get("policy_version") or ""),
                qualification_state=LearningPolicyQualification(str(row.get("qualification_state") or "")),
                qualification_artifact_id=(None if row.get("qualification_artifact_id") is None else str(row.get("qualification_artifact_id"))),
                promotion_rule_artifact_id=(None if row.get("promotion_rule_artifact_id") is None else str(row.get("promotion_rule_artifact_id"))),
                first_available_at=str(row.get("first_available_at") or ""),
                valid_seasons=tuple(str(item) for item in (row.get("valid_seasons") or [])),
                requirements=requirements,
                promotion_rules=rules,
            )
        )
    champion_raw = payload.get("champion_policy_id")
    return LearningPolicyRegistry(
        season=season,
        policies=tuple(policies),
        champion_policy_id=None if champion_raw is None else LearningPolicyId(str(champion_raw)),
    )


def load_learning_policy_registry_bytes(content: bytes) -> LearningPolicyRegistry:
    if not isinstance(content, bytes):
        raise TypeError("learning policy registry content must be bytes")
    try:
        payload = yaml.safe_load(content.decode("utf-8")) or {}
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("learning policy registry is not valid UTF-8 YAML") from exc
    return _registry_from_raw(payload)


def load_learning_policy_registry(path: str | Path) -> LearningPolicyRegistry:
    return load_learning_policy_registry_bytes(Path(path).read_bytes())
