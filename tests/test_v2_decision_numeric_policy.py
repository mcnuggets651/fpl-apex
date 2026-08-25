from __future__ import annotations

import pytest

from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import DEFAULT_NUMERIC_POLICY_ID
from apex_fpl.core.numeric_policy import DECISION_NUMERIC_POLICY_ID
from apex_fpl.core.reference_solver_io import ReferenceSolverRequest


def _documents(*, decision_numeric: str, policy_numeric: str):
    ruleset = {
        "schema_name": "apex-fpl-ruleset",
        "schema_version": 1,
        "season": "2026-2027",
    }
    ruleset_id = canonical_sha256(ruleset)
    manager = {
        "schema_name": "apex-manager-state",
        "schema_version": 1,
        "season": "2026-2027",
        "gameweek": 2,
        "ruleset_id": ruleset_id,
    }
    forecast = {
        "schema_name": "apex-probabilistic-forecast",
        "schema_version": 1,
        "season": "2026-2027",
        "ruleset_id": ruleset_id,
        "global_world_id": "numeric-policy-world",
    }
    universe = {
        "schema_name": "apex-candidate-universe",
        "schema_version": 1,
        "global_world_id": "numeric-policy-world",
    }
    policy = {
        "schema_name": "apex-decision-policy",
        "schema_version": 1,
        "season": "2026-2027",
        "evaluation_mode": "TACTICAL_CURRENT_GAMEWEEK",
        "numeric_policy_id": policy_numeric,
    }
    decision_input = {
        "schema_name": "apex-decision-input",
        "schema_version": 1,
        "manager_state_id": canonical_sha256(manager),
        "forecast_id": canonical_sha256(forecast),
        "ruleset_id": ruleset_id,
        "candidate_universe_id": canonical_sha256(universe),
        "decision_policy_id": canonical_sha256(policy),
        "gameweek": 2,
        "objective_model": "MARGINAL_INDEPENDENCE_BASELINE",
        "numeric_policy_id": decision_numeric,
    }
    return decision_input, manager, forecast, universe, ruleset, policy


def _request(*, decision_numeric: str, policy_numeric: str) -> ReferenceSolverRequest:
    decision_input, manager, forecast, universe, ruleset, policy = _documents(
        decision_numeric=decision_numeric,
        policy_numeric=policy_numeric,
    )
    return ReferenceSolverRequest.from_semantic_documents(
        decision_input=decision_input,
        manager_state=manager,
        forecast=forecast,
        candidate_universe=universe,
        ruleset=ruleset,
        decision_policy=policy,
        max_search_nodes=1,
    )


def test_decision_numeric_policy_identity_has_one_canonical_value() -> None:
    assert DEFAULT_NUMERIC_POLICY_ID == DECISION_NUMERIC_POLICY_ID


def test_raw_sealed_request_accepts_only_canonical_matching_numeric_policy() -> None:
    request = _request(
        decision_numeric=DECISION_NUMERIC_POLICY_ID,
        policy_numeric=DECISION_NUMERIC_POLICY_ID,
    )
    assert request.decision_input["numeric_policy_id"] == DECISION_NUMERIC_POLICY_ID
    assert request.decision_policy["numeric_policy_id"] == DECISION_NUMERIC_POLICY_ID


def test_raw_sealed_request_rejects_forged_decision_numeric_policy() -> None:
    with pytest.raises(ValueError, match="DecisionInput numeric policy"):
        _request(
            decision_numeric="forged-numeric-policy-v1",
            policy_numeric=DECISION_NUMERIC_POLICY_ID,
        )


def test_raw_sealed_request_rejects_forged_policy_numeric_policy() -> None:
    with pytest.raises(ValueError, match="DecisionPolicy numeric policy"):
        _request(
            decision_numeric=DECISION_NUMERIC_POLICY_ID,
            policy_numeric="forged-numeric-policy-v1",
        )
