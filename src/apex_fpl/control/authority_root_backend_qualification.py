"""Mechanical qualification and strict replay for the authority-root registry.

This qualification is intentionally separate from the previously certified production
ArtifactStore/ReleaseRegistry contract. A backend cannot inherit authority-root CAS trust
from older release-registry evidence that never exercised this control-plane capability.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.authority_root_registry import AuthorityRootCompareAndSwapConflict
from apex_fpl.control.backend_ports import ReopenableAuthorityRootRegistry
from apex_fpl.core.authority_root_backend_qualification import AuthorityRootRegistryQualification
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot


@dataclass(frozen=True, slots=True)
class StoredAuthorityRootRegistryQualification:
    qualification: AuthorityRootRegistryQualification
    artifact_id: str


def _text(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _strict_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _backend_id(value: object, *, label: str) -> str:
    backend_id = getattr(value, "backend_id", None)
    if not isinstance(backend_id, str) or not backend_id.strip():
        raise ValueError(f"{label} has no stable backend identity")
    return backend_id.strip()


def _hash(label: str, seed: str) -> str:
    return canonical_sha256(
        {
            "schema_name": "apex-authority-root-registry-probe-member",
            "schema_version": 1,
            "label": label,
            "seed": seed,
        }
    )


def _probe_root(
    *,
    season: str,
    generation: int,
    parent_root_artifact_id: str | None,
    seed: str,
) -> ProductionAuthorityRoot:
    return ProductionAuthorityRoot(
        season=season,
        generation=generation,
        parent_root_artifact_id=parent_root_artifact_id,
        champion_generation_artifact_id=_hash("champion", seed),
        ruleset_artifact_id=_hash("ruleset-artifact", seed),
        ruleset_id=_hash("ruleset", seed),
        learning_policy_registry_artifact_id=_hash("learning-registry", seed),
        learning_policy_id=_hash("learning-policy", seed),
        outcome_truth_registry_artifact_id=_hash("truth-registry-artifact", seed),
        outcome_truth_registry_id=_hash("truth-registry", seed),
        build_manifest_artifact_id=_hash("build-manifest-artifact", seed),
        build_manifest_id=_hash("build-manifest", seed),
        change_control_artifact_id=_hash("change-control", seed),
        authorized_by="apex-authority-root-registry-probe",
        authorized_at="2000-01-01T00:00:00+00:00",
        valid_from="2000-01-01T00:00:00+00:00",
        valid_until="2100-01-01T00:00:00+00:00",
        reason=f"authority-root registry operational probe {seed}",
    )


def qualify_authority_root_registry(
    registry: ReopenableAuthorityRootRegistry,
    *,
    store: ArtifactStore,
    qualification_scope: str,
    probe_nonce: str,
) -> StoredAuthorityRootRegistryQualification:
    """Exercise shared visibility, immutable history and stale-writer-safe CAS."""

    scope = _text(qualification_scope, label="authority-root qualification scope")
    nonce = _text(probe_nonce, label="authority-root probe nonce")
    backend_id = _backend_id(registry, label="AuthorityRootRegistry")
    key_digest = canonical_sha256(
        {
            "schema_name": "apex-authority-root-registry-probe-key",
            "schema_version": 1,
            "qualification_scope": scope,
            "probe_nonce": nonce,
        }
    )
    probe_season = f"apex-authority-root-qualification-{key_digest[7:27]}"
    if registry.current_root_id(probe_season) is not None:
        raise ValueError("authority-root qualification probe season already has current root")

    first = _probe_root(
        season=probe_season,
        generation=1,
        parent_root_artifact_id=None,
        seed=f"{key_digest}:first",
    )
    second = _probe_root(
        season=probe_season,
        generation=2,
        parent_root_artifact_id=first.root_id,
        seed=f"{key_digest}:second",
    )
    stale_candidate = _probe_root(
        season=probe_season,
        generation=2,
        parent_root_artifact_id=first.root_id,
        seed=f"{key_digest}:stale",
    )
    registry.append(first)
    registry.append(second)
    registry.append(stale_candidate)

    reopened = registry.reopen()
    reopened_backend_id = _backend_id(reopened, label="reopened AuthorityRootRegistry")
    shared_visibility = (
        reopened.read_root(first.root_id) == first
        and reopened.read_root(second.root_id) == second
        and reopened.read_root(stale_candidate.root_id) == stale_candidate
    )
    stable_backend_identity = reopened_backend_id == backend_id

    registry.compare_and_swap_current(
        probe_season,
        expected_root_id=None,
        new_root_id=first.root_id,
    )
    reopened.compare_and_swap_current(
        probe_season,
        expected_root_id=first.root_id,
        new_root_id=second.root_id,
    )
    stale_writer_rejected = False
    try:
        registry.compare_and_swap_current(
            probe_season,
            expected_root_id=first.root_id,
            new_root_id=stale_candidate.root_id,
        )
    except AuthorityRootCompareAndSwapConflict:
        stale_writer_rejected = True

    final_root_id = reopened.current_root_id(probe_season)
    immutable_root_history = (
        registry.read_root(first.root_id) == first
        and registry.read_root(second.root_id) == second
    )
    atomic_compare_and_swap = final_root_id == second.root_id
    durable_shared_registry = stable_backend_identity and shared_visibility
    evidence_payload = {
        "schema_name": "apex-authority-root-registry-probe-evidence",
        "schema_version": 1,
        "backend_id": backend_id,
        "reopened_backend_id": reopened_backend_id,
        "qualification_scope": scope,
        "probe_season": probe_season,
        "first_root_id": first.root_id,
        "second_root_id": second.root_id,
        "stale_candidate_root_id": stale_candidate.root_id,
        "final_root_id": final_root_id,
        "stable_backend_identity": stable_backend_identity,
        "shared_visibility": shared_visibility,
        "durable_shared_registry": durable_shared_registry,
        "immutable_root_history": immutable_root_history,
        "atomic_compare_and_swap": atomic_compare_and_swap,
        "stale_writer_rejected": stale_writer_rejected,
    }
    probe_ref = store.put_bytes(
        canonical_json_bytes(evidence_payload),
        media_type="application/json",
        schema_name="apex-authority-root-registry-probe-evidence",
        schema_version="1",
    )
    qualification = AuthorityRootRegistryQualification(
        backend_id=backend_id,
        probe_artifact_id=probe_ref.artifact_id,
        durable_shared_registry=durable_shared_registry,
        immutable_root_history=immutable_root_history,
        atomic_compare_and_swap=atomic_compare_and_swap,
        stale_writer_rejected=stale_writer_rejected,
        qualification_scope=scope,
    )
    envelope = {
        "schema_name": "apex-stored-authority-root-registry-qualification",
        "schema_version": 1,
        "qualification_id": qualification.qualification_id,
        "payload": qualification.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-authority-root-registry-qualification",
        schema_version="1",
    )
    return StoredAuthorityRootRegistryQualification(qualification, ref.artifact_id)


def _canonical_object(content: bytes, *, label: str) -> dict[str, object]:
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be JSON object")
    if canonical_json_bytes(raw) != content:
        raise ValueError(f"{label} must be canonical JSON")
    return dict(raw)


def load_authority_root_registry_qualification(
    artifact_id: str,
    *,
    store: ArtifactStore,
    expected_backend_id: str | None = None,
    expected_scope: str | None = None,
) -> StoredAuthorityRootRegistryQualification:
    """Strictly replay qualification and reconcile it to its retained live-probe evidence."""

    raw = _canonical_object(
        store.read_bytes(artifact_id),
        label="authority-root registry qualification",
    )
    if (
        raw.get("schema_name") != "apex-stored-authority-root-registry-qualification"
        or raw.get("schema_version") != 1
    ):
        raise ValueError("unsupported authority-root registry qualification schema")
    payload = raw.get("payload")
    declared = raw.get("qualification_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("authority-root registry qualification payload/identity is invalid")
    qualification = AuthorityRootRegistryQualification(
        backend_id=str(payload.get("backend_id") or ""),
        probe_artifact_id=str(payload.get("probe_artifact_id") or ""),
        durable_shared_registry=_strict_bool(
            payload.get("durable_shared_registry"),
            label="authority-root durable_shared_registry",
        ),
        immutable_root_history=_strict_bool(
            payload.get("immutable_root_history"),
            label="authority-root immutable_root_history",
        ),
        atomic_compare_and_swap=_strict_bool(
            payload.get("atomic_compare_and_swap"),
            label="authority-root atomic_compare_and_swap",
        ),
        stale_writer_rejected=_strict_bool(
            payload.get("stale_writer_rejected"),
            label="authority-root stale_writer_rejected",
        ),
        qualification_scope=str(payload.get("qualification_scope") or ""),
        schema_version=_strict_int(
            payload.get("schema_version"),
            label="authority-root qualification schema_version",
        ),
    )
    if qualification.qualification_id != declared:
        raise ValueError("authority-root registry qualification semantic identity mismatch")
    if expected_backend_id is not None and qualification.backend_id != str(expected_backend_id):
        raise ValueError("authority-root registry backend differs from qualification")
    if expected_scope is not None and qualification.qualification_scope != str(expected_scope):
        raise ValueError("authority-root registry qualification scope mismatch")

    evidence = _canonical_object(
        store.read_bytes(qualification.probe_artifact_id),
        label="authority-root registry probe evidence",
    )
    if (
        evidence.get("schema_name") != "apex-authority-root-registry-probe-evidence"
        or evidence.get("schema_version") != 1
    ):
        raise ValueError("unsupported authority-root registry probe evidence schema")
    expected_values = {
        "backend_id": qualification.backend_id,
        "qualification_scope": qualification.qualification_scope,
        "durable_shared_registry": qualification.durable_shared_registry,
        "immutable_root_history": qualification.immutable_root_history,
        "atomic_compare_and_swap": qualification.atomic_compare_and_swap,
        "stale_writer_rejected": qualification.stale_writer_rejected,
    }
    if any(evidence.get(key) != value for key, value in expected_values.items()):
        raise ValueError("authority-root registry qualification disagrees with probe evidence")
    if evidence.get("final_root_id") != evidence.get("second_root_id"):
        raise ValueError("authority-root registry probe did not finish on second root")
    if evidence.get("stable_backend_identity") is not True:
        raise ValueError("authority-root registry backend identity was not stable across reopen")
    if evidence.get("shared_visibility") is not True:
        raise ValueError("authority-root registry was not shared across reopened adapter")
    return StoredAuthorityRootRegistryQualification(qualification, artifact_id)
