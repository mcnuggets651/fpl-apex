"""Canonical operator path for prospective/no-hindsight empirical qualification.

The pure experiment contracts retain explicit timestamps for replay. This operational layer does
not accept caller-authored declaration or result times: it records UTC at execution, refuses to
start an already-open evaluation window, refuses outcomes before the window closes, and keeps
qualification distinct from candidate/champion promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Mapping

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.candidate_operations import (
    CandidateMaterialization,
    load_candidate_materialization,
)
from apex_fpl.control.experiment_registry import (
    ExperimentRegistration,
    ExperimentRegistry,
    derive_empirical_qualification_certificate,
    load_empirical_qualification_certificate,
    load_experiment_definition,
    load_experiment_registry_artifact,
    load_experiment_result,
    store_empirical_qualification_certificate,
    store_experiment_definition,
    store_experiment_registry,
    store_experiment_result,
)
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.experiments import (
    EmpiricalQualificationDecision,
    ExactQualificationValue,
    ExperimentDefinition,
    ExperimentResult,
    QualificationMetricDirection,
    QualificationMetricResult,
    QualificationMetricRule,
)


_DECLARATION_SCHEMA = "apex-prospective-experiment-declaration"
_PROOF_BY_CANDIDATE_KIND = {
    "FORECAST_MODEL": "PO-FORECAST-QUALIFICATION-001",
    "DECISION_POLICY": "PO-DECISION-POLICY-QUALIFICATION-001",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _instant(value: str, *, label: str) -> datetime:
    try:
        point = datetime.fromisoformat(str(value).strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if point.tzinfo is None or point.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return point.astimezone(timezone.utc)


def _required_text(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} is required")
    return text


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a string array")
    values = tuple(str(item).strip() for item in value if str(item).strip())
    if not values:
        raise ValueError(f"{label} cannot be empty")
    return values


def _exact(value: object, *, label: str) -> ExactQualificationValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    numerator = value.get("numerator")
    denominator = value.get("denominator")
    if isinstance(numerator, bool) or not isinstance(numerator, int):
        raise ValueError(f"{label} numerator must be integer")
    if isinstance(denominator, bool) or not isinstance(denominator, int):
        raise ValueError(f"{label} denominator must be integer")
    return ExactQualificationValue(numerator, denominator)


def _metric_rules(value: object) -> tuple[QualificationMetricRule, ...]:
    if not isinstance(value, list) or not value or any(not isinstance(item, dict) for item in value):
        raise ValueError("metric_rules must be a non-empty object array")
    return tuple(
        QualificationMetricRule(
            metric_id=_required_text(item.get("metric_id"), label="metric_id"),
            direction=QualificationMetricDirection(
                _required_text(item.get("direction"), label="metric direction")
            ),
            threshold=_exact(item.get("threshold"), label="metric threshold"),
        )
        for item in value
    )


def _metric_results(value: object) -> tuple[QualificationMetricResult, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("metrics must be an object array")
    return tuple(
        QualificationMetricResult(
            metric_id=_required_text(item.get("metric_id"), label="metric_id"),
            value=_exact(item.get("value"), label="metric value"),
        )
        for item in value
    )


def _read_canonical_object(artifact_id: str, *, store: ArtifactStore) -> dict[str, object]:
    if not store.verify(artifact_id):
        raise ValueError(f"prospective declaration artifact missing/corrupt: {artifact_id}")
    content = store.read_bytes(artifact_id)
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("prospective declaration is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or canonical_json_bytes(raw) != content:
        raise ValueError("prospective declaration must be canonical JSON object")
    return raw


@dataclass(frozen=True, slots=True)
class ProspectiveExperimentDeclaration:
    candidate_artifact_id: str
    experiment_id: str
    definition_artifact_id: str
    registry_artifact_id: str
    declared_at: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProspectiveExperimentDeclaration schema")
        for field in (
            "candidate_artifact_id",
            "experiment_id",
            "definition_artifact_id",
            "registry_artifact_id",
            "declared_at",
        ):
            object.__setattr__(
                self,
                field,
                _required_text(getattr(self, field), label=field),
            )
        _instant(self.declared_at, label="declared_at")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": _DECLARATION_SCHEMA,
            "schema_version": self.schema_version,
            "candidate_artifact_id": self.candidate_artifact_id,
            "experiment_id": self.experiment_id,
            "definition_artifact_id": self.definition_artifact_id,
            "registry_artifact_id": self.registry_artifact_id,
            "declared_at": self.declared_at,
        }

    @property
    def declaration_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ExperimentDeclarationMaterialization:
    declaration: ProspectiveExperimentDeclaration
    declaration_artifact_id: str
    definition: ExperimentDefinition

    def operator_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-experiment-declaration-result",
            "schema_version": 1,
            "declaration_id": self.declaration.declaration_id,
            "declaration_artifact_id": self.declaration_artifact_id,
            "experiment_id": self.definition.experiment_id,
            "definition_artifact_id": self.declaration.definition_artifact_id,
            "registry_artifact_id": self.declaration.registry_artifact_id,
            "declared_at": self.definition.declared_at,
            "evaluation_window_start": self.definition.evaluation_window_start,
            "evaluation_window_end": self.definition.evaluation_window_end,
            "valid_until": self.definition.valid_until,
            "prospective": True,
        }


@dataclass(frozen=True, slots=True)
class ExperimentResultMaterialization:
    result: ExperimentResult
    result_artifact_id: str

    def operator_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-experiment-result-materialization",
            "schema_version": 1,
            "experiment_id": self.result.experiment_id,
            "result_id": self.result.result_id,
            "result_artifact_id": self.result_artifact_id,
            "evaluated_at": self.result.evaluated_at,
            "sample_size": self.result.sample_size,
        }


@dataclass(frozen=True, slots=True)
class QualificationMaterialization:
    certificate_artifact_id: str
    certificate_id: str
    decision: str
    blockers: tuple[str, ...]
    subject_kind: str
    subject_id: str
    season: str

    def operator_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-qualification-materialization",
            "schema_version": 1,
            "certificate_artifact_id": self.certificate_artifact_id,
            "certificate_id": self.certificate_id,
            "decision": self.decision,
            "blockers": list(self.blockers),
            "subject_kind": self.subject_kind,
            "subject_id": self.subject_id,
            "season": self.season,
            "champion_changed": False,
        }


def _store_declaration(
    declaration: ProspectiveExperimentDeclaration,
    *,
    store: ArtifactStore,
) -> str:
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                **declaration.semantic_payload(),
                "declaration_id": declaration.declaration_id,
            }
        ),
        media_type="application/json",
        schema_name=_DECLARATION_SCHEMA,
        schema_version="1",
    )
    return ref.artifact_id


def load_prospective_experiment_declaration(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> tuple[ProspectiveExperimentDeclaration, ExperimentDefinition, CandidateMaterialization]:
    raw = _read_canonical_object(artifact_id, store=store)
    if raw.get("schema_name") != _DECLARATION_SCHEMA or raw.get("schema_version") != 1:
        raise ValueError("artifact is not a prospective experiment declaration")
    declaration = ProspectiveExperimentDeclaration(
        candidate_artifact_id=_required_text(
            raw.get("candidate_artifact_id"), label="candidate_artifact_id"
        ),
        experiment_id=_required_text(raw.get("experiment_id"), label="experiment_id"),
        definition_artifact_id=_required_text(
            raw.get("definition_artifact_id"), label="definition_artifact_id"
        ),
        registry_artifact_id=_required_text(
            raw.get("registry_artifact_id"), label="registry_artifact_id"
        ),
        declared_at=_required_text(raw.get("declared_at"), label="declared_at"),
        schema_version=1,
    )
    if raw.get("declaration_id") != declaration.declaration_id:
        raise ValueError("prospective experiment declaration identity mismatch")
    definition = load_experiment_definition(declaration.definition_artifact_id, store=store)
    candidate = load_candidate_materialization(declaration.candidate_artifact_id, store=store)
    registry = load_experiment_registry_artifact(declaration.registry_artifact_id, store=store)
    registration = registry.get(definition.experiment_id)
    if registration is None or registration.definition_artifact_id != declaration.definition_artifact_id:
        raise ValueError("prospective declaration registry does not retain exact definition")
    if definition.experiment_id != declaration.experiment_id:
        raise ValueError("prospective declaration experiment identity mismatch")
    if definition.declared_at != declaration.declared_at:
        raise ValueError("prospective declaration timestamp does not reconcile")
    if definition.subject_id != candidate.subject_id:
        raise ValueError("prospective declaration candidate subject mismatch")
    if definition.subject_kind != candidate.subject_kind or definition.season != candidate.season:
        raise ValueError("prospective declaration candidate scope mismatch")
    return declaration, definition, candidate


def declare_candidate_experiment(
    candidate_artifact_id: str,
    spec: Mapping[str, object],
    *,
    store: ArtifactStore,
) -> ExperimentDeclarationMaterialization:
    """Seal an experiment before its window opens, using runtime UTC for declaration time."""

    candidate = load_candidate_materialization(candidate_artifact_id, store=store)
    if candidate.qualification_state != "SHADOW" or candidate.qualification_artifact_id is not None:
        raise ValueError("prospective qualification must start from an unqualified SHADOW candidate")
    expected_proof = _PROOF_BY_CANDIDATE_KIND.get(candidate.candidate_kind)
    if expected_proof is None:
        raise ValueError("candidate kind is not supported for prospective qualification")
    supplied_proof = spec.get("proof_id")
    if supplied_proof is not None and str(supplied_proof).strip() != expected_proof:
        raise ValueError("experiment proof_id does not match candidate kind")

    evaluator_id = _required_text(spec.get("evaluator_artifact_id"), label="evaluator_artifact_id")
    policy_id = _required_text(spec.get("policy_artifact_id"), label="policy_artifact_id")
    for artifact_id in (evaluator_id, policy_id):
        if not store.verify(artifact_id):
            raise ValueError(f"experiment control artifact missing/corrupt: {artifact_id}")

    declared_at = _utc_now()
    window_start = _required_text(
        spec.get("evaluation_window_start"), label="evaluation_window_start"
    )
    if _instant(declared_at, label="declared_at") >= _instant(
        window_start, label="evaluation_window_start"
    ):
        raise ValueError("prospective experiment must be sealed before evaluation window starts")

    definition = ExperimentDefinition(
        proof_id=expected_proof,
        subject_kind=candidate.subject_kind,
        subject_id=candidate.subject_id,
        season=candidate.season,
        evaluator_artifact_id=evaluator_id,
        policy_artifact_id=policy_id,
        declared_at=declared_at,
        evaluation_window_start=window_start,
        evaluation_window_end=_required_text(
            spec.get("evaluation_window_end"), label="evaluation_window_end"
        ),
        minimum_sample_size=_positive_int(
            spec.get("minimum_sample_size"), label="minimum_sample_size"
        ),
        metric_rules=_metric_rules(spec.get("metric_rules")),
        valid_until=_required_text(spec.get("valid_until"), label="valid_until"),
    )
    definition_ref = store_experiment_definition(definition, store=store)

    existing_registry_id = spec.get("registry_artifact_id")
    if existing_registry_id is None:
        registrations: tuple[ExperimentRegistration, ...] = ()
    else:
        existing_registry = load_experiment_registry_artifact(
            _required_text(existing_registry_id, label="registry_artifact_id"),
            store=store,
        )
        if existing_registry.season != candidate.season:
            raise ValueError("existing ExperimentRegistry season mismatch")
        if existing_registry.get(definition.experiment_id) is not None:
            raise ValueError("experiment is already registered; do not redeclare it")
        registrations = existing_registry.registrations

    registry = ExperimentRegistry(
        season=candidate.season,
        registrations=(
            *registrations,
            ExperimentRegistration(
                experiment_id=definition.experiment_id,
                definition_artifact_id=definition_ref.artifact_id,
            ),
        ),
    )
    registry_ref = store_experiment_registry(registry, store=store)
    declaration = ProspectiveExperimentDeclaration(
        candidate_artifact_id=candidate_artifact_id,
        experiment_id=definition.experiment_id,
        definition_artifact_id=definition_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        declared_at=declared_at,
    )
    declaration_artifact_id = _store_declaration(declaration, store=store)
    return ExperimentDeclarationMaterialization(
        declaration=declaration,
        declaration_artifact_id=declaration_artifact_id,
        definition=definition,
    )


def record_candidate_experiment_result(
    declaration_artifact_id: str,
    spec: Mapping[str, object],
    *,
    store: ArtifactStore,
) -> ExperimentResultMaterialization:
    """Seal post-window outcome evidence; caller cannot provide evaluated_at."""

    _, definition, _ = load_prospective_experiment_declaration(
        declaration_artifact_id,
        store=store,
    )
    evaluated_at = _utc_now()
    now = _instant(evaluated_at, label="evaluated_at")
    if now < _instant(definition.evaluation_window_end, label="evaluation_window_end"):
        raise ValueError("experiment outcome cannot be finalized before evaluation window ends")
    if now > _instant(definition.valid_until, label="valid_until"):
        raise ValueError("experiment outcome cannot be finalized after experiment validity expires")

    source_ids = _string_tuple(spec.get("source_artifact_ids"), label="source_artifact_ids")
    for artifact_id in source_ids:
        if not store.verify(artifact_id):
            raise ValueError(f"experiment result source missing/corrupt: {artifact_id}")
    result = ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=definition.proof_id,
        subject_kind=definition.subject_kind,
        subject_id=definition.subject_id,
        season=definition.season,
        evaluator_artifact_id=definition.evaluator_artifact_id,
        evaluated_at=evaluated_at,
        sample_size=(
            spec.get("sample_size")
            if isinstance(spec.get("sample_size"), int) and not isinstance(spec.get("sample_size"), bool)
            else -1
        ),
        metrics=_metric_results(spec.get("metrics")),
        source_artifact_ids=source_ids,
    )
    result_ref = store_experiment_result(result, store=store)
    return ExperimentResultMaterialization(result=result, result_artifact_id=result_ref.artifact_id)


def derive_candidate_qualification(
    declaration_artifact_id: str,
    result_artifact_id: str,
    *,
    store: ArtifactStore,
) -> QualificationMaterialization:
    """Derive and replay a certificate. This function never promotes or changes a champion."""

    declaration, definition, candidate = load_prospective_experiment_declaration(
        declaration_artifact_id,
        store=store,
    )
    result = load_experiment_result(result_artifact_id, store=store)
    if result.experiment_id != definition.experiment_id:
        raise ValueError("qualification result does not belong to prospective declaration")
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=declaration.definition_artifact_id,
        result_artifact_id=result_artifact_id,
        registry_artifact_id=declaration.registry_artifact_id,
        store=store,
    )
    if certificate.subject_id != candidate.subject_id or certificate.subject_kind != candidate.subject_kind:
        raise ValueError("derived qualification does not bind exact candidate subject")
    certificate_ref = store_empirical_qualification_certificate(certificate, store=store)
    replayed = load_empirical_qualification_certificate(
        certificate_ref.artifact_id,
        store=store,
        as_of=_utc_now(),
    )
    if replayed.semantic_payload() != certificate.semantic_payload():
        raise ValueError("stored qualification certificate failed exact replay")
    return QualificationMaterialization(
        certificate_artifact_id=certificate_ref.artifact_id,
        certificate_id=certificate.certificate_id,
        decision=certificate.decision.value,
        blockers=certificate.blockers,
        subject_kind=certificate.subject_kind,
        subject_id=certificate.subject_id,
        season=certificate.season,
    )


def qualification_supported(materialization: QualificationMaterialization) -> bool:
    return materialization.decision == EmpiricalQualificationDecision.SUPPORTED.value
