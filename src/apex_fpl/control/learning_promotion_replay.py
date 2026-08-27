"""Replay verification for forecast-model champion authority.

Production champion authority must not trust a caller-authored ``COMPLETE`` evaluation,
``PROMOTE`` certificate or registry row.  This module reconstructs the retained learning
inputs, re-runs the canonical evaluator/comparison/promotion functions and replays each
parent-linked model-registry transition before a forecast champion can be accepted.
"""

from __future__ import annotations

from dataclasses import dataclass

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.learning_evaluator import evaluate_model
from apex_fpl.control.learning_policy_registry import (
    LearningPolicyRegistry,
    load_learning_policy_registry_bytes,
)
from apex_fpl.control.learning_promotion import (
    apply_model_promotion,
    compare_model_evaluations,
    issue_model_promotion_certificate,
)
from apex_fpl.control.learning_store import StoredLearningObject, load_learning_object
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry_bytes
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    EvaluationDatasetId,
    EvaluationObservationSetId,
    EvaluationTruthSetId,
    FeatureSnapshotId,
    ForecastId,
    LearningPolicyId,
    ModelArtifactId,
    ModelComparisonId,
    ModelEvaluationId,
    ModelPromotionId,
    ModelRegistryGenerationId,
    OutcomeTruthRegistryId,
)
from apex_fpl.core.learning_common import (
    ExactMetricValue,
    ModelPromotionDecision,
    instant,
)
from apex_fpl.core.learning_dataset import EvaluationCase, EvaluationDataset
from apex_fpl.core.learning_evaluation import ModelEvaluationReport
from apex_fpl.core.learning_observations import EvaluationObservation, EvaluationObservationSet
from apex_fpl.core.learning_policy import LearningEvaluationPolicy
from apex_fpl.core.learning_promotion import ModelPromotionCertificate, ModelRegistryGeneration
from apex_fpl.core.learning_training import ModelTrainingRun
from apex_fpl.core.outcome_truth import OutcomeTarget, OutcomeTruthRegistry


@dataclass(frozen=True, slots=True)
class VerifiedModelEvaluationReplay:
    stored: StoredLearningObject
    report: ModelEvaluationReport
    policy: LearningEvaluationPolicy
    policy_registry: LearningPolicyRegistry
    policy_registry_artifact_id: str


@dataclass(frozen=True, slots=True)
class VerifiedModelPromotionReplay:
    stored: StoredLearningObject
    certificate: ModelPromotionCertificate
    candidate: VerifiedModelEvaluationReplay
    incumbent: VerifiedModelEvaluationReplay
    comparison_artifact_id: str


@dataclass(frozen=True, slots=True)
class VerifiedForecastChampionEvidence:
    registry_generation_artifact_id: str
    registry_generation: ModelRegistryGeneration
    champion_model_id: str
    promotion_artifact_id: str
    promotion: VerifiedModelPromotionReplay



def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _string_list(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be string array")
    canonical = tuple(sorted(set(value)))
    if canonical != tuple(value):
        raise ValueError(f"{label} must be canonical sorted unique array")
    return canonical


def _metric_value(value: object, *, label: str) -> ExactMetricValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be exact-value object")
    return ExactMetricValue(
        _strict_int(value.get("numerator"), label=f"{label} numerator"),
        _strict_int(value.get("denominator"), label=f"{label} denominator"),
    )


def _optional_metric_value(value: object, *, label: str) -> ExactMetricValue | None:
    return None if value is None else _metric_value(value, label=label)


def _source_ids(stored: StoredLearningObject, *, label: str) -> tuple[str, ...]:
    payload_sources = _string_list(
        stored.payload.get("source_artifact_ids"),
        label=f"{label} payload source artifacts",
    )
    if payload_sources != stored.source_artifact_ids:
        raise ValueError(f"{label} envelope/payload source artifacts disagree")
    return payload_sources


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
            "forecast learning replay must find exactly one retained learning-policy registry"
        )
    registry, policy, artifact_id = matches[0]
    if registry.season != season:
        raise ValueError("forecast learning-policy registry season mismatch")
    registry.verify_policy(
        policy,
        store=store,
        season=season,
        cutoff=as_of,
        production=True,
    )
    return registry, policy, artifact_id


