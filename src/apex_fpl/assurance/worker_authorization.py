"""Persist and replay proof that a reference solver was the qualified champion."""

from __future__ import annotations

from dataclasses import dataclass
import json

import yaml

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.reference_solver_registry import ReferenceSolverRegistry
from apex_fpl.core.assurance import ReferenceSolverCertificate
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.ids import ReferenceSolverCertificateId, ReferenceSolverWorkerId
from apex_fpl.core.reference_solver_authorization import ReferenceSolverAuthorization
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)


@dataclass(frozen=True, slots=True)
class StoredReferenceSolverAuthorization:
    authorization: ReferenceSolverAuthorization
    artifact_id: str


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string")
    return value.strip()


def _object(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    return dict(value)


def _workers(value: object) -> list[dict[str, object]]:
    if value is None:
        return []
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError("reference solver workers must be an array of objects")
    return [dict(row) for row in value]


def _registry_from_bytes(content: bytes) -> ReferenceSolverRegistry:
    try:
        payload = yaml.safe_load(content.decode("utf-8")) or {}
    except (UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ValueError("retained reference solver registry is not valid UTF-8 YAML") from exc
    if not isinstance(payload, dict):
        raise ValueError("retained reference solver registry must be object")
    if _strict_int(payload.get("schema_version"), label="registry schema_version") != 1:
        raise ValueError("retained reference solver registry requires schema_version 1")
    season = _text(payload.get("season"), label="registry season")
    workers = tuple(
        ReferenceSolverWorkerArtifact(
            worker_name=str(row.get("worker_name") or ""),
            worker_version=str(row.get("worker_version") or ""),
            solver_contract=str(row.get("solver_contract") or ""),
            code_artifact_id=str(row.get("code_artifact_id") or ""),
            qualification_state=ReferenceSolverWorkerQualification(
                str(row.get("qualification_state") or "")
            ),
            qualification_artifact_id=(
                None
                if row.get("qualification_artifact_id") is None
                else str(row.get("qualification_artifact_id"))
            ),
            valid_seasons=tuple(str(item) for item in (row.get("valid_seasons") or [])),
            first_available_at=str(row.get("first_available_at") or ""),
            max_horizon_gameweeks=_strict_int(
                row.get("max_horizon_gameweeks"),
                label="registry max_horizon_gameweeks",
            ),
        )
        for row in _workers(payload.get("workers"))
    )
    champion_raw = payload.get("champion_worker_id")
    return ReferenceSolverRegistry(
        season=season,
        workers=workers,
        champion_worker_id=(
            None
            if champion_raw is None
            else ReferenceSolverWorkerId(_text(champion_raw, label="champion_worker_id"))
        ),
    )


def _registry_signature(registry: ReferenceSolverRegistry) -> tuple[object, ...]:
    return (
        registry.schema_version,
        registry.season,
        tuple(str(worker.worker_id) for worker in registry.workers),
        None if registry.champion_worker_id is None else str(registry.champion_worker_id),
    )


def create_reference_solver_authorization(
    certificate: ReferenceSolverCertificate,
    *,
    worker_registry: ReferenceSolverRegistry,
    registry_artifact_id: str,
    store: ArtifactStore,
    season: str,
    decision_cutoff: str,
    horizon_gameweeks: int,
) -> StoredReferenceSolverAuthorization:
    """Authorize one certificate against retained exact registry bytes and persist proof."""

    registry_bytes = store.read_bytes(registry_artifact_id)
    retained_registry = _registry_from_bytes(registry_bytes)
    if _registry_signature(retained_registry) != _registry_signature(worker_registry):
        raise ValueError("reference solver registry object does not match retained registry artifact")
    worker = retained_registry.verify_certificate_worker(
        certificate,
        store=store,
        season=season,
        cutoff=decision_cutoff,
        horizon_gameweeks=horizon_gameweeks,
        production=True,
    )
    qualification = worker.qualification_artifact_id
    if qualification is None:
        raise ValueError("qualified reference solver worker lacks qualification artifact")
    for artifact_id in (registry_artifact_id, worker.code_artifact_id, qualification):
        store.read_bytes(artifact_id)
    authorization = ReferenceSolverAuthorization(
        solver_certificate_id=certificate.certificate_id,
        worker_id=worker.worker_id,
        worker_code_artifact_id=worker.code_artifact_id,
        qualification_artifact_id=qualification,
        registry_artifact_id=registry_artifact_id,
        season=season,
        decision_cutoff=decision_cutoff,
        horizon_gameweeks=horizon_gameweeks,
    )
    envelope = {
        "schema_name": "apex-stored-reference-solver-authorization",
        "schema_version": 1,
        "authorization_id": authorization.authorization_id,
        "authorization": authorization.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-reference-solver-authorization",
        schema_version="1",
    )
    return StoredReferenceSolverAuthorization(authorization, ref.artifact_id)


def load_reference_solver_authorization(
    artifact_id: str,
    *,
    certificate: ReferenceSolverCertificate,
    store: ArtifactStore,
) -> StoredReferenceSolverAuthorization:
    """Replay authorization and re-prove champion/qualification from retained registry."""

    try:
        envelope_raw = json.loads(store.read_bytes(artifact_id).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("stored reference solver authorization is not valid UTF-8 JSON") from exc
    envelope = _object(envelope_raw, label="stored reference solver authorization")
    if envelope.get("schema_name") != "apex-stored-reference-solver-authorization":
        raise ValueError("not an Apex stored reference solver authorization")
    if _strict_int(envelope.get("schema_version"), label="authorization schema_version") != 1:
        raise ValueError("unsupported stored reference solver authorization schema")
    raw = _object(envelope.get("authorization"), label="reference solver authorization")
    authorization = ReferenceSolverAuthorization(
        solver_certificate_id=ReferenceSolverCertificateId(
            _text(raw.get("solver_certificate_id"), label="solver_certificate_id")
        ),
        worker_id=ReferenceSolverWorkerId(_text(raw.get("worker_id"), label="worker_id")),
        worker_code_artifact_id=_text(
            raw.get("worker_code_artifact_id"),
            label="worker_code_artifact_id",
        ),
        qualification_artifact_id=_text(
            raw.get("qualification_artifact_id"),
            label="qualification_artifact_id",
        ),
        registry_artifact_id=_text(
            raw.get("registry_artifact_id"),
            label="registry_artifact_id",
        ),
        season=_text(raw.get("season"), label="authorization season"),
        decision_cutoff=_text(raw.get("decision_cutoff"), label="decision_cutoff"),
        horizon_gameweeks=_strict_int(
            raw.get("horizon_gameweeks"),
            label="horizon_gameweeks",
        ),
    )
    declared = _text(envelope.get("authorization_id"), label="declared authorization_id")
    if authorization.authorization_id != declared:
        raise ValueError("stored reference solver authorization semantic identity mismatch")
    if authorization.solver_certificate_id != certificate.certificate_id:
        raise ValueError("reference solver authorization names a different solver certificate")

    registry = _registry_from_bytes(store.read_bytes(authorization.registry_artifact_id))
    worker = registry.verify_certificate_worker(
        certificate,
        store=store,
        season=authorization.season,
        cutoff=authorization.decision_cutoff,
        horizon_gameweeks=authorization.horizon_gameweeks,
        production=True,
    )
    if worker.worker_id != authorization.worker_id:
        raise ValueError("authorization worker identity does not match retained champion")
    if worker.code_artifact_id != authorization.worker_code_artifact_id:
        raise ValueError("authorization worker code artifact does not match retained registry")
    if worker.qualification_artifact_id != authorization.qualification_artifact_id:
        raise ValueError("authorization qualification artifact does not match retained registry")
    for source_id in (
        authorization.registry_artifact_id,
        authorization.worker_code_artifact_id,
        authorization.qualification_artifact_id,
    ):
        store.read_bytes(source_id)
    return StoredReferenceSolverAuthorization(authorization, artifact_id)
