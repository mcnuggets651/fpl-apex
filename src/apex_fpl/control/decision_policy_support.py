"""Canonical storage/replay for typed V2 DecisionPolicy support artifacts."""

from __future__ import annotations

from datetime import datetime
import json
from typing import TypeVar

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision_policy_support import (
    CandidatePolicy,
    CandidatePolicyMode,
    ChipOptionValueMode,
    ChipOptionValuePolicy,
    ContinuationValueMode,
    ContinuationValuePolicy,
    ExactPolicyValue,
    PricePolicy,
    PricePolicyMode,
)


PolicySupport = ContinuationValuePolicy | ChipOptionValuePolicy | PricePolicy | CandidatePolicy
T = TypeVar("T", bound=PolicySupport)


def _read_object(artifact_id: str, *, store: ArtifactStore, label: str) -> dict[str, object]:
    try:
        raw = store.read_bytes(artifact_id)
    except (ArtifactIntegrityError, FileNotFoundError, ValueError) as exc:
        raise ValueError(f"{label} artifact failed integrity verification") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} artifact is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact must be an object")
    if canonical_json_bytes(payload) != raw:
        raise ValueError(f"{label} artifact is not canonical JSON")
    return payload


def _exact(value: object, *, label: str) -> ExactPolicyValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an exact rational object")
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if isinstance(numerator, bool) or not isinstance(numerator, int):
        raise ValueError(f"{label} numerator must be integer")
    if isinstance(denominator, bool) or not isinstance(denominator, int):
        raise ValueError(f"{label} denominator must be integer")
    return ExactPolicyValue(numerator, denominator)


def _require_available(first_available_at: str, *, as_of: str | None, label: str) -> None:
    if as_of is None:
        return
    try:
        available = datetime.fromisoformat(first_available_at.replace("Z", "+00:00"))
        point = datetime.fromisoformat(str(as_of).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} as_of must be ISO-8601") from exc
    if point.tzinfo is None or point.utcoffset() is None:
        raise ValueError(f"{label} as_of must be timezone-aware")
    if available > point:
        raise ValueError(f"{label} was not available at as_of")


def store_decision_policy_support(policy: PolicySupport, *, store: ArtifactStore) -> str:
    """Store exact semantic JSON; artifact identity must equal the policy semantic identity."""

    ref = store.put_bytes(
        canonical_json_bytes(policy.semantic_payload()),
        media_type="application/json",
        schema_name=str(policy.semantic_payload()["schema_name"]),
        schema_version=str(policy.schema_version),
    )
    if ref.artifact_id != policy.policy_id:
        raise ValueError("DecisionPolicy support semantic/content identity mismatch")
    return ref.artifact_id


def load_continuation_value_policy(
    artifact_id: str,
    *,
    store: ArtifactStore,
    as_of: str | None = None,
) -> ContinuationValuePolicy:
    payload = _read_object(artifact_id, store=store, label="continuation-value policy")
    if payload.get("schema_name") != "apex-decision-continuation-value-policy":
        raise ValueError("artifact is not a continuation-value policy")
    weights = payload.get("gameweek_weights")
    if not isinstance(weights, list):
        raise ValueError("continuation-value gameweek_weights must be an array")
    policy = ContinuationValuePolicy(
        season=str(payload.get("season") or ""),
        horizon_gameweeks=payload.get("horizon_gameweeks"),  # type: ignore[arg-type]
        first_available_at=str(payload.get("first_available_at") or ""),
        gameweek_weights=tuple(
            _exact(row, label="continuation-value weight") for row in weights
        ),
        terminal_value=_exact(payload.get("terminal_value"), label="terminal value"),
        mode=ContinuationValueMode(str(payload.get("mode") or "")),
        schema_version=payload.get("schema_version"),  # type: ignore[arg-type]
    )
    if policy.policy_id != artifact_id:
        raise ValueError("continuation-value policy semantic identity mismatch")
    _require_available(policy.first_available_at, as_of=as_of, label="continuation-value policy")
    return policy


def load_chip_option_value_policy(
    artifact_id: str,
    *,
    store: ArtifactStore,
    as_of: str | None = None,
) -> ChipOptionValuePolicy:
    payload = _read_object(artifact_id, store=store, label="chip-option policy")
    if payload.get("schema_name") != "apex-decision-chip-option-value-policy":
        raise ValueError("artifact is not a chip-option policy")
    raw_values = payload.get("option_values")
    if not isinstance(raw_values, list):
        raise ValueError("chip-option option_values must be an array")
    values: list[tuple[str, ExactPolicyValue]] = []
    for row in raw_values:
        if not isinstance(row, dict):
            raise ValueError("chip-option value row must be an object")
        values.append(
            (
                str(row.get("chip") or ""),
                _exact(row.get("value"), label="chip-option value"),
            )
        )
    policy = ChipOptionValuePolicy(
        season=str(payload.get("season") or ""),
        horizon_gameweeks=payload.get("horizon_gameweeks"),  # type: ignore[arg-type]
        first_available_at=str(payload.get("first_available_at") or ""),
        option_values=tuple(values),
        mode=ChipOptionValueMode(str(payload.get("mode") or "")),
        schema_version=payload.get("schema_version"),  # type: ignore[arg-type]
    )
    if policy.policy_id != artifact_id:
        raise ValueError("chip-option policy semantic identity mismatch")
    _require_available(policy.first_available_at, as_of=as_of, label="chip-option policy")
    return policy


def load_price_policy(
    artifact_id: str,
    *,
    store: ArtifactStore,
    as_of: str | None = None,
) -> PricePolicy:
    payload = _read_object(artifact_id, store=store, label="price policy")
    if payload.get("schema_name") != "apex-decision-price-policy":
        raise ValueError("artifact is not a price policy")
    policy = PricePolicy(
        season=str(payload.get("season") or ""),
        first_available_at=str(payload.get("first_available_at") or ""),
        mode=PricePolicyMode(str(payload.get("mode") or "")),
        schema_version=payload.get("schema_version"),  # type: ignore[arg-type]
    )
    if policy.policy_id != artifact_id:
        raise ValueError("price policy semantic identity mismatch")
    _require_available(policy.first_available_at, as_of=as_of, label="price policy")
    return policy


def load_candidate_policy(
    artifact_id: str,
    *,
    store: ArtifactStore,
    as_of: str | None = None,
) -> CandidatePolicy:
    payload = _read_object(artifact_id, store=store, label="candidate policy")
    if payload.get("schema_name") != "apex-decision-candidate-policy":
        raise ValueError("artifact is not a candidate policy")
    policy = CandidatePolicy(
        season=str(payload.get("season") or ""),
        first_available_at=str(payload.get("first_available_at") or ""),
        mode=CandidatePolicyMode(str(payload.get("mode") or "")),
        schema_version=payload.get("schema_version"),  # type: ignore[arg-type]
    )
    if policy.policy_id != artifact_id:
        raise ValueError("candidate policy semantic identity mismatch")
    _require_available(policy.first_available_at, as_of=as_of, label="candidate policy")
    return policy
