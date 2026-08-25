"""Independent replay of production backend qualification evidence."""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.core.production import ProductionBackendQualification


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def load_production_backend_qualification(
    artifact_id: str,
    *,
    artifact_store: ArtifactStore,
) -> ProductionBackendQualification:
    """Replay one qualification snapshot and verify its semantic identity/evidence."""

    try:
        raw = json.loads(artifact_store.read_bytes(artifact_id).decode("utf-8"))
    except ArtifactIntegrityError as exc:
        raise ValueError("production backend qualification failed integrity verification") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("production backend qualification is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("production backend qualification artifact must be JSON object")
    if (
        raw.get("schema_name") != "apex-stored-production-backend-qualification"
        or raw.get("schema_version") != 1
    ):
        raise ValueError("unsupported production backend qualification schema")
    payload = raw.get("payload")
    declared = raw.get("qualification_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("production backend qualification payload/identity is invalid")
    bool_fields = (
        "durable_shared_artifact_store",
        "durable_shared_release_registry",
        "atomic_compare_and_swap",
        "immutable_release_history",
    )
    if any(not isinstance(payload.get(name), bool) for name in bool_fields):
        raise ValueError("production backend qualification booleans must be typed")
    qualification = ProductionBackendQualification(
        artifact_store_backend_id=str(payload.get("artifact_store_backend_id") or ""),
        release_registry_backend_id=str(payload.get("release_registry_backend_id") or ""),
        artifact_store_qualification_artifact_id=str(
            payload.get("artifact_store_qualification_artifact_id") or ""
        ),
        release_registry_qualification_artifact_id=str(
            payload.get("release_registry_qualification_artifact_id") or ""
        ),
        durable_shared_artifact_store=payload["durable_shared_artifact_store"],
        durable_shared_release_registry=payload["durable_shared_release_registry"],
        atomic_compare_and_swap=payload["atomic_compare_and_swap"],
        immutable_release_history=payload["immutable_release_history"],
        qualification_scope=str(payload.get("qualification_scope") or ""),
        schema_version=_strict_int(payload.get("schema_version"), label="backend schema_version"),
    )
    if qualification.qualification_id != declared:
        raise ValueError("production backend qualification semantic identity mismatch")
    for evidence_id in (
        qualification.artifact_store_qualification_artifact_id,
        qualification.release_registry_qualification_artifact_id,
    ):
        if not artifact_store.verify(evidence_id):
            raise ValueError(
                f"production backend qualification evidence is missing/corrupt: {evidence_id}"
            )
    return qualification
