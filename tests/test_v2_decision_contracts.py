from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.decision_policy_registry import (
    DecisionPolicyRegistry,
    load_decision_policy_registry,
)
from apex_fpl.control.experiment_registry import (
    ExperimentRegistration,
    ExperimentRegistry,
    derive_empirical_qualification_certificate,
    store_empirical_qualification_certificate,
    store_experiment_definition,
    store_experiment_registry,
    store_experiment_result,
)
from apex_fpl.core.decision import (
    CandidateUniverseScope,
    DecisionChip,
    DecisionInput,
    DecisionObjectiveModel,
    DecisionUseMode,
    ExactnessClaim,
    ExactnessStatus,
    ExpansionResult,
    RationalValue,
    SolverCertificate,
    SolverStatus,
)
from apex_fpl.core.decision_policy import (
    TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from apex_fpl.core.experiments import (
    ExactQualificationValue,
    ExperimentDefinition,
    ExperimentResult,
    QualificationMetricDirection,
    QualificationMetricResult,
    QualificationMetricRule,
    qualification_subject_id,
)
from apex_fpl.core.ids import (
    CandidateUniverseId,
    DecisionPolicyId,
    ForecastId,
    ManagerStateId,
    RuleSetId,
)


SEASON = "2026-2027"
DECISION_CUTOFF = "2026-08-25T00:00:00Z"


def _artifact(store: FileSystemArtifactStore, content: bytes) -> str:
    return store.put_bytes(content).artifact_id


def _shadow_policy() -> DecisionPolicy:
    return DecisionPolicy(
        policy_name="tactical-reference",
        policy_version="1",
        season=SEASON,
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-24T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.TACTICAL_CURRENT_GAMEWEEK,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=1,
        continuation_value_artifact_id=None,
        chip_option_value_artifact_id=None,
        price_policy_artifact_id=None,
        candidate_policy_artifact_id=None,
        tie_break_policy=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    )


def _decision_input(policy_id: DecisionPolicyId) -> DecisionInput:
    return DecisionInput(
        manager_state_id=ManagerStateId("state"),
        forecast_id=ForecastId("forecast"),
        ruleset_id=RuleSetId("rules"),
        candidate_universe_id=CandidateUniverseId("universe"),
        decision_policy_id=policy_id,
        gameweek=2,
        use_mode=DecisionUseMode.SHADOW,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=1,
        chips_considered=(DecisionChip.NONE,),
    )


def _attach_decision_policy_qualification(
    store: FileSystemArtifactStore,
    policy: DecisionPolicy,
) -> DecisionPolicy:
    evaluator = _artifact(store, b"decision-policy-evaluator")
    qualification_policy = _artifact(store, b"decision-policy-qualification-policy")
    source = _artifact(store, b"decision-policy-qualification-source")
    definition = ExperimentDefinition(
        proof_id="PO-DECISION-POLICY-QUALIFICATION-001",
        subject_kind="apex.decision-policy",
        subject_id=qualification_subject_id(policy.semantic_payload()),
        season=SEASON,
        evaluator_artifact_id=evaluator,
        policy_artifact_id=qualification_policy,
        declared_at="2026-08-01T00:00:00Z",
        evaluation_window_start="2026-08-02T00:00:00Z",
        evaluation_window_end="2026-08-23T00:00:00Z",
        minimum_sample_size=1,
        metric_rules=(
            QualificationMetricRule(
                metric_id="synthetic-policy-score",
                direction=QualificationMetricDirection.AT_LEAST,
                threshold=ExactQualificationValue(1, 1),
            ),
        ),
        valid_until="2026-09-01T00:00:00Z",
    )
    definition_ref = store_experiment_definition(definition, store=store)
    result = ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=definition.proof_id,
        subject_kind=definition.subject_kind,
        subject_id=definition.subject_id,
        season=SEASON,
        evaluator_artifact_id=evaluator,
        evaluated_at="2026-08-23T00:00:00Z",
        sample_size=1,
        metrics=(
            QualificationMetricResult(
                metric_id="synthetic-policy-score",
                value=ExactQualificationValue(1, 1),
            ),
        ),
        source_artifact_ids=(source,),
    )
    result_ref = store_experiment_result(result, store=store)
    registry = ExperimentRegistry(
        season=SEASON,
        registrations=(
            ExperimentRegistration(definition.experiment_id, definition_ref.artifact_id),
        ),
    )
    registry_ref = store_experiment_registry(registry, store=store)
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=definition_ref.artifact_id,
        result_artifact_id=result_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        store=store,
    )
    certificate_ref = store_empirical_qualification_certificate(certificate, store=store)
    assert certificate.supported is True
    return replace(policy, qualification_artifact_id=certificate_ref.artifact_id)


