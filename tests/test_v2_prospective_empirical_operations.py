from __future__ import annotations

import inspect

import pytest
import typer

import apex_fpl.control.candidate_operations as candidate_operations
import apex_fpl.control.prospective_experiment_operations as experiment_operations
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.candidate_operations import (
    materialize_decision_policy_candidate,
    materialize_forecast_model_candidate,
    materialize_qualified_candidate,
)
from apex_fpl.control.decision_policy_support import store_decision_policy_support
from apex_fpl.control.prospective_experiment_operations import (
    declare_candidate_experiment,
    derive_candidate_qualification,
    record_candidate_experiment_result,
)
from apex_fpl.core.decision_policy import (
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
)
from apex_fpl.core.decision_policy_support import (
    CandidatePolicy,
    ChipOptionValuePolicy,
    ContinuationValuePolicy,
    ExactPolicyValue,
    PricePolicy,
)
from apex_fpl.core.numeric_policy import DECISION_NUMERIC_POLICY_ID
from apex_fpl.v2_operations_cli import (
    _EXPERIMENT_SPEC_FIELDS,
    _MODEL_SPEC_FIELDS,
    _POLICY_SPEC_FIELDS,
    _RESULT_SPEC_FIELDS,
    _validate_spec,
    experiment_declare,
    experiment_result,
)


T0 = "2026-08-26T16:00:00Z"
T1 = "2026-08-26T16:01:00Z"
T2 = "2026-08-26T16:02:00Z"
T3 = "2026-08-26T16:03:00Z"
T4 = "2026-08-26T16:04:00Z"
TEND = "2026-08-26T17:00:00Z"
SEASON = "2026-27"


def _store(tmp_path):
    return FileSystemArtifactStore(tmp_path / "artifacts")


def _model_spec(parameter_id: str) -> dict[str, object]:
    return {
        "model_name": "prospective-test-model",
        "model_version": "1",
        "feature_contract": "feature-v2",
        "prediction_contract": "prediction-v2",
        "parameter_artifact_ids": [parameter_id],
        "valid_seasons": [SEASON],
        "qualification_season": SEASON,
        "trained_through": "2026-08-25T23:59:00Z",
        "max_horizon_gameweeks": 8,
    }


def _experiment_spec(evaluator_id: str, policy_id: str) -> dict[str, object]:
    return {
        "evaluator_artifact_id": evaluator_id,
        "policy_artifact_id": policy_id,
        "evaluation_window_start": T1,
        "evaluation_window_end": T2,
        "minimum_sample_size": 5,
        "metric_rules": [
            {
                "metric_id": "score",
                "direction": "AT_LEAST",
                "threshold": {"numerator": 1, "denominator": 1},
            }
        ],
        "valid_until": TEND,
    }


def _result_spec(source_id: str) -> dict[str, object]:
    return {
        "sample_size": 10,
        "metrics": [
            {
                "metric_id": "score",
                "value": {"numerator": 2, "denominator": 1},
            }
        ],
        "source_artifact_ids": [source_id],
    }


def _policy_supports(store: FileSystemArtifactStore) -> dict[str, str]:
    continuation = ContinuationValuePolicy(
        season=SEASON,
        horizon_gameweeks=2,
        first_available_at=T0,
        gameweek_weights=(ExactPolicyValue.one(), ExactPolicyValue.one()),
    )
    chip = ChipOptionValuePolicy(
        season=SEASON,
        horizon_gameweeks=2,
        first_available_at=T0,
        option_values=tuple(
            (name, ExactPolicyValue.zero())
            for name in ("BENCH_BOOST", "FREE_HIT", "TRIPLE_CAPTAIN", "WILDCARD")
        ),
    )
    price = PricePolicy(season=SEASON, first_available_at=T0)
    candidate = CandidatePolicy(season=SEASON, first_available_at=T0)
    return {
        "continuation_value_artifact_id": store_decision_policy_support(
            continuation, store=store
        ),
        "chip_option_value_artifact_id": store_decision_policy_support(chip, store=store),
        "price_policy_artifact_id": store_decision_policy_support(price, store=store),
        "candidate_policy_artifact_id": store_decision_policy_support(candidate, store=store),
    }


