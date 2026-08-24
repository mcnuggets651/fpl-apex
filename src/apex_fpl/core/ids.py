"""Typed execution and semantic identifiers for Apex V2."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True)
class ApexId:
    """Base value object. Subclasses are intentionally not interchangeable by type."""

    value: str
    kind: ClassVar[str] = "id"

    def __post_init__(self) -> None:
        text = str(self.value).strip()
        if not text:
            raise ValueError(f"{self.kind} cannot be empty")
        if any(char.isspace() for char in text):
            raise ValueError(f"{self.kind} cannot contain whitespace")
        object.__setattr__(self, "value", text)

    def __str__(self) -> str:
        return self.value


class RunId(ApexId):
    kind = "run_id"


class RawCaptureId(ApexId):
    kind = "raw_capture_id"


class GlobalWorldId(ApexId):
    kind = "global_world_id"


class PersonId(ApexId):
    kind = "person_id"


class RuleSetId(ApexId):
    kind = "ruleset_id"


class ManagerPublicSnapshotId(ApexId):
    kind = "manager_public_snapshot_id"


class InitialManagerBasisId(ApexId):
    kind = "initial_manager_basis_id"


class ManagerStateId(ApexId):
    kind = "manager_state_id"


class FeatureSnapshotId(ApexId):
    kind = "feature_snapshot_id"


class ModelArtifactId(ApexId):
    kind = "model_artifact_id"


class TrainingRunId(ApexId):
    kind = "training_run_id"


class PredictionBatchId(ApexId):
    kind = "prediction_batch_id"


class CandidateUniverseId(ApexId):
    kind = "candidate_universe_id"


class DecisionWorldId(ApexId):
    kind = "decision_world_id"


class ForecastId(ApexId):
    kind = "forecast_id"


class ScenarioGeneratorId(ApexId):
    kind = "scenario_generator_id"


class ScenarioPolicyId(ApexId):
    kind = "scenario_policy_id"


class ScenarioSetId(ApexId):
    kind = "scenario_set_id"


class RobustnessReportId(ApexId):
    kind = "robustness_report_id"


class DecisionPolicyId(ApexId):
    kind = "decision_policy_id"


class DecisionInputId(ApexId):
    kind = "decision_input_id"


class DecisionId(ApexId):
    kind = "decision_id"


class ReferenceMechanicsCertificateId(ApexId):
    kind = "reference_mechanics_certificate_id"


class ReferenceSolverWorkerId(ApexId):
    kind = "reference_solver_worker_id"


class ReferenceSolverCertificateId(ApexId):
    kind = "reference_solver_certificate_id"


class IndependentAssuranceReportId(ApexId):
    kind = "independent_assurance_report_id"


class OutcomeTruthRegistryId(ApexId):
    kind = "outcome_truth_registry_id"


class LearningPolicyId(ApexId):
    kind = "learning_policy_id"


class EvaluationDatasetId(ApexId):
    kind = "evaluation_dataset_id"


class EvaluationTruthSetId(ApexId):
    kind = "evaluation_truth_set_id"


class EvaluationObservationSetId(ApexId):
    kind = "evaluation_observation_set_id"


class ModelEvaluationId(ApexId):
    kind = "model_evaluation_id"


class ModelComparisonId(ApexId):
    kind = "model_comparison_id"


class ModelPromotionId(ApexId):
    kind = "model_promotion_id"


class ModelRegistryGenerationId(ApexId):
    kind = "model_registry_generation_id"


class BundleId(ApexId):
    kind = "bundle_id"


class ReleaseId(ApexId):
    kind = "release_id"