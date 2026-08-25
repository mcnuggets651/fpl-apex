"""Dependency-free content contracts for exact V2 production decision lineage.

Schema v1 retains the certified tactical bundle for historical/mechanism replay. Schema
v2 is the production receding-horizon contract: it additionally binds retained current
ManagerState truth, the exact RuleSet, and the replay-derived PlanningResult that selected
the user-facing action. Production authority must migrate explicitly to v2 rather than
silently widening v1 semantics.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256
from .ids import (
    BundleId,
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    DecisionPolicyId,
    ForecastId,
    GlobalWorldId,
    ManagerStateId,
    ModelArtifactId,
    PlanningResultId,
    RobustnessReportId,
    RuleSetId,
    ScenarioSetId,
)


def _sha256_id(value: object, *, label: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ProductionDecisionBundle:
    """Certified v1 tactical replay surface retained for historical/mechanism evidence."""

    season: str
    entry: int
    gameweek: int
    world_id: GlobalWorldId
    forecast_id: ForecastId
    forecast_artifact_id: str
    forecast_model_id: ModelArtifactId
    decision_policy_id: DecisionPolicyId
    candidate_universe_id: CandidateUniverseId
    candidate_universe_artifact_id: str
    decision_input_id: DecisionInputId
    decision_id: DecisionId
    decision_result_artifact_id: str
    scenario_set_id: ScenarioSetId
    scenario_set_artifact_id: str
    robustness_report_id: RobustnessReportId
    robustness_report_artifact_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProductionDecisionBundle schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("production decision bundle requires season")
        _positive_int(self.entry, label="production decision bundle entry")
        _positive_int(self.gameweek, label="production decision bundle gameweek")
        typed_ids = (
            (self.world_id, "production bundle world_id"),
            (self.forecast_id, "production bundle forecast_id"),
            (self.forecast_model_id, "production bundle forecast_model_id"),
            (self.decision_policy_id, "production bundle decision_policy_id"),
            (self.candidate_universe_id, "production bundle candidate_universe_id"),
            (self.decision_input_id, "production bundle decision_input_id"),
            (self.decision_id, "production bundle decision_id"),
            (self.scenario_set_id, "production bundle scenario_set_id"),
            (self.robustness_report_id, "production bundle robustness_report_id"),
        )
        for value, label in typed_ids:
            _sha256_id(value, label=label)
        artifact_fields = (
            "forecast_artifact_id",
            "candidate_universe_artifact_id",
            "decision_result_artifact_id",
            "scenario_set_artifact_id",
            "robustness_report_artifact_id",
        )
        for field in artifact_fields:
            normalized = _sha256_id(getattr(self, field), label=f"production bundle {field}")
            object.__setattr__(self, field, normalized)
        object.__setattr__(self, "season", season)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-decision-bundle",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry": self.entry,
            "gameweek": self.gameweek,
            "world_id": str(self.world_id),
            "forecast_id": str(self.forecast_id),
            "forecast_artifact_id": self.forecast_artifact_id,
            "forecast_model_id": str(self.forecast_model_id),
            "decision_policy_id": str(self.decision_policy_id),
            "candidate_universe_id": str(self.candidate_universe_id),
            "candidate_universe_artifact_id": self.candidate_universe_artifact_id,
            "decision_input_id": str(self.decision_input_id),
            "decision_id": str(self.decision_id),
            "decision_result_artifact_id": self.decision_result_artifact_id,
            "scenario_set_id": str(self.scenario_set_id),
            "scenario_set_artifact_id": self.scenario_set_artifact_id,
            "robustness_report_id": str(self.robustness_report_id),
            "robustness_report_artifact_id": self.robustness_report_artifact_id,
        }

    @property
    def bundle_id(self) -> BundleId:
        return BundleId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class ProductionPlanningBundle:
    """Schema-v2 production lineage for one receding-horizon decision."""

    season: str
    entry: int
    gameweek: int
    world_id: GlobalWorldId
    manager_state_id: ManagerStateId
    manager_state_artifact_id: str
    ruleset_id: RuleSetId
    ruleset_artifact_id: str
    forecast_id: ForecastId
    forecast_artifact_id: str
    forecast_model_id: ModelArtifactId
    decision_policy_id: DecisionPolicyId
    candidate_universe_id: CandidateUniverseId
    candidate_universe_artifact_id: str
    decision_input_id: DecisionInputId
    decision_id: DecisionId
    planning_result_id: PlanningResultId
    planning_result_artifact_id: str
    scenario_set_id: ScenarioSetId
    scenario_set_artifact_id: str
    robustness_report_id: RobustnessReportId
    robustness_report_artifact_id: str
    schema_version: int = 2

    def __post_init__(self) -> None:
        if self.schema_version != 2:
            raise ValueError("unsupported ProductionPlanningBundle schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("production planning bundle requires season")
        _positive_int(self.entry, label="production planning bundle entry")
        _positive_int(self.gameweek, label="production planning bundle gameweek")
        typed_ids = (
            (self.world_id, "production planning bundle world_id"),
            (self.manager_state_id, "production planning bundle manager_state_id"),
            (self.ruleset_id, "production planning bundle ruleset_id"),
            (self.forecast_id, "production planning bundle forecast_id"),
            (self.forecast_model_id, "production planning bundle forecast_model_id"),
            (self.decision_policy_id, "production planning bundle decision_policy_id"),
            (self.candidate_universe_id, "production planning bundle candidate_universe_id"),
            (self.decision_input_id, "production planning bundle decision_input_id"),
            (self.decision_id, "production planning bundle decision_id"),
            (self.planning_result_id, "production planning bundle planning_result_id"),
            (self.scenario_set_id, "production planning bundle scenario_set_id"),
            (self.robustness_report_id, "production planning bundle robustness_report_id"),
        )
        for value, label in typed_ids:
            _sha256_id(value, label=label)
        if str(self.decision_id) != str(self.planning_result_id):
            raise ValueError("production planning DecisionId must equal PlanningResultId")
        artifact_fields = (
            "manager_state_artifact_id",
            "ruleset_artifact_id",
            "forecast_artifact_id",
            "candidate_universe_artifact_id",
            "planning_result_artifact_id",
            "scenario_set_artifact_id",
            "robustness_report_artifact_id",
        )
        for field in artifact_fields:
            normalized = _sha256_id(
                getattr(self, field),
                label=f"production planning bundle {field}",
            )
            object.__setattr__(self, field, normalized)
        if self.manager_state_artifact_id != str(self.manager_state_id):
            raise ValueError("production planning ManagerState artifact must be self-addressing")
        if self.ruleset_artifact_id != str(self.ruleset_id):
            raise ValueError("production planning RuleSet artifact must be self-addressing")
        if self.planning_result_artifact_id != str(self.planning_result_id):
            raise ValueError("production planning result artifact must be self-addressing")
        object.__setattr__(self, "season", season)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-decision-bundle",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry": self.entry,
            "gameweek": self.gameweek,
            "world_id": str(self.world_id),
            "manager_state_id": str(self.manager_state_id),
            "manager_state_artifact_id": self.manager_state_artifact_id,
            "ruleset_id": str(self.ruleset_id),
            "ruleset_artifact_id": self.ruleset_artifact_id,
            "forecast_id": str(self.forecast_id),
            "forecast_artifact_id": self.forecast_artifact_id,
            "forecast_model_id": str(self.forecast_model_id),
            "decision_policy_id": str(self.decision_policy_id),
            "candidate_universe_id": str(self.candidate_universe_id),
            "candidate_universe_artifact_id": self.candidate_universe_artifact_id,
            "decision_input_id": str(self.decision_input_id),
            "decision_id": str(self.decision_id),
            "planning_result_id": str(self.planning_result_id),
            "planning_result_artifact_id": self.planning_result_artifact_id,
            "scenario_set_id": str(self.scenario_set_id),
            "scenario_set_artifact_id": self.scenario_set_artifact_id,
            "robustness_report_id": str(self.robustness_report_id),
            "robustness_report_artifact_id": self.robustness_report_artifact_id,
        }

    @property
    def bundle_id(self) -> BundleId:
        return BundleId(canonical_sha256(self.semantic_payload()))