def test_empty_registry_has_no_fabricated_production_decision_policy() -> None:
    registry = load_decision_policy_registry(Path("config/decision_policies_v2.yaml"))
    assert registry.season == SEASON
    assert registry.policies == ()
    assert registry.champion() is None


def test_decision_policy_identity_is_part_of_decision_input_identity() -> None:
    first = _shadow_policy()
    second = replace(first, policy_version="2")
    assert first.decision_policy_id != second.decision_policy_id
    assert (
        _decision_input(first.decision_policy_id).decision_input_id
        != _decision_input(second.decision_policy_id).decision_input_id
    )


def test_tactical_policy_rejects_unimplemented_tie_break_semantics() -> None:
    with pytest.raises(ValueError, match="unimplemented tie-break semantics"):
        replace(_shadow_policy(), tie_break_policy="lexicographic-official-id-v2")


def test_tactical_policy_requires_exactly_one_gameweek_horizon() -> None:
    with pytest.raises(ValueError, match="horizon_gameweeks == 1"):
        replace(_shadow_policy(), horizon_gameweeks=2)


def test_tactical_policy_rejects_semantic_artifacts_it_does_not_execute() -> None:
    artifact = "sha256:" + "a" * 64
    for field in (
        "continuation_value_artifact_id",
        "chip_option_value_artifact_id",
        "price_policy_artifact_id",
        "candidate_policy_artifact_id",
    ):
        with pytest.raises(ValueError, match="cannot declare unused policy artifacts"):
            replace(_shadow_policy(), **{field: artifact})


def test_receding_policy_tie_break_is_semantic_identity() -> None:
    artifact = "sha256:" + "a" * 64
    first = DecisionPolicy(
        policy_name="receding-shadow",
        policy_version="1",
        season=SEASON,
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-24T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=6,
        continuation_value_artifact_id=artifact,
        chip_option_value_artifact_id=artifact,
        price_policy_artifact_id=None,
        candidate_policy_artifact_id=None,
        tie_break_policy="future-policy-v1",
    )
    second = replace(first, tie_break_policy="future-policy-v2")
    assert first.decision_policy_id != second.decision_policy_id


def test_receding_horizon_policy_requires_continuation_and_chip_option_artifacts() -> None:
    with pytest.raises(ValueError, match="continuation-value artifact"):
        DecisionPolicy(
            policy_name="bad-receding",
            policy_version="1",
            season=SEASON,
            qualification_state=DecisionPolicyQualificationState.SHADOW,
            qualification_artifact_id=None,
            first_available_at="2026-08-24T00:00:00Z",
            evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
            objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
            horizon_gameweeks=6,
            continuation_value_artifact_id=None,
            chip_option_value_artifact_id=None,
            price_policy_artifact_id=None,
            candidate_policy_artifact_id=None,
            tie_break_policy="v1",
        )


