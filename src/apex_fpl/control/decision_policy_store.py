"""Immutable storage and strict replay for exact DecisionPolicy semantics."""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision_policy import (
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from apex_fpl.core.ids import DecisionPolicyId


def _object(content: bytes) -> dict[str, object]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("DecisionPolicy artifact is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("DecisionPolicy artifact must be a JSON object")
    return dict(value)


def _int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{label} must be string or null")
    return value


def store_decision_policy(policy: DecisionPolicy, *, store: ArtifactStore) -> str:
    """Store semantic bytes so the ArtifactStore ID is exactly DecisionPolicyId."""

    ref = store.put_bytes(
        canonical_json_bytes(policy.semantic_payload()),
        media_type="application/json",
        schema_name="apex-decision-policy",
        schema_version=str(policy.schema_version),
    )
    if ref.artifact_id != str(policy.decision_policy_id):
        raise ValueError("stored DecisionPolicy content identity does not match semantic identity")
    return ref.artifact_id


def load_decision_policy(
    policy_id: DecisionPolicyId | str,
    *,
    store: ArtifactStore,
) -> DecisionPolicy:
    """Replay one DecisionPolicy directly from its semantic content identity."""

    expected = DecisionPolicyId(str(policy_id))
    raw = _object(store.read_bytes(str(expected)))
    if raw.get("schema_name") != "apex-decision-policy":
        raise ValueError("not an Apex DecisionPolicy artifact")
    schema_version = _int(raw.get("schema_version"), label="DecisionPolicy schema_version")
    policy = DecisionPolicy(
        policy_name=str(raw.get("policy_name") or ""),
        policy_version=str(raw.get("policy_version") or ""),
        season=str(raw.get("season") or ""),
        qualification_state=DecisionPolicyQualificationState(
            str(raw.get("qualification_state") or "")
        ),
        qualification_artifact_id=_optional_text(
            raw.get("qualification_artifact_id"),
            label="DecisionPolicy qualification_artifact_id",
        ),
        first_available_at=str(raw.get("first_available_at") or ""),
        evaluation_mode=DecisionEvaluationMode(str(raw.get("evaluation_mode") or "")),
        objective_policy=DecisionObjectivePolicy(str(raw.get("objective_policy") or "")),
        horizon_gameweeks=_int(
            raw.get("horizon_gameweeks"), label="DecisionPolicy horizon_gameweeks"
        ),
        continuation_value_artifact_id=_optional_text(
            raw.get("continuation_value_artifact_id"),
            label="DecisionPolicy continuation_value_artifact_id",
        ),
        chip_option_value_artifact_id=_optional_text(
            raw.get("chip_option_value_artifact_id"),
            label="DecisionPolicy chip_option_value_artifact_id",
        ),
        price_policy_artifact_id=_optional_text(
            raw.get("price_policy_artifact_id"),
            label="DecisionPolicy price_policy_artifact_id",
        ),
        candidate_policy_artifact_id=_optional_text(
            raw.get("candidate_policy_artifact_id"),
            label="DecisionPolicy candidate_policy_artifact_id",
        ),
        tie_break_policy=str(raw.get("tie_break_policy") or ""),
        numeric_policy_id=str(raw.get("numeric_policy_id") or ""),
        schema_version=schema_version,
    )
    if policy.decision_policy_id != expected:
        raise ValueError("DecisionPolicy semantic identity mismatch")
    return policy
