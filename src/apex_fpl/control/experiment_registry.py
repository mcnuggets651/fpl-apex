"""Immutable ExperimentRegistry and replay-derived empirical qualification evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

import yaml

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.experiments import (
    EmpiricalQualificationCertificate,
    EmpiricalQualificationDecision,
    ExactQualificationValue,
    ExperimentDefinition,
    ExperimentResult,
    QualificationMetricDirection,
    QualificationMetricResult,
    QualificationMetricRule,
)


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _string(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty string")
    return value.strip()


def _string_tuple(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be string array")
    return tuple(value)


def _aware_instant(value: str, *, label: str) -> datetime:
    text = _string(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _read_json_object(
    artifact_id: str,
    *,
    store: ArtifactStore,
    schema_name: str,
) -> dict[str, object]:
    try:
        content = store.read_bytes(artifact_id)
    except (FileNotFoundError, ArtifactIntegrityError, ValueError) as exc:
        raise ValueError(f"{schema_name} artifact missing/corrupt: {artifact_id}") from exc
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{schema_name} artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{schema_name} artifact must be JSON object")
    if raw.get("schema_name") != schema_name or raw.get("schema_version") != 1:
        raise ValueError(f"unsupported {schema_name} schema")
    return raw


def _metric_value(value: object, *, label: str) -> ExactQualificationValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    return ExactQualificationValue(
        _strict_int(value.get("numerator"), label=f"{label} numerator"),
        _strict_int(value.get("denominator"), label=f"{label} denominator"),
    )


def _metric_rules(value: object) -> tuple[QualificationMetricRule, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("experiment metric_rules must be object array")
    return tuple(
        QualificationMetricRule(
            metric_id=_string(item.get("metric_id"), label="metric_id"),
            direction=QualificationMetricDirection(
                _string(item.get("direction"), label="metric direction")
            ),
            threshold=_metric_value(item.get("threshold"), label="metric threshold"),
        )
        for item in value
    )


def _metric_results(value: object) -> tuple[QualificationMetricResult, ...]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("experiment metrics must be object array")
    return tuple(
        QualificationMetricResult(
            metric_id=_string(item.get("metric_id"), label="metric_id"),
            value=_metric_value(item.get("value"), label="metric value"),
        )
        for item in value
    )


@dataclass(frozen=True, slots=True)
class ExperimentRegistration:
    experiment_id: str
    definition_artifact_id: str

    def __post_init__(self) -> None:
        if not str(self.experiment_id).strip():
            raise ValueError("experiment registration requires experiment_id")
        if not str(self.definition_artifact_id).strip():
            raise ValueError("experiment registration requires definition_artifact_id")

    def semantic_payload(self) -> dict[str, str]:
        return {
            "experiment_id": self.experiment_id,
            "definition_artifact_id": self.definition_artifact_id,
        }


@dataclass(frozen=True, slots=True)
class ExperimentRegistry:
    season: str
    registrations: tuple[ExperimentRegistration, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ExperimentRegistry schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("ExperimentRegistry requires season")
        registrations = tuple(sorted(self.registrations, key=lambda row: row.experiment_id))
        ids = [row.experiment_id for row in registrations]
        if len(ids) != len(set(ids)):
            raise ValueError("ExperimentRegistry contains duplicate experiment identities")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "registrations", registrations)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-experiment-registry",
            "schema_version": self.schema_version,
            "season": self.season,
            "registrations": [row.semantic_payload() for row in self.registrations],
        }

    @property
    def registry_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    def get(self, experiment_id: str) -> ExperimentRegistration | None:
        return next(
            (row for row in self.registrations if row.experiment_id == experiment_id),
            None,
        )


def load_experiment_registry(path: str | Path) -> ExperimentRegistry:
    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict) or _strict_int(
        payload.get("schema_version"), label="schema_version"
    ) != 1:
        raise ValueError("ExperimentRegistry requires schema_version 1")
    season = _string(payload.get("season"), label="ExperimentRegistry season")
    rows = payload.get("experiments")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("ExperimentRegistry experiments must be object array")
    return ExperimentRegistry(
        season=season,
        registrations=tuple(
            ExperimentRegistration(
                experiment_id=_string(row.get("experiment_id"), label="experiment_id"),
                definition_artifact_id=_string(
                    row.get("definition_artifact_id"),
                    label="definition_artifact_id",
                ),
            )
            for row in rows
        ),
    )


def store_experiment_definition(
    definition: ExperimentDefinition,
    *,
    store: ArtifactStore,
):
    return store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-experiment-definition",
                "schema_version": 1,
                "experiment_id": definition.experiment_id,
                "payload": definition.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-experiment-definition",
        schema_version="1",
    )


def load_experiment_definition(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ExperimentDefinition:
    raw = _read_json_object(
        artifact_id,
        store=store,
        schema_name="apex-stored-experiment-definition",
    )
    payload = raw.get("payload")
    declared = raw.get("experiment_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("stored ExperimentDefinition payload/identity is invalid")
    definition = ExperimentDefinition(
        proof_id=_string(payload.get("proof_id"), label="proof_id"),
        subject_kind=_string(payload.get("subject_kind"), label="subject_kind"),
        subject_id=_string(payload.get("subject_id"), label="subject_id"),
        season=_string(payload.get("season"), label="season"),
        evaluator_artifact_id=_string(
            payload.get("evaluator_artifact_id"), label="evaluator_artifact_id"
        ),
        policy_artifact_id=_string(
            payload.get("policy_artifact_id"), label="policy_artifact_id"
        ),
        declared_at=_string(payload.get("declared_at"), label="declared_at"),
        evaluation_window_start=_string(
            payload.get("evaluation_window_start"), label="evaluation_window_start"
        ),
        evaluation_window_end=_string(
            payload.get("evaluation_window_end"), label="evaluation_window_end"
        ),
        minimum_sample_size=_strict_int(
            payload.get("minimum_sample_size"), label="minimum_sample_size"
        ),
        metric_rules=_metric_rules(payload.get("metric_rules")),
        valid_until=_string(payload.get("valid_until"), label="valid_until"),
        schema_version=_strict_int(
            payload.get("schema_version"), label="definition schema_version"
        ),
    )
    if definition.experiment_id != declared:
        raise ValueError("ExperimentDefinition semantic identity mismatch")
    for source_id in (definition.evaluator_artifact_id, definition.policy_artifact_id):
        if not store.verify(source_id):
            raise ValueError("ExperimentDefinition source artifact missing/corrupt")
    return definition


def store_experiment_result(
    result: ExperimentResult,
    *,
    store: ArtifactStore,
):
    return store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-experiment-result",
                "schema_version": 1,
                "result_id": result.result_id,
                "payload": result.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-experiment-result",
        schema_version="1",
    )


def load_experiment_result(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ExperimentResult:
    raw = _read_json_object(
        artifact_id,
        store=store,
        schema_name="apex-stored-experiment-result",
    )
    payload = raw.get("payload")
    declared = raw.get("result_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("stored ExperimentResult payload/identity is invalid")
    result = ExperimentResult(
        experiment_id=_string(payload.get("experiment_id"), label="experiment_id"),
        proof_id=_string(payload.get("proof_id"), label="proof_id"),
        subject_kind=_string(payload.get("subject_kind"), label="subject_kind"),
        subject_id=_string(payload.get("subject_id"), label="subject_id"),
        season=_string(payload.get("season"), label="season"),
        evaluator_artifact_id=_string(
            payload.get("evaluator_artifact_id"), label="evaluator_artifact_id"
        ),
        evaluated_at=_string(payload.get("evaluated_at"), label="evaluated_at"),
        sample_size=_strict_int(payload.get("sample_size"), label="sample_size"),
        metrics=_metric_results(payload.get("metrics")),
        source_artifact_ids=_string_tuple(
            payload.get("source_artifact_ids"), label="source_artifact_ids"
        ),
        schema_version=_strict_int(payload.get("schema_version"), label="result schema_version"),
    )
    if result.result_id != declared:
        raise ValueError("ExperimentResult semantic identity mismatch")
    for source_id in result.source_artifact_ids:
        if not store.verify(source_id):
            raise ValueError("ExperimentResult source artifact missing/corrupt")
    if not store.verify(result.evaluator_artifact_id):
        raise ValueError("ExperimentResult evaluator artifact missing/corrupt")
    return result


def store_experiment_registry(
    registry: ExperimentRegistry,
    *,
    store: ArtifactStore,
):
    return store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-experiment-registry",
                "schema_version": 1,
                "registry_id": registry.registry_id,
                "payload": registry.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-experiment-registry",
        schema_version="1",
    )


def load_experiment_registry_artifact(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ExperimentRegistry:
    raw = _read_json_object(
        artifact_id,
        store=store,
        schema_name="apex-stored-experiment-registry",
    )
    payload = raw.get("payload")
    declared = raw.get("registry_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("stored ExperimentRegistry payload/identity is invalid")
    rows = payload.get("registrations")
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError("stored ExperimentRegistry registrations must be object array")
    registry = ExperimentRegistry(
        season=_string(payload.get("season"), label="registry season"),
        registrations=tuple(
            ExperimentRegistration(
                experiment_id=_string(row.get("experiment_id"), label="experiment_id"),
                definition_artifact_id=_string(
                    row.get("definition_artifact_id"), label="definition_artifact_id"
                ),
            )
            for row in rows
        ),
        schema_version=_strict_int(payload.get("schema_version"), label="registry schema_version"),
    )
    if registry.registry_id != declared:
        raise ValueError("ExperimentRegistry semantic identity mismatch")
    for registration in registry.registrations:
        definition = load_experiment_definition(
            registration.definition_artifact_id,
            store=store,
        )
        if definition.experiment_id != registration.experiment_id:
            raise ValueError("ExperimentRegistry definition identity mismatch")
        if definition.season != registry.season:
            raise ValueError("ExperimentRegistry definition season mismatch")
    return registry


def _derive_decision(
    definition: ExperimentDefinition,
    result: ExperimentResult,
) -> tuple[EmpiricalQualificationDecision, tuple[str, ...]]:
    blockers: list[str] = []
    if result.experiment_id != definition.experiment_id:
        blockers.append("experiment result references different experiment")
    if result.proof_id != definition.proof_id:
        blockers.append("experiment result proof_id mismatch")
    if result.subject_kind != definition.subject_kind:
        blockers.append("experiment result subject_kind mismatch")
    if result.subject_id != definition.subject_id:
        blockers.append("experiment result subject_id mismatch")
    if result.season != definition.season:
        blockers.append("experiment result season mismatch")
    if result.evaluator_artifact_id != definition.evaluator_artifact_id:
        blockers.append("experiment result evaluator identity mismatch")
    if result.evaluated_at < definition.evaluation_window_end:
        blockers.append("experiment result was finalized before evaluation window ended")
    if result.evaluated_at > definition.valid_until:
        blockers.append("experiment result was finalized after experiment validity expired")
    if result.sample_size < definition.minimum_sample_size:
        blockers.append(
            f"insufficient sample: {result.sample_size} < {definition.minimum_sample_size}"
        )

    values = {row.metric_id: row.value for row in result.metrics}
    rule_ids = {row.metric_id for row in definition.metric_rules}
    unknown = sorted(set(values) - rule_ids)
    missing = sorted(rule_ids - set(values))
    if unknown:
        blockers.append(f"unexpected experiment metrics: {unknown}")
    if missing:
        blockers.append(f"missing experiment metrics: {missing}")
    failed_metrics = sorted(
        rule.metric_id
        for rule in definition.metric_rules
        if rule.metric_id in values and not rule.satisfied_by(values[rule.metric_id])
    )
    if failed_metrics:
        blockers.append(f"qualification thresholds failed: {failed_metrics}")

    if not blockers:
        return EmpiricalQualificationDecision.SUPPORTED, ()
    if any(
        blocker.startswith("insufficient sample")
        or blocker.startswith("missing experiment metrics")
        for blocker in blockers
    ):
        return EmpiricalQualificationDecision.INCONCLUSIVE, tuple(blockers)
    return EmpiricalQualificationDecision.REJECTED, tuple(blockers)


def derive_empirical_qualification_certificate(
    *,
    definition_artifact_id: str,
    result_artifact_id: str,
    registry_artifact_id: str,
    store: ArtifactStore,
) -> EmpiricalQualificationCertificate:
    registry = load_experiment_registry_artifact(registry_artifact_id, store=store)
    definition = load_experiment_definition(definition_artifact_id, store=store)
    registration = registry.get(definition.experiment_id)
    if registration is None:
        raise ValueError("experiment is not registered")
    if registration.definition_artifact_id != definition_artifact_id:
        raise ValueError("registered experiment definition artifact does not match supplied definition")
    if definition.season != registry.season:
        raise ValueError("experiment registry/definition season mismatch")
    result = load_experiment_result(result_artifact_id, store=store)
    decision, blockers = _derive_decision(definition, result)
    sources = tuple(
        sorted(
            {
                registry_artifact_id,
                definition_artifact_id,
                result_artifact_id,
                definition.evaluator_artifact_id,
                definition.policy_artifact_id,
                *result.source_artifact_ids,
            }
        )
    )
    return EmpiricalQualificationCertificate(
        proof_id=definition.proof_id,
        subject_kind=definition.subject_kind,
        subject_id=definition.subject_id,
        season=definition.season,
        experiment_id=definition.experiment_id,
        experiment_definition_artifact_id=definition_artifact_id,
        result_id=result.result_id,
        result_artifact_id=result_artifact_id,
        decision=decision,
        blockers=blockers,
        source_artifact_ids=sources,
        first_available_at=result.evaluated_at,
        valid_until=definition.valid_until,
    )


def store_empirical_qualification_certificate(
    certificate: EmpiricalQualificationCertificate,
    *,
    store: ArtifactStore,
):
    return store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-stored-empirical-qualification-certificate",
                "schema_version": 1,
                "certificate_id": certificate.certificate_id,
                "payload": certificate.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-stored-empirical-qualification-certificate",
        schema_version="1",
    )


def load_empirical_qualification_certificate(
    artifact_id: str,
    *,
    store: ArtifactStore,
    as_of: str | None = None,
) -> EmpiricalQualificationCertificate:
    raw = _read_json_object(
        artifact_id,
        store=store,
        schema_name="apex-stored-empirical-qualification-certificate",
    )
    payload = raw.get("payload")
    declared = raw.get("certificate_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("stored empirical qualification payload/identity is invalid")
    certificate = EmpiricalQualificationCertificate(
        proof_id=_string(payload.get("proof_id"), label="proof_id"),
        subject_kind=_string(payload.get("subject_kind"), label="subject_kind"),
        subject_id=_string(payload.get("subject_id"), label="subject_id"),
        season=_string(payload.get("season"), label="season"),
        experiment_id=_string(payload.get("experiment_id"), label="experiment_id"),
        experiment_definition_artifact_id=_string(
            payload.get("experiment_definition_artifact_id"),
            label="experiment_definition_artifact_id",
        ),
        result_id=_string(payload.get("result_id"), label="result_id"),
        result_artifact_id=_string(
            payload.get("result_artifact_id"), label="result_artifact_id"
        ),
        decision=EmpiricalQualificationDecision(
            _string(payload.get("decision"), label="qualification decision")
        ),
        blockers=_string_tuple(payload.get("blockers"), label="qualification blockers"),
        source_artifact_ids=_string_tuple(
            payload.get("source_artifact_ids"), label="qualification source artifacts"
        ),
        first_available_at=_string(
            payload.get("first_available_at"), label="first_available_at"
        ),
        valid_until=_string(payload.get("valid_until"), label="valid_until"),
        schema_version=_strict_int(payload.get("schema_version"), label="certificate schema_version"),
    )
    if certificate.certificate_id != declared:
        raise ValueError("empirical qualification certificate semantic identity mismatch")
    for source_id in certificate.source_artifact_ids:
        if not store.verify(source_id):
            raise ValueError("empirical qualification source artifact missing/corrupt")

    replayable_registries = []
    for source_id in certificate.source_artifact_ids:
        try:
            registry = load_experiment_registry_artifact(source_id, store=store)
        except ValueError:
            continue
        replayable_registries.append((source_id, registry))
    if len(replayable_registries) != 1:
        raise ValueError("empirical qualification must retain exactly one replayable ExperimentRegistry")
    registry_artifact_id, _ = replayable_registries[0]
    derived = derive_empirical_qualification_certificate(
        definition_artifact_id=certificate.experiment_definition_artifact_id,
        result_artifact_id=certificate.result_artifact_id,
        registry_artifact_id=registry_artifact_id,
        store=store,
    )
    if derived.semantic_payload() != certificate.semantic_payload():
        raise ValueError("empirical qualification certificate does not re-derive from retained evidence")
    if as_of is not None:
        current = _aware_instant(as_of, label="qualification as_of")
        first = _aware_instant(
            certificate.first_available_at,
            label="qualification first_available_at",
        )
        expiry = _aware_instant(certificate.valid_until, label="qualification valid_until")
        if current < first:
            raise ValueError("empirical qualification was not yet available at as_of")
        if current > expiry:
            raise ValueError("empirical qualification has expired")
    return certificate