def test_qualified_policy_without_price_and_candidate_policy_is_not_production_qualified(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    policy = DecisionPolicy(
        policy_name="incomplete-over-time",
        policy_version="1",
        season=SEASON,
        qualification_state=DecisionPolicyQualificationState.QUALIFIED,
        qualification_artifact_id=_artifact(store, b"qualification"),
        first_available_at="2026-08-24T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=6,
        continuation_value_artifact_id=_artifact(store, b"continuation"),
        chip_option_value_artifact_id=_artifact(store, b"chip-option"),
        price_policy_artifact_id=None,
        candidate_policy_artifact_id=None,
        tie_break_policy="v1",
    )
    assert policy.production_qualified is False
    with pytest.raises(ValueError, match="champion must be production qualified"):
        DecisionPolicyRegistry(
            season=SEASON,
            policies=(policy,),
            champion_policy_id=policy.decision_policy_id,
        )


def test_qualified_policy_artifacts_must_exist_and_champion_must_be_qualified(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    continuation = _artifact(store, b"continuation")
    chip_option = _artifact(store, b"chip-option")
    price_policy = _artifact(store, b"price-policy")
    candidate_policy = _artifact(store, b"candidate-policy")
    policy = DecisionPolicy(
        policy_name="qualified-over-time",
        policy_version="1",
        season=SEASON,
        qualification_state=DecisionPolicyQualificationState.QUALIFIED,
        qualification_artifact_id=_artifact(store, b"prequalification-placeholder"),
        first_available_at="2026-08-24T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=6,
        continuation_value_artifact_id=continuation,
        chip_option_value_artifact_id=chip_option,
        price_policy_artifact_id=price_policy,
        candidate_policy_artifact_id=candidate_policy,
        tie_break_policy="v1",
    )
    policy = _attach_decision_policy_qualification(store, policy)
    assert policy.production_qualified is True
    registry = DecisionPolicyRegistry(
        season=SEASON,
        policies=(policy,),
        champion_policy_id=policy.decision_policy_id,
    )
    registry.verify_policy_artifacts(
        policy,
        store=store,
        production=True,
        as_of=DECISION_CUTOFF,
    )

    other_store = FileSystemArtifactStore(tmp_path / "other")
    with pytest.raises(FileNotFoundError):
        registry.verify_policy_artifacts(
            policy,
            store=other_store,
            production=True,
            as_of=DECISION_CUTOFF,
        )


def test_solver_limit_and_error_are_not_constructible_as_infeasible_shortcuts() -> None:
    zero = RationalValue.zero()
    limited = SolverCertificate(
        status=SolverStatus.SOLVER_LIMIT,
        incumbent_objective=RationalValue(10, 1),
        best_bound=RationalValue(12, 1),
        gap=RationalValue(2, 1),
        numeric_error_bound=zero,
        message="time limit",
    )
    assert limited.status is SolverStatus.SOLVER_LIMIT
    assert limited.status is not SolverStatus.INFEASIBLE

    with pytest.raises(ValueError, match="cannot carry an incumbent"):
        SolverCertificate(
            status=SolverStatus.INFEASIBLE,
            incumbent_objective=RationalValue(1, 1),
            best_bound=None,
            gap=None,
            numeric_error_bound=zero,
            message="not actually infeasible",
        )


def test_global_optimal_exactness_requires_full_universe_complete_surface_and_zero_gap() -> None:
    zero = RationalValue.zero()
    with pytest.raises(ValueError, match="internally inconsistent"):
        ExactnessClaim(
            status=ExactnessStatus.GLOBAL_OPTIMAL,
            candidate_universe_id=CandidateUniverseId("u"),
            universe_scope=CandidateUniverseScope.SCOPED,
            solver_status=SolverStatus.OPTIMAL,
            action_surface_complete=True,
            search_complete=True,
            best_bound=RationalValue(10, 1),
            gap=zero,
            filter_identity="sha256:" + "a" * 64,
            expansion_result=ExpansionResult.NOT_RUN,
            expansion_certificate_id=None,
            numeric_error_bound=zero,
            reasons=(),
        )


def test_rational_numeric_policy_has_exact_semantic_normalisation() -> None:
    assert RationalValue(6, 4) == RationalValue(3, 2)
    assert RationalValue(0, 9000) == RationalValue.zero()