def _truth_authority(
    source_artifact_ids: tuple[str, ...],
    *,
    truth_registry_id: str,
    store: ArtifactStore,
) -> tuple[OutcomeTruthRegistry, str]:
    matches: list[tuple[OutcomeTruthRegistry, str]] = []
    for artifact_id in source_artifact_ids:
        try:
            registry = load_outcome_truth_registry_bytes(store.read_bytes(artifact_id))
        except (FileNotFoundError, TypeError, ValueError):
            continue
        if str(registry.truth_registry_id) == truth_registry_id:
            matches.append((registry, artifact_id))
    if len(matches) != 1:
        raise ValueError(
            "forecast evaluation replay must find exactly one retained outcome-truth registry"
        )
    return matches[0]


def _typed_training(stored: StoredLearningObject) -> ModelTrainingRun:
    payload = stored.payload
    if payload.get("schema_name") != "apex-model-training-run":
        raise ValueError("forecast training replay has wrong schema")
    value = ModelTrainingRun(
        model_artifact_id=ModelArtifactId(str(payload.get("model_artifact_id") or "")),
        training_cutoff=str(payload.get("training_cutoff") or ""),
        first_available_at=str(payload.get("first_available_at") or ""),
        training_dataset_artifact_ids=_string_list(
            payload.get("training_dataset_artifact_ids"),
            label="training dataset artifacts",
        ),
        trainer_code_artifact_id=str(payload.get("trainer_code_artifact_id") or ""),
        parameter_artifact_ids=_string_list(
            payload.get("parameter_artifact_ids"),
            label="training parameter artifacts",
        ),
        source_artifact_ids=_string_list(
            payload.get("source_artifact_ids"),
            label="training source artifacts",
        ),
        schema_version=_strict_int(payload.get("schema_version"), label="training schema_version"),
    )
    if value.semantic_payload() != payload or str(value.training_run_id) != stored.semantic_id:
        raise ValueError("forecast training replay semantic identity mismatch")
    return value


def _typed_dataset(stored: StoredLearningObject) -> EvaluationDataset:
    payload = stored.payload
    if payload.get("schema_name") != "apex-evaluation-dataset":
        raise ValueError("forecast evaluation dataset replay has wrong schema")
    rows = payload.get("cases")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("forecast evaluation dataset cases must be object array")
    cases = tuple(
        EvaluationCase(
            forecast_id=ForecastId(str(row.get("forecast_id") or "")),
            feature_snapshot_id=FeatureSnapshotId(str(row.get("feature_snapshot_id") or "")),
            model_artifact_id=ModelArtifactId(str(row.get("model_artifact_id") or "")),
            target=OutcomeTarget(str(row.get("target") or "")),
            player_id=OfficialPlayerId(
                _strict_int(row.get("player_id"), label="evaluation player_id")
            ),
            gameweek=_strict_int(row.get("gameweek"), label="evaluation gameweek"),
            prediction_sealed_at=str(row.get("prediction_sealed_at") or ""),
            outcome_first_available_at=str(row.get("outcome_first_available_at") or ""),
            prediction_artifact_id=str(row.get("prediction_artifact_id") or ""),
            outcome_artifact_id=str(row.get("outcome_artifact_id") or ""),
        )
        for row in rows
    )
    value = EvaluationDataset(
        season=str(payload.get("season") or ""),
        truth_registry_id=OutcomeTruthRegistryId(str(payload.get("truth_registry_id") or "")),
        cases=cases,
        source_artifact_ids=_string_list(
            payload.get("source_artifact_ids"),
            label="evaluation dataset source artifacts",
        ),
        schema_version=_strict_int(
            payload.get("schema_version"), label="evaluation dataset schema_version"
        ),
    )
    if value.semantic_payload() != payload or str(value.dataset_id) != stored.semantic_id:
        raise ValueError("forecast evaluation dataset semantic identity mismatch")
    return value


