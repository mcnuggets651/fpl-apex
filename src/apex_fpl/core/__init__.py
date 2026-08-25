"""Dependency-free constitutional core for Apex V2."""

from .assurance import (
    AssuranceParityStatus,
    IndependentAssuranceReport,
    ReferenceCheckResult,
    ReferenceMechanicsCertificate,
    ReferenceMechanicsCheck,
    ReferenceSolverCertificate,
    ReferenceSolverStatus,
)
from .canonical import canonical_json_bytes, canonical_sha256
from .decision import (
    DEFAULT_NUMERIC_POLICY_ID,
    CandidateExpansionCertificate,
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionAction,
    DecisionChip,
    DecisionInput,
    DecisionMechanics,
    DecisionObjectiveModel,
    DecisionResult,
    DecisionUseMode,
    ExactnessClaim,
    ExactnessStatus,
    ExpansionResult,
    RationalValue,
    SolverCertificate,
    SolverStatus,
    TransferMove,
)
from .decision_policy import (
    TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from .decision_search import DecisionSearchFailure, DecisionSearchOutcome
from .evidence import EvidenceClaim, EvidenceClaimType, EvidenceConflictState, EvidenceLedger, EvidencePolarity
from .features import FeatureObservation, FeatureScope, FeatureSnapshot, FeatureValue, FeatureValueKind
from .forecast import (
    DiscreteIntegerDistribution,
    Forecast,
    ForecastAbstention,
    ForecastModelArtifact,
    ForecastUncertainty,
    ForecastUseMode,
    ModelQualificationState,
    PlayerFixtureForecast,
    PlayerFixtureScenario,
    PlayerFixtureTarget,
    PlayerMatchOutcome,
    PredictionBatch,
    PredictionDisposition,
    PredictionRow,
    UncertaintyKind,
    compile_forecast,
    compile_prediction_row,
    score_match_outcome,
)
from .freshness import DeadlineFreshnessPolicy, FreshnessBand
from .identity import IdentityIntegrityError, IdentityRegistry, IdentityResolution, IdentityResolutionState, IdentityWitness, OfficialPlayerId, OfficialPlayerIdentity, PersonLink
from .ids import *
from .learning_common import EvaluationMetric, ExactMetricValue, LearningEvaluationStatus, LearningPolicyQualification, LearningUseMode, MetricDirection, ModelPromotionDecision
from .learning_dataset import EvaluationCase, EvaluationDataset
from .learning_evaluation import EvaluationMetricResult, MetricComparisonResult, ModelComparisonReport, ModelEvaluationReport
from .learning_observations import EvaluationObservation, EvaluationObservationSet
from .learning_policy import LearningEvaluationPolicy, MetricPromotionRule, MetricRequirement
from .learning_promotion import ModelPromotionCertificate, ModelRegistryGeneration
from .learning_training import ModelTrainingRun
from .manager_state import ChipUse, CurrentStateAttestation, ManagerState, ManagerStateIntegrityError, ManagerStateScope, OwnedPlayer, TransferLedgerEvent, TransferTransition, advance_deadline, apply_permanent_transfer, attest_deadline_snapshot_current, calculate_selling_price_tenths, owned_player_from_official, reprice_manager_state
from .minutes_features import MinutesFeatureVector, minutes_feature_vector
from .minutes_history import HistoricalMinutesSample, PreseasonAppearance, historical_minutes_observations, preseason_minutes_observations
from .outcome_truth import OutcomeTarget, OutcomeTruthAuthority, OutcomeTruthRegistry, TruthAuthorityStatus
from .proofs import AssuranceCase, AssuranceClaim, ProofClass, ProofObligation, ProofStatus, ReleaseCertificate, ReleasePolicy
from .reference_solver_worker import ReferenceSolverWorkerArtifact, ReferenceSolverWorkerQualification
from .reliability import ReliabilityContext, ReliabilityQualification
from .rules import OfficialRuleSource, RuleDefinition, RuleSet
from .scenarios import HISTORICAL_SCENARIO_FLOOR, ActionRobustnessMetrics, JointPlayerGameweekOutcome, JointScenario, RobustnessReport, ScenarioConvergenceCheckpoint, ScenarioConvergencePolicy, ScenarioConvergenceStatus, ScenarioGeneratorArtifact, ScenarioQualificationState, ScenarioSet
from .shadow import ShadowProductionReport, ShadowProductionStatus
from .sources import DegradationDecision, DegradationProfile, HealthState, SourceAdmissionState, SourceCapability, SourceCriticality, SourceHealth, evaluate_source_runtime
from .world import GlobalWorld, WorldSource

# This module intentionally re-exports the constitutional value types. Keep names explicit
# enough for downstream users while allowing typed IDs from core.ids to remain available.
__all__ = [name for name in globals() if not name.startswith("_")]
