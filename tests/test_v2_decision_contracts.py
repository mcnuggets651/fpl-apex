from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.decision_policy_registry import (
    DecisionPolicyRegistry,
    load_decision_policy_registry,
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
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from apex_fpl.core.ids import (
    CandidateUniverseId,
    DecisionPolicyId,
    ForecastId,
    ManagerStateId,
    RuleSetId,
)


def _artifact(store: FileSystemArtifactStore, content: bytes) -> str:
    return store.put_bytes(content).artifact_id


def _shadow_policy() -> DecisionPolicy:
    return DecisionPolicy(
        policy_name="tactical-reference",
        policy_version="1",
        season="2026-2027",
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
        tie_break_policy="lexicographic-official-id-v1",
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


def test_empty_registry_has_no_fabricated_production_decision_policy() -> None:
    registry = load_decision_policy_registry(Path("config/decision_policies_v2.yaml"))
    assert registry.season == "2026-2027"
    assert registry.policies == ()
    assert registry.champion() is None


def test_decision_policy_identity_is_part_of_decision_input_identity() -> None:
    first = _shadow_policy()
    second = DecisionPolicy(
        **{
            **first.__dict__,
            "policy_version": "2",
            "tie_break_policy": "lexicographic-official-id-v2",
        }
    )
    assert first.decision_policy_id != second.decision_policy_id
    assert (
        _decision_input(first.decision_policy_id).decision_input_id
        != _decision_input(second.decision_policy_id).decision_input_id
    )


def test_receding_horizon_policy_requires_continuation_and_chip_option_artifacts() -> None:
    with pytest.raises(ValueError, match="continuation-value artifact"):
        DecisionPolicy(
            policy_name="bad-receding",
            policy_version="1",
            season="2026-2027",
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


def test_qualified_policy_artifacts_must_exist_and_champion_must_be_qualified(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    qualification = _artifact(store, b"qualification")
    continuation = _artifact(store, b"continuation")
    chip_option = _artifact(store, b"chip-option")
    policy = DecisionPolicy(
        policy_name="qualified-over-time",
        policy_version="1",
        season="2026-2027",
        qualification_state=DecisionPolicyQualificationState.QUALIFIED,
        qualification_artifact_id=qualification,
        first_available_at="2026-08-24T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=6,
        continuation_value_artifact_id=continuation,
        chip_option_value_artifact_id=chip_option,
        price_policy_artifact_id=None,
        candidate_policy_artifact_id=None,
        tie_break_policy="v1",
    )
    registry = DecisionPolicyRegistry(
        season="2026-2027",
        policies=(policy,),
        champion_policy_id=policy.decision_policy_id,
    )
    registry.verify_policy_artifacts(policy, store=store, production=True)

    other_store = FileSystemArtifactStore(tmp_path / "other")
    with pytest.raises(FileNotFoundError):
        registry.verify_policy_artifacts(policy, store=other_store, production=True)


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