def _typed_observations(stored: StoredLearningObject) -> EvaluationObservationSet:
    payload = stored.payload
    if payload.get("schema_name") != "apex-evaluation-observation-set":
        raise ValueError("forecast observation replay has wrong schema")
    rows = payload.get("observations")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("forecast observations must be object array")
    observations = tuple(
        EvaluationObservation(
            case_id=str(row.get("case_id") or ""),
            truth_case_id=str(row.get("truth_case_id") or ""),
            target=OutcomeTarget(str(row.get("target") or "")),
            predicted_value=_optional_metric_value(
                row.get("predicted_value"), label="evaluation predicted value"
            ),
            actual_value=_metric_value(
                row.get("actual_value"), label="evaluation actual value"
            ),
            interval_lower=_optional_metric_value(
                row.get("interval_lower"), label="evaluation interval lower"
            ),
            interval_upper=_optional_metric_value(
                row.get("interval_upper"), label="evaluation interval upper"
            ),
        )
        for row in rows
    )
    value = EvaluationObservationSet(
        evaluation_dataset_id=EvaluationDatasetId(
            str(payload.get("evaluation_dataset_id") or "")
        ),
        evaluation_truth_set_id=EvaluationTruthSetId(
            str(payload.get("evaluation_truth_set_id") or "")
        ),
        observations=observations,
        schema_version=_strict_int(
            payload.get("schema_version"), label="observation schema_version"
        ),
    )
    if value.semantic_payload() != payload or str(value.observation_set_id) != stored.semantic_id:
        raise ValueError("forecast observation semantic identity mismatch")
    return value


def _typed_promotion(stored: StoredLearningObject) -> ModelPromotionCertificate:
    payload = stored.payload
    if payload.get("schema_name") != "apex-model-promotion-certificate":
        raise ValueError("forecast promotion replay has wrong schema")
    value = ModelPromotionCertificate(
        candidate_model_id=ModelArtifactId(str(payload.get("candidate_model_id") or "")),
        incumbent_model_id=ModelArtifactId(str(payload.get("incumbent_model_id") or "")),
        candidate_evaluation_id=ModelEvaluationId(
            str(payload.get("candidate_evaluation_id") or "")
        ),
        incumbent_evaluation_id=ModelEvaluationId(
            str(payload.get("incumbent_evaluation_id") or "")
        ),
        comparison_id=ModelComparisonId(str(payload.get("comparison_id") or "")),
        policy_id=LearningPolicyId(str(payload.get("policy_id") or "")),
        decision=ModelPromotionDecision(str(payload.get("decision") or "")),
        reason=str(payload.get("reason") or ""),
        source_artifact_ids=_string_list(
            payload.get("source_artifact_ids"),
            label="promotion source artifacts",
        ),
        schema_version=_strict_int(
            payload.get("schema_version"), label="promotion schema_version"
        ),
    )
    if value.semantic_payload() != payload or str(value.promotion_id) != stored.semantic_id:
        raise ValueError("forecast promotion semantic identity mismatch")
    return value


def _typed_registry_generation(stored: StoredLearningObject) -> ModelRegistryGeneration:
    payload = stored.payload
    if payload.get("schema_name") != "apex-model-registry-generation":
        raise ValueError("forecast model registry replay has wrong schema")
    parent_raw = payload.get("parent_generation_id")
    champion_raw = payload.get("champion_model_id")
    promotion_raw = payload.get("promotion_id")
    registered = payload.get("registered_model_ids")
    if not isinstance(registered, list) or any(not isinstance(item, str) for item in registered):
        raise ValueError("forecast model registry registered models must be string array")
    value = ModelRegistryGeneration(
        season=str(payload.get("season") or ""),
        generation=_strict_int(payload.get("generation"), label="model registry generation"),
        parent_generation_id=(
            None if parent_raw is None else ModelRegistryGenerationId(str(parent_raw))
        ),
        registered_model_ids=tuple(ModelArtifactId(item) for item in registered),
        champion_model_id=(
            None if champion_raw is None else ModelArtifactId(str(champion_raw))
        ),
        promotion_id=None if promotion_raw is None else ModelPromotionId(str(promotion_raw)),
        source_artifact_ids=_string_list(
            payload.get("source_artifact_ids"),
            label="model registry source artifacts",
        ),
        schema_version=_strict_int(
            payload.get("schema_version"), label="model registry schema_version"
        ),
    )
    if value.semantic_payload() != payload or str(value.generation_id) != stored.semantic_id:
        raise ValueError("forecast model registry semantic identity mismatch")
    return value