def test_forecast_candidate_prospective_qualification_is_separate_from_promotion(
    tmp_path, monkeypatch
) -> None:
    store = _store(tmp_path)
    parameter_id = store.put_bytes(b"model-parameters").artifact_id
    evaluator_id = store.put_bytes(b"frozen-evaluator").artifact_id
    policy_id = store.put_bytes(b"frozen-evaluation-policy").artifact_id
    outcome_id = store.put_bytes(b"retained-outcome-truth").artifact_id

    monkeypatch.setattr(candidate_operations, "_utc_now", lambda: T0)
    shadow = materialize_forecast_model_candidate(_model_spec(parameter_id), store=store)
    assert shadow.qualification_state == "SHADOW"
    assert shadow.qualification_artifact_id is None
    assert shadow.registry_row["first_available_at"] == T0
    assert shadow.operator_payload()["champion_changed"] is False

    monkeypatch.setattr(experiment_operations, "_utc_now", lambda: T0)
    declaration = declare_candidate_experiment(
        shadow.candidate_artifact_id,
        _experiment_spec(evaluator_id, policy_id),
        store=store,
    )
    assert declaration.definition.declared_at == T0
    assert declaration.definition.evaluation_window_start == T1

    monkeypatch.setattr(experiment_operations, "_utc_now", lambda: T1)
    with pytest.raises(ValueError, match="before evaluation window ends"):
        record_candidate_experiment_result(
            declaration.declaration_artifact_id,
            _result_spec(outcome_id),
            store=store,
        )

    monkeypatch.setattr(experiment_operations, "_utc_now", lambda: T3)
    result = record_candidate_experiment_result(
        declaration.declaration_artifact_id,
        _result_spec(outcome_id),
        store=store,
    )
    assert result.result.evaluated_at == T3

    qualification = derive_candidate_qualification(
        declaration.declaration_artifact_id,
        result.result_artifact_id,
        store=store,
    )
    assert qualification.decision == "SUPPORTED"
    assert qualification.operator_payload()["champion_changed"] is False

    monkeypatch.setattr(candidate_operations, "_utc_now", lambda: T4)
    qualified = materialize_qualified_candidate(
        shadow.candidate_artifact_id,
        qualification.certificate_artifact_id,
        store=store,
    )
    assert qualified.qualification_state == "QUALIFIED"
    assert qualified.qualification_artifact_id == qualification.certificate_artifact_id
    assert qualified.candidate_id != shadow.candidate_id
    assert qualified.subject_id == shadow.subject_id
    assert qualified.operator_payload()["champion_changed"] is False


def test_declaration_cannot_be_backdated_or_opened_after_window_start(tmp_path, monkeypatch) -> None:
    store = _store(tmp_path)
    parameter_id = store.put_bytes(b"model-parameters").artifact_id
    evaluator_id = store.put_bytes(b"evaluator").artifact_id
    policy_id = store.put_bytes(b"policy").artifact_id

    monkeypatch.setattr(candidate_operations, "_utc_now", lambda: T0)
    shadow = materialize_forecast_model_candidate(_model_spec(parameter_id), store=store)

    monkeypatch.setattr(experiment_operations, "_utc_now", lambda: T1)
    with pytest.raises(ValueError, match="before evaluation window starts"):
        declare_candidate_experiment(
            shadow.candidate_artifact_id,
            _experiment_spec(evaluator_id, policy_id),
            store=store,
        )


def test_decision_policy_candidate_requires_receding_support_and_cannot_use_tactical_policy(
    tmp_path, monkeypatch
) -> None:
    store = _store(tmp_path)
    monkeypatch.setattr(candidate_operations, "_utc_now", lambda: T0)
    supports = _policy_supports(store)
    policy_spec = {
        "policy_name": "prospective-policy",
        "policy_version": "1",
        "season": SEASON,
        "evaluation_mode": DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION.value,
        "objective_policy": DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME.value,
        "horizon_gameweeks": 2,
        **supports,
        "tie_break_policy": TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
        "numeric_policy_id": DECISION_NUMERIC_POLICY_ID,
    }
    policy = materialize_decision_policy_candidate(policy_spec, store=store)
    assert policy.qualification_state == "SHADOW"
    assert policy.subject_kind == "apex.decision-policy"
    assert policy.operator_payload()["review_required"] is True

    tactical = dict(policy_spec)
    tactical["evaluation_mode"] = DecisionEvaluationMode.TACTICAL_CURRENT_GAMEWEEK.value
    tactical["horizon_gameweeks"] = 1
    with pytest.raises(ValueError):
        materialize_decision_policy_candidate(tactical, store=store)


@pytest.mark.parametrize(
    ("allowed_fields", "payload", "label"),
    [
        (_MODEL_SPEC_FIELDS, {"first_available_at": "2000-01-01T00:00:00Z"}, "model spec"),
        (_POLICY_SPEC_FIELDS, {"first_available_at": "2000-01-01T00:00:00Z"}, "policy spec"),
        (_EXPERIMENT_SPEC_FIELDS, {"declared_at": "2000-01-01T00:00:00Z"}, "experiment spec"),
        (_RESULT_SPEC_FIELDS, {"evaluated_at": "2000-01-01T00:00:00Z"}, "result spec"),
    ],
)
def test_operator_specs_reject_caller_owned_chronology(
    allowed_fields: frozenset[str],
    payload: dict[str, object],
    label: str,
) -> None:
    with pytest.raises(typer.BadParameter, match="unsupported fields"):
        _validate_spec(payload, allowed_fields=allowed_fields, label=label)


def test_cli_exposes_no_caller_authored_declaration_or_result_timestamp() -> None:
    assert "declared_at" not in inspect.signature(experiment_declare).parameters
    assert "evaluated_at" not in inspect.signature(experiment_result).parameters
