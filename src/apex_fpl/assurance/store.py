"""Strict content-addressed persistence for Slice 10 assurance evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.assurance import (
    AssuranceParityStatus,
    IndependentAssuranceReport,
    ReferenceCheckResult,
    ReferenceMechanicsCertificate,
    ReferenceMechanicsCheck,
    ReferenceSolverCertificate,
    ReferenceSolverStatus,
)
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import DecisionMechanics, RationalValue
from apex_fpl.core.ids import (
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    DecisionPolicyId,
    ForecastId,
    ManagerStateId,
    ReferenceMechanicsCertificateId,
    ReferenceSolverCertificateId,
    RuleSetId,
)


@dataclass(frozen=True, slots=True)
class StoredReferenceMechanicsCertificate:
    certificate: ReferenceMechanicsCertificate
    artifact_id: str


@dataclass(frozen=True, slots=True)
class StoredReferenceSolverCertificate:
    certificate: ReferenceSolverCertificate
    artifact_id: str


@dataclass(frozen=True, slots=True)
class StoredIndependentAssuranceReport:
    report: IndependentAssuranceReport
    artifact_id: str
    mechanics_certificate_artifact_id: str
    solver_certificate_artifact_id: str | None


def _object(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    return dict(value)


def _array(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be array")
    return list(value)


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string")
    return value.strip()


def _int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _json(content: bytes, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    return _object(payload, label=label)


def _rv(value: object, *, label: str) -> RationalValue:
    raw = _object(value, label=label)
    return RationalValue(
        _int(raw.get("numerator"), label=f"{label} numerator"),
        _int(raw.get("denominator"), label=f"{label} denominator"),
    )


def _maybe_rv(value: object, *, label: str) -> RationalValue | None:
    return None if value is None else _rv(value, label=label)


def _mechanics(value: object) -> DecisionMechanics:
    raw = _object(value, label="reference recomputed mechanics")
    return DecisionMechanics(
        xi_points=_rv(raw.get("xi_points"), label="xi_points"),
        autosub_points=_rv(raw.get("autosub_points"), label="autosub_points"),
        captain_bonus=_rv(raw.get("captain_bonus"), label="captain_bonus"),
        squad_points_if_bench_boost=_rv(
            raw.get("squad_points_if_bench_boost"),
            label="squad_points_if_bench_boost",
        ),
        points_before_hits=_rv(raw.get("points_before_hits"), label="points_before_hits"),
        hit_points=_int(raw.get("hit_points"), label="hit_points"),
        objective_points=_rv(raw.get("objective_points"), label="objective_points"),
    )


def store_reference_mechanics_certificate(
    certificate: ReferenceMechanicsCertificate,
    *,
    store: ArtifactStore,
) -> StoredReferenceMechanicsCertificate:
    for source_id in certificate.source_artifact_ids:
        store.read_bytes(source_id)
    envelope = {
        "schema_name": "apex-stored-reference-mechanics-certificate",
        "schema_version": 1,
        "certificate_id": str(certificate.certificate_id),
        "certificate": certificate.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-reference-mechanics-certificate",
        schema_version="1",
    )
    return StoredReferenceMechanicsCertificate(certificate, ref.artifact_id)


def load_reference_mechanics_certificate(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredReferenceMechanicsCertificate:
    envelope = _json(store.read_bytes(artifact_id), label="stored reference mechanics")
    if envelope.get("schema_name") != "apex-stored-reference-mechanics-certificate":
        raise ValueError("not an Apex stored reference mechanics certificate")
    if _int(envelope.get("schema_version"), label="reference mechanics schema_version") != 1:
        raise ValueError("unsupported stored reference mechanics schema")
    raw = _object(envelope.get("certificate"), label="reference mechanics certificate")
    mechanics_raw = raw.get("recomputed_mechanics")
    checks = tuple(
        ReferenceCheckResult(
            check=ReferenceMechanicsCheck(
                _text(_object(item, label="reference check").get("check"), label="reference check name")
            ),
            passed=_bool(
                _object(item, label="reference check").get("passed"),
                label="reference check passed",
            ),
            detail=_text(
                _object(item, label="reference check").get("detail"),
                label="reference check detail",
            ),
        )
        for item in _array(raw.get("checks"), label="reference checks")
    )
    bank_raw = raw.get("recomputed_bank_after_tenths")
    hit_raw = raw.get("recomputed_hit_points")
    certificate = ReferenceMechanicsCertificate(
        decision_id=DecisionId(_text(raw.get("decision_id"), label="decision_id")),
        decision_input_id=DecisionInputId(
            _text(raw.get("decision_input_id"), label="decision_input_id")
        ),
        manager_state_id=ManagerStateId(
            _text(raw.get("manager_state_id"), label="manager_state_id")
        ),
        forecast_id=ForecastId(_text(raw.get("forecast_id"), label="forecast_id")),
        ruleset_id=RuleSetId(_text(raw.get("ruleset_id"), label="ruleset_id")),
        candidate_universe_id=CandidateUniverseId(
            _text(raw.get("candidate_universe_id"), label="candidate_universe_id")
        ),
        action_id=_text(raw.get("action_id"), label="action_id"),
        recomputed_bank_after_tenths=(
            None if bank_raw is None else _int(bank_raw, label="recomputed bank")
        ),
        recomputed_hit_points=(
            None if hit_raw is None else _int(hit_raw, label="recomputed hit")
        ),
        recomputed_mechanics=(None if mechanics_raw is None else _mechanics(mechanics_raw)),
        checks=checks,
        algorithm_id=_text(raw.get("algorithm_id"), label="algorithm_id"),
        source_artifact_ids=tuple(
            _text(item, label="reference source artifact")
            for item in _array(raw.get("source_artifact_ids"), label="reference source artifacts")
        ),
    )
    declared = _text(envelope.get("certificate_id"), label="declared mechanics certificate_id")
    if str(certificate.certificate_id) != declared:
        raise ValueError("stored reference mechanics semantic identity mismatch")
    for source_id in certificate.source_artifact_ids:
        store.read_bytes(source_id)
    return StoredReferenceMechanicsCertificate(certificate, artifact_id)


def store_reference_solver_certificate(
    certificate: ReferenceSolverCertificate,
    *,
    store: ArtifactStore,
) -> StoredReferenceSolverCertificate:
    for source_id in (
        certificate.solver_input_artifact_id,
        certificate.solver_output_artifact_id,
        certificate.worker_artifact_id,
    ):
        store.read_bytes(source_id)
    envelope = {
        "schema_name": "apex-stored-reference-solver-certificate",
        "schema_version": 1,
        "certificate_id": str(certificate.certificate_id),
        "certificate": certificate.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-reference-solver-certificate",
        schema_version="1",
    )
    return StoredReferenceSolverCertificate(certificate, ref.artifact_id)


def load_reference_solver_certificate(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredReferenceSolverCertificate:
    envelope = _json(store.read_bytes(artifact_id), label="stored reference solver")
    if envelope.get("schema_name") != "apex-stored-reference-solver-certificate":
        raise ValueError("not an Apex stored reference solver certificate")
    if _int(envelope.get("schema_version"), label="reference solver schema_version") != 1:
        raise ValueError("unsupported stored reference solver schema")
    raw = _object(envelope.get("certificate"), label="reference solver certificate")
    selected = raw.get("selected_action_id")
    tie = raw.get("tie_break_policy_id")
    certificate = ReferenceSolverCertificate(
        decision_input_id=DecisionInputId(
            _text(raw.get("decision_input_id"), label="solver decision_input_id")
        ),
        candidate_universe_id=CandidateUniverseId(
            _text(raw.get("candidate_universe_id"), label="solver candidate_universe_id")
        ),
        decision_policy_id=DecisionPolicyId(
            _text(raw.get("decision_policy_id"), label="solver decision_policy_id")
        ),
        worker_name=_text(raw.get("worker_name"), label="worker_name"),
        worker_version=_text(raw.get("worker_version"), label="worker_version"),
        solver_status=ReferenceSolverStatus(
            _text(raw.get("solver_status"), label="solver_status")
        ),
        best_objective=_maybe_rv(raw.get("best_objective"), label="best_objective"),
        best_bound=_maybe_rv(raw.get("best_bound"), label="best_bound"),
        gap=_maybe_rv(raw.get("gap"), label="solver gap"),
        selected_action_id=(None if selected is None else _text(selected, label="selected_action_id")),
        action_surface_complete=_bool(
            raw.get("action_surface_complete"), label="action_surface_complete"
        ),
        tie_break_policy_id=(None if tie is None else _text(tie, label="tie_break_policy_id")),
        solver_input_artifact_id=_text(
            raw.get("solver_input_artifact_id"), label="solver_input_artifact_id"
        ),
        solver_output_artifact_id=_text(
            raw.get("solver_output_artifact_id"), label="solver_output_artifact_id"
        ),
        worker_artifact_id=_text(raw.get("worker_artifact_id"), label="worker_artifact_id"),
    )
    declared = _text(envelope.get("certificate_id"), label="declared solver certificate_id")
    if str(certificate.certificate_id) != declared:
        raise ValueError("stored reference solver semantic identity mismatch")
    for source_id in (
        certificate.solver_input_artifact_id,
        certificate.solver_output_artifact_id,
        certificate.worker_artifact_id,
    ):
        store.read_bytes(source_id)
    return StoredReferenceSolverCertificate(certificate, artifact_id)


def store_independent_assurance_report(
    report: IndependentAssuranceReport,
    *,
    mechanics: StoredReferenceMechanicsCertificate,
    solver: StoredReferenceSolverCertificate | None,
    store: ArtifactStore,
) -> StoredIndependentAssuranceReport:
    if mechanics.certificate.certificate_id != report.mechanics_certificate_id:
        raise ValueError("assurance report mechanics certificate identity mismatch")
    if solver is None:
        if report.solver_certificate_id is not None:
            raise ValueError("assurance report names solver certificate but none supplied")
        solver_artifact_id = None
    else:
        if solver.certificate.certificate_id != report.solver_certificate_id:
            raise ValueError("assurance report solver certificate identity mismatch")
        solver_artifact_id = solver.artifact_id
    store.read_bytes(mechanics.artifact_id)
    if solver_artifact_id is not None:
        store.read_bytes(solver_artifact_id)
    for source_id in report.source_artifact_ids:
        store.read_bytes(source_id)
    envelope = {
        "schema_name": "apex-stored-independent-assurance-report",
        "schema_version": 1,
        "report_id": str(report.report_id),
        "mechanics_certificate_artifact_id": mechanics.artifact_id,
        "solver_certificate_artifact_id": solver_artifact_id,
        "report": report.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-independent-assurance-report",
        schema_version="1",
    )
    return StoredIndependentAssuranceReport(
        report,
        ref.artifact_id,
        mechanics.artifact_id,
        solver_artifact_id,
    )


def load_independent_assurance_report(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredIndependentAssuranceReport:
    envelope = _json(store.read_bytes(artifact_id), label="stored independent assurance")
    if envelope.get("schema_name") != "apex-stored-independent-assurance-report":
        raise ValueError("not an Apex stored independent assurance report")
    if _int(envelope.get("schema_version"), label="assurance report schema_version") != 1:
        raise ValueError("unsupported stored independent assurance schema")
    mechanics_artifact = _text(
        envelope.get("mechanics_certificate_artifact_id"),
        label="mechanics certificate artifact",
    )
    solver_artifact_raw = envelope.get("solver_certificate_artifact_id")
    solver_artifact = (
        None
        if solver_artifact_raw is None
        else _text(solver_artifact_raw, label="solver certificate artifact")
    )
    mechanics = load_reference_mechanics_certificate(mechanics_artifact, store=store)
    solver = (
        None
        if solver_artifact is None
        else load_reference_solver_certificate(solver_artifact, store=store)
    )
    raw = _object(envelope.get("report"), label="independent assurance report")
    solver_id_raw = raw.get("solver_certificate_id")
    report = IndependentAssuranceReport(
        decision_id=DecisionId(_text(raw.get("decision_id"), label="assurance decision_id")),
        mechanics_certificate_id=ReferenceMechanicsCertificateId(
            _text(raw.get("mechanics_certificate_id"), label="mechanics certificate_id")
        ),
        mechanics_passed=_bool(raw.get("mechanics_passed"), label="mechanics_passed"),
        solver_certificate_id=(
            None
            if solver_id_raw is None
            else ReferenceSolverCertificateId(
                _text(solver_id_raw, label="solver certificate_id")
            )
        ),
        solver_parity_status=AssuranceParityStatus(
            _text(raw.get("solver_parity_status"), label="solver parity status")
        ),
        blockers=tuple(
            _text(item, label="assurance blocker")
            for item in _array(raw.get("blockers"), label="assurance blockers")
        ),
        source_artifact_ids=tuple(
            _text(item, label="assurance source artifact")
            for item in _array(raw.get("source_artifact_ids"), label="assurance source artifacts")
        ),
    )
    declared = _text(envelope.get("report_id"), label="declared assurance report_id")
    if str(report.report_id) != declared:
        raise ValueError("stored independent assurance semantic identity mismatch")
    if mechanics.certificate.certificate_id != report.mechanics_certificate_id:
        raise ValueError("stored assurance mechanics certificate does not match report")
    if solver is None:
        if report.solver_certificate_id is not None:
            raise ValueError("stored assurance solver certificate is missing")
    elif solver.certificate.certificate_id != report.solver_certificate_id:
        raise ValueError("stored assurance solver certificate does not match report")
    for source_id in report.source_artifact_ids:
        store.read_bytes(source_id)
    return StoredIndependentAssuranceReport(
        report,
        artifact_id,
        mechanics_artifact,
        solver_artifact,
    )
