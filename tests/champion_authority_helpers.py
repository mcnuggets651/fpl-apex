from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.champion_authority import (
    StoredChampionAdmission,
    StoredChampionGeneration,
    create_production_champion_generation,
    issue_champion_admission,
)
from apex_fpl.control.learning_store import store_learning_object
from apex_fpl.core.champion_authority import ChampionRole
from apex_fpl.core.ids import (
    LearningPolicyId,
    ModelArtifactId,
    ModelComparisonId,
    ModelEvaluationId,
)
from apex_fpl.core.learning_common import ModelPromotionDecision
from apex_fpl.core.learning_promotion import ModelPromotionCertificate, ModelRegistryGeneration
from apex_fpl.decision.scenario_store import load_robustness_report, load_scenario_set

from empirical_qualification_helpers import synthetic_supported_qualification_artifact
from production_planning_bundle_helpers import SyntheticPlanningBundleFixture


@dataclass(frozen=True, slots=True)
class SyntheticChampionAuthorityFixture:
    generation: StoredChampionGeneration
    forecast_registry_generation_artifact_id: str
    decision_policy_admission: StoredChampionAdmission
    scenario_generator_admission: StoredChampionAdmission
    scenario_policy_admission: StoredChampionAdmission


def _source_id(store, label: str) -> str:
    return store.put_bytes(f"synthetic-champion-authority:{label}".encode("utf-8")).artifact_id


def _json_at(store, artifact_id: str) -> dict[str, object]:
    value = json.loads(store.read_bytes(artifact_id).decode("utf-8"))
    if not isinstance(value, dict):
        raise AssertionError("synthetic champion semantic artifact must be JSON object")
    return dict(value)


def _forecast_registry_generation(*, store, fixture: SyntheticPlanningBundleFixture) -> str:
    candidate_model_id = ModelArtifactId(str(fixture.bundle.forecast_model_id))
    incumbent_model_id = ModelArtifactId(_source_id(store, "incumbent-model"))
    candidate_evaluation_id = ModelEvaluationId(_source_id(store, "candidate-evaluation"))
    incumbent_evaluation_id = ModelEvaluationId(_source_id(store, "incumbent-evaluation"))
    comparison_id = ModelComparisonId(_source_id(store, "model-comparison"))
    policy_id = LearningPolicyId(_source_id(store, "learning-policy"))
    certificate_sources = (
        str(candidate_evaluation_id),
        str(incumbent_evaluation_id),
        str(comparison_id),
        str(policy_id),
    )
    certificate = ModelPromotionCertificate(
        candidate_model_id=candidate_model_id,
        incumbent_model_id=incumbent_model_id,
        candidate_evaluation_id=candidate_evaluation_id,
        incumbent_evaluation_id=incumbent_evaluation_id,
        comparison_id=comparison_id,
        policy_id=policy_id,
        decision=ModelPromotionDecision.PROMOTE,
        reason="synthetic mechanism-only production champion promotion",
        source_artifact_ids=certificate_sources,
    )
    stored_certificate = store_learning_object(certificate, store=store)
    generation = ModelRegistryGeneration(
        season=fixture.bundle.season,
        generation=1,
        parent_generation_id=None,
        registered_model_ids=(incumbent_model_id, candidate_model_id),
        champion_model_id=candidate_model_id,
        promotion_id=certificate.promotion_id,
        source_artifact_ids=(stored_certificate.artifact_id,),
    )
    return store_learning_object(generation, store=store).artifact_id


def synthetic_production_champion_authority(
    *,
    store,
    fixture: SyntheticPlanningBundleFixture,
    reviewed_at: str = "2026-08-24T12:00:00Z",
    current_generation_artifact_id: str | None = None,
    expected_parent_generation_id: str | None = None,
) -> SyntheticChampionAuthorityFixture:
    """Build mechanism-only authority evidence; never real production admission evidence."""

    season = fixture.bundle.season
    policy_payload = _json_at(store, str(fixture.bundle.decision_policy_id))
    policy_qualification = fixture.direct_qualifications[
        "PO-DECISION-POLICY-QUALIFICATION-001"
    ].artifact_id
    policy_admission = issue_champion_admission(
        role=ChampionRole.DECISION_POLICY,
        season=season,
        candidate_id=str(fixture.bundle.decision_policy_id),
        subject_payload=policy_payload,
        qualification_artifact_id=policy_qualification,
        review_artifact_id=_source_id(store, "decision-policy-reviewed-change"),
        reviewed_by="synthetic-reviewer",
        reviewed_at=reviewed_at,
        reason="synthetic mechanism-only DecisionPolicy admission",
        store=store,
    )

    scenario_set = load_scenario_set(
        fixture.bundle.scenario_set_artifact_id,
        store=store,
    ).scenario_set
    generator_payload = {
        "schema_name": "synthetic-planning-generator",
        "season": season,
    }
    generator_qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=generator_payload,
        subject_kind="apex.scenario-generator",
        proof_id="QUAL-SCENARIO-GENERATOR-001",
        season=season,
    )
    generator_admission = issue_champion_admission(
        role=ChampionRole.SCENARIO_GENERATOR,
        season=season,
        candidate_id=str(scenario_set.scenario_generator_id),
        subject_payload=generator_payload,
        qualification_artifact_id=generator_qualification,
        review_artifact_id=_source_id(store, "scenario-generator-reviewed-change"),
        reviewed_by="synthetic-reviewer",
        reviewed_at=reviewed_at,
        reason="synthetic mechanism-only scenario-generator admission",
        store=store,
    )

    robustness_report = load_robustness_report(
        fixture.bundle.robustness_report_artifact_id,
        store=store,
    ).report
    policy_subject = {
        "schema_name": "synthetic-planning-scenario-policy",
        "season": season,
    }
    scenario_policy_qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=policy_subject,
        subject_kind="apex.scenario-policy",
        proof_id="QUAL-SCENARIO-POLICY-001",
        season=season,
    )
    scenario_policy_admission = issue_champion_admission(
        role=ChampionRole.SCENARIO_POLICY,
        season=season,
        candidate_id=str(robustness_report.scenario_policy_id),
        subject_payload=policy_subject,
        qualification_artifact_id=scenario_policy_qualification,
        review_artifact_id=_source_id(store, "scenario-policy-reviewed-change"),
        reviewed_by="synthetic-reviewer",
        reviewed_at=reviewed_at,
        reason="synthetic mechanism-only scenario-policy admission",
        store=store,
    )

    registry_artifact_id = _forecast_registry_generation(store=store, fixture=fixture)
    stored_generation = create_production_champion_generation(
        season=season,
        forecast_registry_generation_artifact_id=registry_artifact_id,
        decision_policy_admission_artifact_id=policy_admission.artifact_id,
        scenario_generator_admission_artifact_id=generator_admission.artifact_id,
        scenario_policy_admission_artifact_id=scenario_policy_admission.artifact_id,
        change_control_artifact_id=_source_id(store, "champion-generation-change-control"),
        authorized_by="synthetic-authorizer",
        authorized_at=reviewed_at,
        reason="synthetic mechanism-only production champion generation",
        current_generation_artifact_id=current_generation_artifact_id,
        expected_parent_generation_id=expected_parent_generation_id,
        store=store,
    )
    return SyntheticChampionAuthorityFixture(
        generation=stored_generation,
        forecast_registry_generation_artifact_id=registry_artifact_id,
        decision_policy_admission=policy_admission,
        scenario_generator_admission=generator_admission,
        scenario_policy_admission=scenario_policy_admission,
    )
