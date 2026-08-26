"""Immutable operator materialization for V2 empirical qualification candidates.

This module creates reviewable content-addressed candidate artifacts. It never edits a registry,
sets a champion, or fabricates empirical qualification. A SHADOW candidate may later be rebuilt as
QUALIFIED only from a replay-valid SUPPORTED certificate for the exact stable qualification subject.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import json
from typing import Mapping

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.decision_policy_support import (
    load_candidate_policy,
    load_chip_option_value_policy,
    load_continuation_value_policy,
    load_price_policy,
)
from apex_fpl.control.experiment_registry import load_empirical_qualification_certificate
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision_policy import (
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from apex_fpl.core.experiments import EmpiricalQualificationDecision, qualification_subject_id
from apex_fpl.core.forecast import ForecastModelArtifact, ModelQualificationState
from apex_fpl.core.numeric_policy import DECISION_NUMERIC_POLICY_ID


_FORECAST_SCHEMA = "apex-stored-forecast-model-candidate"
_POLICY_SCHEMA = "apex-stored-decision-policy-candidate"
_FORECAST_SUBJECT_KIND = "apex.forecast-model"
_POLICY_SUBJECT_KIND = "apex.decision-policy"
_FORECAST_PROOF_ID = "PO-FORECAST-QUALIFICATION-001"
_POLICY_PROOF_ID = "PO-DECISION-POLICY-QUALIFICATION-001"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _required_text(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    values = tuple(str(item).strip() for item in value if str(item).strip())
    if not values:
        raise ValueError(f"{label} cannot be empty")
    return values


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


def _read_object(artifact_id: str, *, store: ArtifactStore) -> dict[str, object]:
    if not store.verify(artifact_id):
        raise ValueError(f"candidate artifact missing/corrupt: {artifact_id}")
    content = store.read_bytes(artifact_id)
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("candidate artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != content:
        raise ValueError("candidate artifact must be canonical JSON object")
    return raw


def _verify_sources(store: ArtifactStore, artifact_ids: tuple[str, ...]) -> None:
    for artifact_id in artifact_ids:
        if not store.verify(artifact_id):
            raise ValueError(f"candidate source artifact missing/corrupt: {artifact_id}")


@dataclass(frozen=True, slots=True)
class CandidateMaterialization:
    candidate_kind: str
    candidate_artifact_id: str
    candidate_id: str
    subject_kind: str
    subject_id: str
    season: str
    created_at: str
    qualification_state: str
    qualification_artifact_id: str | None
    registry_row: dict[str, object]

    def operator_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-candidate-materialization-result",
            "schema_version": 1,
            "candidate_kind": self.candidate_kind,
            "candidate_artifact_id": self.candidate_artifact_id,
            "candidate_id": self.candidate_id,
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "season": self.season,
            "created_at": self.created_at,
            "qualification_state": self.qualification_state,
            "qualification_artifact_id": self.qualification_artifact_id,
            "registry_row": self.registry_row,
            "review_required": True,
            "champion_changed": False,
        }


def _forecast_registry_row(model: ForecastModelArtifact) -> dict[str, object]:
    return {
        "model_name": model.model_name,
        "model_version": model.model_version,
        "feature_contract": model.feature_contract,
        "prediction_contract": model.prediction_contract,
        "parameter_artifact_ids": list(model.parameter_artifact_ids),
        "qualification_state": model.qualification_state.value,
        "qualification_artifact_id": model.qualification_artifact_id,
        "valid_seasons": list(model.valid_seasons),
        "trained_through": model.trained_through,
        "first_available_at": model.first_available_at,
        "max_horizon_gameweeks": model.max_horizon_gameweeks,
    }


def _policy_registry_row(policy: DecisionPolicy) -> dict[str, object]:
    return {
        "policy_name": policy.policy_name,
        "policy_version": policy.policy_version,
        "season": policy.season,
        "qualification_state": policy.qualification_state.value,
        "qualification_artifact_id": policy.qualification_artifact_id,
        "first_available_at": policy.first_available_at,
        "evaluation_mode": policy.evaluation_mode.value,
        "objective_policy": policy.objective_policy.value,
        "horizon_gameweeks": policy.horizon_gameweeks,
        "continuation_value_artifact_id": policy.continuation_value_artifact_id,
        "chip_option_value_artifact_id": policy.chip_option_value_artifact_id,
        "price_policy_artifact_id": policy.price_policy_artifact_id,
        "candidate_policy_artifact_id": policy.candidate_policy_artifact_id,
        "tie_break_policy": policy.tie_break_policy,
        "numeric_policy_id": policy.numeric_policy_id,
    }


def _store_forecast_candidate(
    model: ForecastModelArtifact,
    *,
    qualification_season: str,
    source_artifact_ids: tuple[str, ...],
    created_at: str,
    store: ArtifactStore,
) -> CandidateMaterialization:
    season = _required_text(qualification_season, label="qualification_season")
    if season not in model.valid_seasons:
        raise ValueError("qualification_season is not in forecast model valid_seasons")
    subject_id = qualification_subject_id(model.semantic_payload())
    registry_row = _forecast_registry_row(model)
    sources = tuple(sorted(set(source_artifact_ids)))
    _verify_sources(store, sources)
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": _FORECAST_SCHEMA,
                "schema_version": 1,
                "candidate_id": str(model.model_artifact_id),
                "subject_kind": _FORECAST_SUBJECT_KIND,
                "subject_id": subject_id,
                "qualification_season": season,
                "created_at": created_at,
                "source_artifact_ids": list(sources),
                "registry_row": registry_row,
                "payload": model.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name=_FORECAST_SCHEMA,
        schema_version="1",
    )
    return CandidateMaterialization(
        candidate_kind="FORECAST_MODEL",
        candidate_artifact_id=ref.artifact_id,
        candidate_id=str(model.model_artifact_id),
        subject_kind=_FORECAST_SUBJECT_KIND,
        subject_id=subject_id,
        season=season,
        created_at=created_at,
        qualification_state=model.qualification_state.value,
        qualification_artifact_id=model.qualification_artifact_id,
        registry_row=registry_row,
    )


def materialize_forecast_model_candidate(
    spec: Mapping[str, object],
    *,
    store: ArtifactStore,
) -> CandidateMaterialization:
    """Create one SHADOW forecast-model candidate using operator-recorded availability time."""

    created_at = _utc_now()
    parameter_ids = _string_tuple(spec.get("parameter_artifact_ids"), label="parameter_artifact_ids")
    _verify_sources(store, parameter_ids)
    valid_seasons = _string_tuple(spec.get("valid_seasons"), label="valid_seasons")
    model = ForecastModelArtifact(
        model_name=_required_text(spec.get("model_name"), label="model_name"),
        model_version=_required_text(spec.get("model_version"), label="model_version"),
        feature_contract=_required_text(spec.get("feature_contract"), label="feature_contract"),
        prediction_contract=_required_text(
            spec.get("prediction_contract"), label="prediction_contract"
        ),
        parameter_artifact_ids=parameter_ids,
        qualification_state=ModelQualificationState.SHADOW,
        qualification_artifact_id=None,
        valid_seasons=valid_seasons,
        trained_through=_required_text(spec.get("trained_through"), label="trained_through"),
        first_available_at=created_at,
        max_horizon_gameweeks=_positive_int(
            spec.get("max_horizon_gameweeks"), label="max_horizon_gameweeks"
        ),
    )
    return _store_forecast_candidate(
        model,
        qualification_season=_required_text(
            spec.get("qualification_season"), label="qualification_season"
        ),
        source_artifact_ids=parameter_ids,
        created_at=created_at,
        store=store,
    )


def _load_forecast_candidate(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> tuple[ForecastModelArtifact, CandidateMaterialization, tuple[str, ...]]:
    raw = _read_object(artifact_id, store=store)
    if raw.get("schema_name") != _FORECAST_SCHEMA or raw.get("schema_version") != 1:
        raise ValueError("artifact is not a stored forecast-model candidate")
    payload = raw.get("payload")
    registry_row = raw.get("registry_row")
    sources = raw.get("source_artifact_ids")
    if not isinstance(payload, dict) or not isinstance(registry_row, dict):
        raise ValueError("forecast candidate payload/registry_row is invalid")
    source_ids = _string_tuple(sources, label="source_artifact_ids")
    model = ForecastModelArtifact(
        model_name=_required_text(payload.get("model_name"), label="model_name"),
        model_version=_required_text(payload.get("model_version"), label="model_version"),
        feature_contract=_required_text(payload.get("feature_contract"), label="feature_contract"),
        prediction_contract=_required_text(
            payload.get("prediction_contract"), label="prediction_contract"
        ),
        parameter_artifact_ids=_string_tuple(
            payload.get("parameter_artifact_ids"), label="parameter_artifact_ids"
        ),
        qualification_state=ModelQualificationState(
            _required_text(payload.get("qualification_state"), label="qualification_state")
        ),
        qualification_artifact_id=(
            None
            if payload.get("qualification_artifact_id") is None
            else _required_text(
                payload.get("qualification_artifact_id"), label="qualification_artifact_id"
            )
        ),
        valid_seasons=_string_tuple(payload.get("valid_seasons"), label="valid_seasons"),
        trained_through=_required_text(payload.get("trained_through"), label="trained_through"),
        first_available_at=_required_text(
            payload.get("first_available_at"), label="first_available_at"
        ),
        max_horizon_gameweeks=_positive_int(
            payload.get("max_horizon_gameweeks"), label="max_horizon_gameweeks"
        ),
        schema_version=_positive_int(payload.get("schema_version"), label="schema_version"),
    )
    candidate_id = str(model.model_artifact_id)
    subject_id = qualification_subject_id(model.semantic_payload())
    season = _required_text(raw.get("qualification_season"), label="qualification_season")
    created_at = _required_text(raw.get("created_at"), label="created_at")
    if raw.get("candidate_id") != candidate_id or raw.get("subject_id") != subject_id:
        raise ValueError("forecast candidate semantic identity mismatch")
    if raw.get("subject_kind") != _FORECAST_SUBJECT_KIND:
        raise ValueError("forecast candidate subject_kind mismatch")
    if registry_row != _forecast_registry_row(model):
        raise ValueError("forecast candidate registry row does not reconcile")
    if set(source_ids) != set(model.parameter_artifact_ids) and model.qualification_artifact_id is None:
        raise ValueError("forecast candidate source lineage does not reconcile")
    _verify_sources(store, source_ids)
    material = CandidateMaterialization(
        candidate_kind="FORECAST_MODEL",
        candidate_artifact_id=artifact_id,
        candidate_id=candidate_id,
        subject_kind=_FORECAST_SUBJECT_KIND,
        subject_id=subject_id,
        season=season,
        created_at=created_at,
        qualification_state=model.qualification_state.value,
        qualification_artifact_id=model.qualification_artifact_id,
        registry_row=registry_row,
    )
    return model, material, source_ids


def _validate_policy_supports(policy: DecisionPolicy, *, store: ArtifactStore) -> tuple[str, ...]:
    support_ids = (
        policy.continuation_value_artifact_id,
        policy.chip_option_value_artifact_id,
        policy.price_policy_artifact_id,
        policy.candidate_policy_artifact_id,
    )
    if any(value is None for value in support_ids):
        raise ValueError("receding-horizon policy lacks complete support artifacts")
    continuation_id, chip_id, price_id, candidate_id = support_ids
    assert continuation_id and chip_id and price_id and candidate_id
    continuation = load_continuation_value_policy(
        continuation_id, store=store, as_of=policy.first_available_at
    )
    chip = load_chip_option_value_policy(chip_id, store=store, as_of=policy.first_available_at)
    price = load_price_policy(price_id, store=store, as_of=policy.first_available_at)
    candidate = load_candidate_policy(candidate_id, store=store, as_of=policy.first_available_at)
    supports = (continuation, chip, price, candidate)
    if any(item.season != policy.season for item in supports):
        raise ValueError("DecisionPolicy support artifact season mismatch")
    if continuation.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("DecisionPolicy continuation-value horizon mismatch")
    if chip.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("DecisionPolicy chip-option horizon mismatch")
    return tuple(str(value) for value in support_ids)


def _store_policy_candidate(
    policy: DecisionPolicy,
    *,
    source_artifact_ids: tuple[str, ...],
    created_at: str,
    store: ArtifactStore,
) -> CandidateMaterialization:
    subject_id = qualification_subject_id(policy.semantic_payload())
    registry_row = _policy_registry_row(policy)
    sources = tuple(sorted(set(source_artifact_ids)))
    _verify_sources(store, sources)
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": _POLICY_SCHEMA,
                "schema_version": 1,
                "candidate_id": str(policy.decision_policy_id),
                "subject_kind": _POLICY_SUBJECT_KIND,
                "subject_id": subject_id,
                "qualification_season": policy.season,
                "created_at": created_at,
                "source_artifact_ids": list(sources),
                "registry_row": registry_row,
                "payload": policy.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name=_POLICY_SCHEMA,
        schema_version="1",
    )
    return CandidateMaterialization(
        candidate_kind="DECISION_POLICY",
        candidate_artifact_id=ref.artifact_id,
        candidate_id=str(policy.decision_policy_id),
        subject_kind=_POLICY_SUBJECT_KIND,
        subject_id=subject_id,
        season=policy.season,
        created_at=created_at,
        qualification_state=policy.qualification_state.value,
        qualification_artifact_id=policy.qualification_artifact_id,
        registry_row=registry_row,
    )


def materialize_decision_policy_candidate(
    spec: Mapping[str, object],
    *,
    store: ArtifactStore,
) -> CandidateMaterialization:
    """Create one SHADOW receding-horizon DecisionPolicy candidate."""

    created_at = _utc_now()
    policy = DecisionPolicy(
        policy_name=_required_text(spec.get("policy_name"), label="policy_name"),
        policy_version=_required_text(spec.get("policy_version"), label="policy_version"),
        season=_required_text(spec.get("season"), label="season"),
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at=created_at,
        evaluation_mode=DecisionEvaluationMode(
            _required_text(spec.get("evaluation_mode"), label="evaluation_mode")
        ),
        objective_policy=DecisionObjectivePolicy(
            _required_text(spec.get("objective_policy"), label="objective_policy")
        ),
        horizon_gameweeks=_positive_int(spec.get("horizon_gameweeks"), label="horizon_gameweeks"),
        continuation_value_artifact_id=_required_text(
            spec.get("continuation_value_artifact_id"), label="continuation_value_artifact_id"
        ),
        chip_option_value_artifact_id=_required_text(
            spec.get("chip_option_value_artifact_id"), label="chip_option_value_artifact_id"
        ),
        price_policy_artifact_id=_required_text(
            spec.get("price_policy_artifact_id"), label="price_policy_artifact_id"
        ),
        candidate_policy_artifact_id=_required_text(
            spec.get("candidate_policy_artifact_id"), label="candidate_policy_artifact_id"
        ),
        tie_break_policy=_required_text(spec.get("tie_break_policy"), label="tie_break_policy"),
        numeric_policy_id=_required_text(
            spec.get("numeric_policy_id", DECISION_NUMERIC_POLICY_ID), label="numeric_policy_id"
        ),
    )
    if policy.evaluation_mode is not DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION:
        raise ValueError("production candidate materialization requires receding-horizon policy")
    supports = _validate_policy_supports(policy, store=store)
    return _store_policy_candidate(
        policy,
        source_artifact_ids=supports,
        created_at=created_at,
        store=store,
    )


def _load_policy_candidate(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> tuple[DecisionPolicy, CandidateMaterialization, tuple[str, ...]]:
    raw = _read_object(artifact_id, store=store)
    if raw.get("schema_name") != _POLICY_SCHEMA or raw.get("schema_version") != 1:
        raise ValueError("artifact is not a stored DecisionPolicy candidate")
    payload = raw.get("payload")
    registry_row = raw.get("registry_row")
    if not isinstance(payload, dict) or not isinstance(registry_row, dict):
        raise ValueError("DecisionPolicy candidate payload/registry_row is invalid")
    source_ids = _string_tuple(raw.get("source_artifact_ids"), label="source_artifact_ids")
    policy = DecisionPolicy(
        policy_name=_required_text(payload.get("policy_name"), label="policy_name"),
        policy_version=_required_text(payload.get("policy_version"), label="policy_version"),
        season=_required_text(payload.get("season"), label="season"),
        qualification_state=DecisionPolicyQualificationState(
            _required_text(payload.get("qualification_state"), label="qualification_state")
        ),
        qualification_artifact_id=(
            None
            if payload.get("qualification_artifact_id") is None
            else _required_text(
                payload.get("qualification_artifact_id"), label="qualification_artifact_id"
            )
        ),
        first_available_at=_required_text(
            payload.get("first_available_at"), label="first_available_at"
        ),
        evaluation_mode=DecisionEvaluationMode(
            _required_text(payload.get("evaluation_mode"), label="evaluation_mode")
        ),
        objective_policy=DecisionObjectivePolicy(
            _required_text(payload.get("objective_policy"), label="objective_policy")
        ),
        horizon_gameweeks=_positive_int(
            payload.get("horizon_gameweeks"), label="horizon_gameweeks"
        ),
        continuation_value_artifact_id=_required_text(
            payload.get("continuation_value_artifact_id"), label="continuation_value_artifact_id"
        ),
        chip_option_value_artifact_id=_required_text(
            payload.get("chip_option_value_artifact_id"), label="chip_option_value_artifact_id"
        ),
        price_policy_artifact_id=_required_text(
            payload.get("price_policy_artifact_id"), label="price_policy_artifact_id"
        ),
        candidate_policy_artifact_id=_required_text(
            payload.get("candidate_policy_artifact_id"), label="candidate_policy_artifact_id"
        ),
        tie_break_policy=_required_text(payload.get("tie_break_policy"), label="tie_break_policy"),
        numeric_policy_id=_required_text(payload.get("numeric_policy_id"), label="numeric_policy_id"),
        schema_version=_positive_int(payload.get("schema_version"), label="schema_version"),
    )
    candidate_id = str(policy.decision_policy_id)
    subject_id = qualification_subject_id(policy.semantic_payload())
    created_at = _required_text(raw.get("created_at"), label="created_at")
    if raw.get("candidate_id") != candidate_id or raw.get("subject_id") != subject_id:
        raise ValueError("DecisionPolicy candidate semantic identity mismatch")
    if raw.get("subject_kind") != _POLICY_SUBJECT_KIND:
        raise ValueError("DecisionPolicy candidate subject_kind mismatch")
    if raw.get("qualification_season") != policy.season:
        raise ValueError("DecisionPolicy candidate season mismatch")
    if registry_row != _policy_registry_row(policy):
        raise ValueError("DecisionPolicy candidate registry row does not reconcile")
    supports = _validate_policy_supports(policy, store=store)
    if not set(supports).issubset(set(source_ids)):
        raise ValueError("DecisionPolicy candidate source lineage does not reconcile")
    _verify_sources(store, source_ids)
    material = CandidateMaterialization(
        candidate_kind="DECISION_POLICY",
        candidate_artifact_id=artifact_id,
        candidate_id=candidate_id,
        subject_kind=_POLICY_SUBJECT_KIND,
        subject_id=subject_id,
        season=policy.season,
        created_at=created_at,
        qualification_state=policy.qualification_state.value,
        qualification_artifact_id=policy.qualification_artifact_id,
        registry_row=registry_row,
    )
    return policy, material, source_ids


def load_candidate_materialization(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> CandidateMaterialization:
    raw = _read_object(artifact_id, store=store)
    schema = raw.get("schema_name")
    if schema == _FORECAST_SCHEMA:
        return _load_forecast_candidate(artifact_id, store=store)[1]
    if schema == _POLICY_SCHEMA:
        return _load_policy_candidate(artifact_id, store=store)[1]
    raise ValueError("artifact is not a supported V2 empirical candidate")


def materialize_qualified_candidate(
    candidate_artifact_id: str,
    qualification_artifact_id: str,
    *,
    store: ArtifactStore,
) -> CandidateMaterialization:
    """Attach a replay-valid SUPPORTED certificate without changing any champion registry."""

    now = _utc_now()
    material = load_candidate_materialization(candidate_artifact_id, store=store)
    if material.qualification_state != "SHADOW" or material.qualification_artifact_id is not None:
        raise ValueError("only an unqualified SHADOW candidate may be qualified")
    certificate = load_empirical_qualification_certificate(
        qualification_artifact_id,
        store=store,
        as_of=now,
    )
    if certificate.decision is not EmpiricalQualificationDecision.SUPPORTED:
        raise ValueError("candidate qualification certificate is not SUPPORTED")
    if certificate.subject_kind != material.subject_kind:
        raise ValueError("candidate qualification subject_kind mismatch")
    if certificate.subject_id != material.subject_id:
        raise ValueError("candidate qualification subject identity mismatch")
    if certificate.season != material.season:
        raise ValueError("candidate qualification season mismatch")
    expected_proof = (
        _FORECAST_PROOF_ID
        if material.candidate_kind == "FORECAST_MODEL"
        else _POLICY_PROOF_ID
    )
    if certificate.proof_id != expected_proof:
        raise ValueError("candidate qualification proof_id mismatch")

    if material.candidate_kind == "FORECAST_MODEL":
        model, _, source_ids = _load_forecast_candidate(candidate_artifact_id, store=store)
        qualified = replace(
            model,
            qualification_state=ModelQualificationState.QUALIFIED,
            qualification_artifact_id=qualification_artifact_id,
        )
        return _store_forecast_candidate(
            qualified,
            qualification_season=material.season,
            source_artifact_ids=tuple(
                sorted({*source_ids, candidate_artifact_id, qualification_artifact_id})
            ),
            created_at=now,
            store=store,
        )

    policy, _, source_ids = _load_policy_candidate(candidate_artifact_id, store=store)
    qualified_policy = replace(
        policy,
        qualification_state=DecisionPolicyQualificationState.QUALIFIED,
        qualification_artifact_id=qualification_artifact_id,
    )
    return _store_policy_candidate(
        qualified_policy,
        source_artifact_ids=tuple(
            sorted({*source_ids, candidate_artifact_id, qualification_artifact_id})
        ),
        created_at=now,
        store=store,
    )