def verify_model_evaluation_replay(
    report_artifact_id: str,
    *,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> VerifiedModelEvaluationReplay:
    """Re-run the exact truth-governed evaluator behind one retained COMPLETE report."""

    stored = load_learning_object(
        report_artifact_id,
        store=store,
        expected_object_type="MODEL_EVALUATION_REPORT",
    )
    payload = stored.payload
    if payload.get("schema_name") != "apex-model-evaluation-report":
        raise ValueError("forecast model evaluation has wrong schema")
    if payload.get("use_mode") != "PRODUCTION":
        raise ValueError("forecast model evaluation is not PRODUCTION mode")
    if payload.get("status") != "COMPLETE" or payload.get("blockers") != []:
        raise ValueError("forecast model evaluation is not COMPLETE")
    sources = _source_ids(stored, label="forecast model evaluation")
    training_id = str(payload.get("training_run_id") or "")
    dataset_id = str(payload.get("evaluation_dataset_id") or "")
    observation_id = str(payload.get("observation_set_id") or "")
    policy_id = str(payload.get("policy_id") or "")
    if not all((training_id, dataset_id, observation_id, policy_id)):
        raise ValueError("forecast model evaluation identities are incomplete")

    training_stored = _find_learning_source(
        sources,
        object_type="MODEL_TRAINING_RUN",
        semantic_id=training_id,
        store=store,
        label="forecast training run",
    )
    dataset_stored = _find_learning_source(
        sources,
        object_type="EVALUATION_DATASET",
        semantic_id=dataset_id,
        store=store,
        label="forecast evaluation dataset",
    )
    observations_stored = _find_learning_source(
        sources,
        object_type="EVALUATION_OBSERVATION_SET",
        semantic_id=observation_id,
        store=store,
        label="forecast evaluation observations",
    )
    policy_stored = _find_learning_source(
        sources,
        object_type="LEARNING_EVALUATION_POLICY",
        semantic_id=policy_id,
        store=store,
        label="forecast learning policy",
    )

    training = _typed_training(training_stored)
    dataset = _typed_dataset(dataset_stored)
    observations = _typed_observations(observations_stored)
    if dataset.season != season:
        raise ValueError("forecast model evaluation season mismatch")
    if any(instant(case.outcome_first_available_at) > instant(as_of) for case in dataset.cases):
        raise ValueError("forecast model evaluation uses outcome unavailable at replay as_of")

    policy_registry, policy, policy_registry_artifact_id = _policy_authority(
        sources,
        policy_id=policy_id,
        season=season,
        as_of=as_of,
        store=store,
    )
    if policy_stored.payload != policy.semantic_payload():
        raise ValueError("forecast retained learning policy disagrees with champion registry")
    truth_registry, truth_registry_artifact_id = _truth_authority(
        sources,
        truth_registry_id=str(dataset.truth_registry_id),
        store=store,
    )

    report = evaluate_model(
        training_run=training,
        training_run_artifact_id=training_stored.artifact_id,
        dataset=dataset,
        evaluation_dataset_artifact_id=dataset_stored.artifact_id,
        observation_set=observations,
        observation_set_artifact_id=observations_stored.artifact_id,
        truth_registry=truth_registry,
        truth_registry_artifact_id=truth_registry_artifact_id,
        policy=policy,
        policy_artifact_id=policy_stored.artifact_id,
        policy_registry=policy_registry,
        policy_registry_artifact_id=policy_registry_artifact_id,
        store=store,
        production=True,
    )
    if report.semantic_payload() != payload or str(report.evaluation_id) != stored.semantic_id:
        raise ValueError("forecast model evaluation does not re-derive from retained truth inputs")
    return VerifiedModelEvaluationReplay(
        stored=stored,
        report=report,
        policy=policy,
        policy_registry=policy_registry,
        policy_registry_artifact_id=policy_registry_artifact_id,
    )


def verify_model_promotion_replay(
    promotion_artifact_id: str,
    *,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> VerifiedModelPromotionReplay:
    """Re-run exact evaluation, comparison and promotion semantics for one certificate."""

    stored = load_learning_object(
        promotion_artifact_id,
        store=store,
        expected_object_type="MODEL_PROMOTION_CERTIFICATE",
    )
    declared = _typed_promotion(stored)
    sources = _source_ids(stored, label="forecast promotion certificate")
    candidate_stored = _find_learning_source(
        sources,
        object_type="MODEL_EVALUATION_REPORT",
        semantic_id=str(declared.candidate_evaluation_id),
        store=store,
        label="forecast candidate evaluation",
    )
    incumbent_stored = _find_learning_source(
        sources,
        object_type="MODEL_EVALUATION_REPORT",
        semantic_id=str(declared.incumbent_evaluation_id),
        store=store,
        label="forecast incumbent evaluation",
    )
    comparison_stored = _find_learning_source(
        sources,
        object_type="MODEL_COMPARISON_REPORT",
        semantic_id=str(declared.comparison_id),
        store=store,
        label="forecast model comparison",
    )
    if set(comparison_stored.parent_artifact_ids) != {
        candidate_stored.artifact_id,
        incumbent_stored.artifact_id,
    }:
        raise ValueError("forecast comparison parent lineage does not bind exact evaluations")
    if stored.parent_artifact_ids != (comparison_stored.artifact_id,):
        raise ValueError("forecast promotion parent lineage does not bind exact comparison")

    candidate = verify_model_evaluation_replay(
        candidate_stored.artifact_id,
        season=season,
        as_of=as_of,
        store=store,
    )
    incumbent = verify_model_evaluation_replay(
        incumbent_stored.artifact_id,
        season=season,
        as_of=as_of,
        store=store,
    )
    if candidate.policy.semantic_payload() != incumbent.policy.semantic_payload():
        raise ValueError("forecast promotion evaluations use different learning policies")
    if candidate.policy_registry_artifact_id != incumbent.policy_registry_artifact_id:
        raise ValueError("forecast promotion evaluations use different policy registries")
    policy = candidate.policy
    policy_registry = candidate.policy_registry
    policy_registry_artifact_id = candidate.policy_registry_artifact_id

    comparison = compare_model_evaluations(
        candidate=candidate.report,
        incumbent=incumbent.report,
        candidate_report_artifact_id=candidate.stored.artifact_id,
        incumbent_report_artifact_id=incumbent.stored.artifact_id,
        policy=policy,
        policy_registry=policy_registry,
        policy_registry_artifact_id=policy_registry_artifact_id,
        policy_cutoff=as_of,
        store=store,
        production=True,
    )
    if (
        comparison.semantic_payload() != comparison_stored.payload
        or str(comparison.comparison_id) != comparison_stored.semantic_id
    ):
        raise ValueError("forecast model comparison does not re-derive from exact evaluations")

    certificate = issue_model_promotion_certificate(
        comparison=comparison,
        comparison_artifact_id=comparison_stored.artifact_id,
        candidate=candidate.report,
        candidate_report_artifact_id=candidate.stored.artifact_id,
        incumbent=incumbent.report,
        incumbent_report_artifact_id=incumbent.stored.artifact_id,
        policy=policy,
        policy_registry=policy_registry,
        policy_registry_artifact_id=policy_registry_artifact_id,
        promotion_cutoff=as_of,
        store=store,
    )
    if certificate.semantic_payload() != stored.payload or certificate.promotion_id != declared.promotion_id:
        raise ValueError("forecast promotion certificate does not re-derive from retained evidence")
    if certificate.decision is not ModelPromotionDecision.PROMOTE:
        raise ValueError("forecast champion evidence does not re-derive PROMOTE")
    return VerifiedModelPromotionReplay(
        stored=stored,
        certificate=certificate,
        candidate=candidate,
        incumbent=incumbent,
        comparison_artifact_id=comparison_stored.artifact_id,
    )


def _verify_registry_transition(
    stored: StoredLearningObject,
    *,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> tuple[ModelRegistryGeneration, VerifiedModelPromotionReplay | None, str | None]:
    generation = _typed_registry_generation(stored)
    if generation.season != season:
        raise ValueError("forecast model registry season mismatch")
    if generation.generation == 1:
        if stored.parent_artifact_ids:
            raise ValueError("forecast bootstrap registry generation cannot have parent artifact")
        if generation.champion_model_id is not None or generation.promotion_id is not None:
            raise ValueError("forecast bootstrap registry generation cannot start with champion")
        return generation, None, None

    if generation.parent_generation_id is None or generation.promotion_id is None:
        raise ValueError("forecast champion registry transition lacks parent/promotion identity")
    parent_matches: list[StoredLearningObject] = []
    for artifact_id in stored.parent_artifact_ids:
        try:
            parent = load_learning_object(
                artifact_id,
                store=store,
                expected_object_type="MODEL_REGISTRY_GENERATION",
                expected_semantic_id=str(generation.parent_generation_id),
            )
        except (FileNotFoundError, ValueError):
            continue
        parent_matches.append(parent)
    if len(parent_matches) != 1 or len(stored.parent_artifact_ids) != 1:
        raise ValueError("forecast model registry transition must bind exactly one semantic parent")
    parent_stored = parent_matches[0]
    parent, _, _ = _verify_registry_transition(
        parent_stored,
        season=season,
        as_of=as_of,
        store=store,
    )
    if parent.generation + 1 != generation.generation:
        raise ValueError("forecast model registry generation lineage is not contiguous")

    promotion_matches: list[str] = []
    for artifact_id in stored.source_artifact_ids:
        try:
            promotion = load_learning_object(
                artifact_id,
                store=store,
                expected_object_type="MODEL_PROMOTION_CERTIFICATE",
                expected_semantic_id=str(generation.promotion_id),
            )
        except (FileNotFoundError, ValueError):
            continue
        promotion_matches.append(promotion.artifact_id)
    if len(promotion_matches) != 1:
        raise ValueError("forecast model registry transition must bind exactly one promotion")
    promotion_artifact_id = promotion_matches[0]
    verified_promotion = verify_model_promotion_replay(
        promotion_artifact_id,
        season=season,
        as_of=as_of,
        store=store,
    )
    derived = apply_model_promotion(
        current=parent,
        promotion=verified_promotion.certificate,
        expected_parent_generation_id=parent.generation_id,
        current_generation_artifact_id=parent_stored.artifact_id,
        promotion_artifact_id=promotion_artifact_id,
        store=store,
    )
    if derived.semantic_payload() != generation.semantic_payload():
        raise ValueError("forecast model registry transition does not re-derive via CAS promotion")
    return generation, verified_promotion, promotion_artifact_id


def verify_forecast_registry_champion(
    registry_generation_artifact_id: str,
    *,
    season: str,
    as_of: str,
    store: ArtifactStore,
) -> VerifiedForecastChampionEvidence:
    """Replay the full model-registry transition chain and return exact champion evidence."""

    stored = load_learning_object(
        registry_generation_artifact_id,
        store=store,
        expected_object_type="MODEL_REGISTRY_GENERATION",
    )
    generation, promotion, promotion_artifact_id = _verify_registry_transition(
        stored,
        season=season,
        as_of=as_of,
        store=store,
    )
    if generation.champion_model_id is None or promotion is None or promotion_artifact_id is None:
        raise ValueError("forecast registry generation has no replay-derived champion")
    champion_model_id = str(generation.champion_model_id)
    if str(promotion.certificate.candidate_model_id) != champion_model_id:
        raise ValueError("forecast registry champion does not match replay-derived promoted candidate")
    return VerifiedForecastChampionEvidence(
        registry_generation_artifact_id=registry_generation_artifact_id,
        registry_generation=generation,
        champion_model_id=champion_model_id,
        promotion_artifact_id=promotion_artifact_id,
        promotion=promotion,
    )
