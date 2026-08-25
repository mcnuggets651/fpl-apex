"""Dependency-free content contract for the exact V2 production decision lineage.

A production release cannot authorize an opaque caller-supplied bundle label.  The bundle
identity commits to the exact forecast/model, DecisionPolicy, CandidateUniverse,
DecisionResult and converged robustness artifacts that produced the user-facing action.
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
    ModelArtifactId,
    RobustnessReportId,
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


@dataclass(frozen=True, slots=True)
class ProductionDecisionBundle:
    """Exact replay surface for one production decision and its direct empirical lineage."""

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
        if isinstance(self.entry, bool) or not isinstance(self.entry, int) or self.entry <= 0:
            raise ValueError("production decision bundle entry must be positive integer")
        if (
            isinstance(self.gameweek, bool)
            or not isinstance(self.gameweek, int)
            or self.gameweek <= 0
        ):
            raise ValueError("production decision bundle gameweek must be positive integer")
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
