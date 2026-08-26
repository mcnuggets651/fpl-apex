"""Behavior-derived operational qualification for production backend adapters.

The probe is intentionally provider-neutral.  A backend cannot become production-qualified
merely by choosing a new backend_id and supplying green booleans: the exact adapter must
support fresh-instance shared visibility, immutable release replay and stale-writer-safe CAS,
and the observed evidence is retained under content identity.

Long-horizon retention, credential separation, backup/restore and availability remain
separate deployment evidence obligations; this module proves the live control-plane
behavior that Apex can verify mechanically.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from typing import Protocol

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.production_cutover import ProductionReleaseRegistry
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    ImmutableReleaseConflict,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)
from apex_fpl.core.backend_qualification import (
    ArtifactStoreProbeEvidence,
    ReleaseRegistryProbeEvidence,
)
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.production import ProductionBackendQualification


class ReopenableArtifactStore(ArtifactStore, Protocol):
    backend_id: str

    def reopen(self) -> "ReopenableArtifactStore": ...


class ReopenableReleaseRegistry(ProductionReleaseRegistry, Protocol):
    backend_id: str

    def reopen(self) -> "ReopenableReleaseRegistry": ...


@dataclass(frozen=True, slots=True)
class VerifiedBackendQualification:
    qualification: ProductionBackendQualification
    artifact_store_evidence: ArtifactStoreProbeEvidence
    release_registry_evidence: ReleaseRegistryProbeEvidence


def _backend_id(value: object, *, label: str) -> str:
    backend_id = getattr(value, "backend_id", None)
    if not isinstance(backend_id, str) or not backend_id.strip():
        raise ValueError(f"{label} has no stable backend identity")
    return backend_id.strip()


def _scope(value: str) -> str:
    scope = str(value).strip()
    if not scope:
        raise ValueError("backend qualification scope is required")
    return scope


def _nonce(value: str) -> str:
    nonce = str(value).strip()
    if not nonce:
        raise ValueError("backend qualification probe nonce is required")
    return nonce


def _stored_probe(evidence, *, store: ArtifactStore, schema_name: str) -> str:
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": schema_name,
                "schema_version": 1,
                "evidence_id": evidence.evidence_id,
                "payload": evidence.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name=schema_name,
        schema_version="1",
    )
    return ref.artifact_id


def run_artifact_store_probe(
    store: ReopenableArtifactStore,
    *,
    qualification_scope: str,
    probe_nonce: str,
) -> tuple[ArtifactStoreProbeEvidence, str]:
    scope = _scope(qualification_scope)
    nonce = _nonce(probe_nonce)
    backend_id = _backend_id(store, label="ArtifactStore")
    content = canonical_json_bytes(
        {
            "schema_name": "apex-backend-artifact-probe-payload",
            "schema_version": 1,
            "qualification_scope": scope,
            "probe_nonce": nonce,
        }
    )
    expected_digest = sha256(content).hexdigest()
    ref = store.put_bytes(
        content,
        media_type="application/json",
        schema_name="apex-backend-artifact-probe-payload",
        schema_version="1",
    )
    reopened = store.reopen()
    reopened_backend = _backend_id(reopened, label="reopened ArtifactStore")
    replayed = reopened.read_bytes(ref.artifact_id)
    replayed_digest = sha256(replayed).hexdigest()
    evidence = ArtifactStoreProbeEvidence(
        backend_id=backend_id,
        qualification_scope=scope,
        probe_artifact_id=ref.artifact_id,
        probe_content_sha256=expected_digest,
        reopened_backend_id=reopened_backend,
        reopened_read_sha256=replayed_digest,
        stable_backend_identity=backend_id == reopened_backend,
        shared_visibility=replayed == content,
        integrity_verified=(
            ref.artifact_id == f"sha256:{expected_digest}"
            and reopened.verify(ref.artifact_id)
            and replayed_digest == expected_digest
        ),
    )
    artifact_id = _stored_probe(
        evidence,
        store=store,
        schema_name="apex-artifact-store-operational-probe-evidence",
    )
    return evidence, artifact_id


def _probe_record(
    *,
    season: str,
    runtime_digest: str,
    manifest_id: str,
) -> ReleaseRecord:
    return ReleaseRecord(
        season=season,
        entry=1,
        gameweek=1,
        bundle_id=None,
        world_id=None,
        runtime_digest=runtime_digest,
        created_at="2000-01-01T00:00:00+00:00",
        valid_until=None,
        status=ReleaseStatus.CERTIFIED,
        ready_to_act=False,
        safe_to_act=False,
        artifact_manifest_id=manifest_id,
    ).with_release_id()


def run_release_registry_probe(
    registry: ReopenableReleaseRegistry,
    *,
    artifact_store: ArtifactStore,
    qualification_scope: str,
    probe_nonce: str,
) -> tuple[ReleaseRegistryProbeEvidence, str]:
    scope = _scope(qualification_scope)
    nonce = _nonce(probe_nonce)
    backend_id = _backend_id(registry, label="ReleaseRegistry")
    key_digest = canonical_sha256(
        {
            "schema_name": "apex-backend-release-probe-key",
            "schema_version": 1,
            "qualification_scope": scope,
            "probe_nonce": nonce,
        }
    )
    probe_season = f"apex-qualification-{key_digest[:20]}"
    key = ReleaseKey(probe_season, 1, 1)
    if registry.current_release_id(key) is not None:
        raise ValueError("backend qualification probe key already has a current release")

    first_manifest = artifact_store.put_bytes(
        f"backend-probe:first:{scope}:{nonce}".encode("utf-8")
    ).artifact_id
    second_manifest = artifact_store.put_bytes(
        f"backend-probe:second:{scope}:{nonce}".encode("utf-8")
    ).artifact_id
    first = _probe_record(
        season=probe_season,
        runtime_digest=f"backend-probe:first:{key_digest}",
        manifest_id=first_manifest,
    )
    second = _probe_record(
        season=probe_season,
        runtime_digest=f"backend-probe:second:{key_digest}",
        manifest_id=second_manifest,
    )
    first = registry.append(first)
    second = registry.append(second)
    assert first.release_id is not None and second.release_id is not None

    reopened = registry.reopen()
    reopened_backend = _backend_id(reopened, label="reopened ReleaseRegistry")
    shared_visibility = (
        reopened.read_release(first.release_id) == first
        and reopened.read_release(second.release_id) == second
    )

    forged_identity_rejected = False
    forged = replace(
        first,
        runtime_digest=f"backend-probe:forged:{key_digest}",
        release_id=first.release_id,
    )
    try:
        reopened.append(forged)
    except (ValueError, ImmutableReleaseConflict):
        forged_identity_rejected = True

    registry.compare_and_swap_current(
        key,
        expected_release_id=None,
        new_release_id=first.release_id,
    )
    stale_writer_conflict = False
    try:
        reopened.compare_and_swap_current(
            key,
            expected_release_id=None,
            new_release_id=second.release_id,
        )
    except CompareAndSwapConflict:
        stale_writer_conflict = True

    reopened.compare_and_swap_current(
        key,
        expected_release_id=first.release_id,
        new_release_id=second.release_id,
    )
    final_release = registry.current_release_id(key)
    immutable_replay = registry.read_release(first.release_id) == first
    evidence = ReleaseRegistryProbeEvidence(
        backend_id=backend_id,
        qualification_scope=scope,
        probe_season=probe_season,
        probe_entry=1,
        probe_gameweek=1,
        first_release_id=first.release_id,
        second_release_id=second.release_id,
        reopened_backend_id=reopened_backend,
        stable_backend_identity=backend_id == reopened_backend,
        shared_visibility=shared_visibility,
        immutable_replay=immutable_replay,
        forged_identity_rejected=forged_identity_rejected,
        stale_writer_conflict_observed=stale_writer_conflict,
        successful_cas_transition=final_release == second.release_id,
        final_release_id=str(final_release or "missing"),
    )
    artifact_id = _stored_probe(
        evidence,
        store=artifact_store,
        schema_name="apex-release-registry-operational-probe-evidence",
    )
    return evidence, artifact_id


def derive_backend_qualification_from_probes(
    *,
    artifact_store: ReopenableArtifactStore,
    release_registry: ReopenableReleaseRegistry,
    qualification_scope: str,
    probe_nonce: str,
) -> VerifiedBackendQualification:
    artifact_evidence, artifact_evidence_id = run_artifact_store_probe(
        artifact_store,
        qualification_scope=qualification_scope,
        probe_nonce=f"{probe_nonce}:artifact",
    )
    registry_evidence, registry_evidence_id = run_release_registry_probe(
        release_registry,
        artifact_store=artifact_store,
        qualification_scope=qualification_scope,
        probe_nonce=f"{probe_nonce}:registry",
    )
    qualification = ProductionBackendQualification(
        artifact_store_backend_id=artifact_evidence.backend_id,
        release_registry_backend_id=registry_evidence.backend_id,
        artifact_store_qualification_artifact_id=artifact_evidence_id,
        release_registry_qualification_artifact_id=registry_evidence_id,
        durable_shared_artifact_store=artifact_evidence.supported,
        durable_shared_release_registry=(
            registry_evidence.stable_backend_identity
            and registry_evidence.shared_visibility
        ),
        atomic_compare_and_swap=(
            registry_evidence.stale_writer_conflict_observed
            and registry_evidence.successful_cas_transition
        ),
        immutable_release_history=(
            registry_evidence.immutable_replay
            and registry_evidence.forged_identity_rejected
        ),
        qualification_scope=_scope(qualification_scope),
    )
    return VerifiedBackendQualification(
        qualification=qualification,
        artifact_store_evidence=artifact_evidence,
        release_registry_evidence=registry_evidence,
    )


def _canonical_object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be a JSON object")
    if canonical_json_bytes(payload) != raw:
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def load_artifact_store_probe_evidence(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ArtifactStoreProbeEvidence:
    raw = _canonical_object(
        store.read_bytes(artifact_id),
        label="artifact-store operational probe evidence",
    )
    if (
        raw.get("schema_name") != "apex-artifact-store-operational-probe-evidence"
        or raw.get("schema_version") != 1
    ):
        raise ValueError("unsupported artifact-store operational probe evidence schema")
    payload = raw.get("payload")
    declared = raw.get("evidence_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("artifact-store operational probe payload/identity is invalid")
    evidence = ArtifactStoreProbeEvidence(
        backend_id=str(payload.get("backend_id") or ""),
        qualification_scope=str(payload.get("qualification_scope") or ""),
        probe_artifact_id=str(payload.get("probe_artifact_id") or ""),
        probe_content_sha256=str(payload.get("probe_content_sha256") or ""),
        reopened_backend_id=str(payload.get("reopened_backend_id") or ""),
        reopened_read_sha256=str(payload.get("reopened_read_sha256") or ""),
        stable_backend_identity=payload.get("stable_backend_identity"),  # type: ignore[arg-type]
        shared_visibility=payload.get("shared_visibility"),  # type: ignore[arg-type]
        integrity_verified=payload.get("integrity_verified"),  # type: ignore[arg-type]
        schema_version=payload.get("schema_version"),  # type: ignore[arg-type]
    )
    if evidence.evidence_id != declared:
        raise ValueError("artifact-store operational probe semantic identity mismatch")
    if not store.verify(evidence.probe_artifact_id):
        raise ValueError("artifact-store probe payload is missing/corrupt")
    return evidence


def load_release_registry_probe_evidence(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> ReleaseRegistryProbeEvidence:
    raw = _canonical_object(
        store.read_bytes(artifact_id),
        label="release-registry operational probe evidence",
    )
    if (
        raw.get("schema_name") != "apex-release-registry-operational-probe-evidence"
        or raw.get("schema_version") != 1
    ):
        raise ValueError("unsupported release-registry operational probe evidence schema")
    payload = raw.get("payload")
    declared = raw.get("evidence_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("release-registry operational probe payload/identity is invalid")
    evidence = ReleaseRegistryProbeEvidence(
        backend_id=str(payload.get("backend_id") or ""),
        qualification_scope=str(payload.get("qualification_scope") or ""),
        probe_season=str(payload.get("probe_season") or ""),
        probe_entry=payload.get("probe_entry"),  # type: ignore[arg-type]
        probe_gameweek=payload.get("probe_gameweek"),  # type: ignore[arg-type]
        first_release_id=str(payload.get("first_release_id") or ""),
        second_release_id=str(payload.get("second_release_id") or ""),
        reopened_backend_id=str(payload.get("reopened_backend_id") or ""),
        stable_backend_identity=payload.get("stable_backend_identity"),  # type: ignore[arg-type]
        shared_visibility=payload.get("shared_visibility"),  # type: ignore[arg-type]
        immutable_replay=payload.get("immutable_replay"),  # type: ignore[arg-type]
        forged_identity_rejected=payload.get("forged_identity_rejected"),  # type: ignore[arg-type]
        stale_writer_conflict_observed=payload.get("stale_writer_conflict_observed"),  # type: ignore[arg-type]
        successful_cas_transition=payload.get("successful_cas_transition"),  # type: ignore[arg-type]
        final_release_id=str(payload.get("final_release_id") or ""),
        schema_version=payload.get("schema_version"),  # type: ignore[arg-type]
    )
    if evidence.evidence_id != declared:
        raise ValueError("release-registry operational probe semantic identity mismatch")
    return evidence


def verify_backend_qualification_evidence(
    qualification: ProductionBackendQualification,
    *,
    artifact_store: ArtifactStore,
    release_registry: ProductionReleaseRegistry,
) -> VerifiedBackendQualification:
    artifact_evidence = load_artifact_store_probe_evidence(
        qualification.artifact_store_qualification_artifact_id,
        store=artifact_store,
    )
    registry_evidence = load_release_registry_probe_evidence(
        qualification.release_registry_qualification_artifact_id,
        store=artifact_store,
    )
    actual_artifact_backend = _backend_id(artifact_store, label="ArtifactStore")
    actual_registry_backend = _backend_id(release_registry, label="ReleaseRegistry")
    if artifact_evidence.backend_id != actual_artifact_backend:
        raise ValueError("artifact-store probe evidence belongs to a different backend")
    if registry_evidence.backend_id != actual_registry_backend:
        raise ValueError("release-registry probe evidence belongs to a different backend")
    if artifact_evidence.qualification_scope != qualification.qualification_scope:
        raise ValueError("artifact-store probe evidence scope mismatch")
    if registry_evidence.qualification_scope != qualification.qualification_scope:
        raise ValueError("release-registry probe evidence scope mismatch")

    expected = ProductionBackendQualification(
        artifact_store_backend_id=actual_artifact_backend,
        release_registry_backend_id=actual_registry_backend,
        artifact_store_qualification_artifact_id=(
            qualification.artifact_store_qualification_artifact_id
        ),
        release_registry_qualification_artifact_id=(
            qualification.release_registry_qualification_artifact_id
        ),
        durable_shared_artifact_store=artifact_evidence.supported,
        durable_shared_release_registry=(
            registry_evidence.stable_backend_identity
            and registry_evidence.shared_visibility
        ),
        atomic_compare_and_swap=(
            registry_evidence.stale_writer_conflict_observed
            and registry_evidence.successful_cas_transition
        ),
        immutable_release_history=(
            registry_evidence.immutable_replay
            and registry_evidence.forged_identity_rejected
        ),
        qualification_scope=qualification.qualification_scope,
    )
    if expected.semantic_payload() != qualification.semantic_payload():
        raise ValueError("production backend qualification is not derived from retained probes")
    if not artifact_evidence.supported or not registry_evidence.supported:
        raise ValueError("production backend operational probes are not fully supported")
    return VerifiedBackendQualification(
        qualification=qualification,
        artifact_store_evidence=artifact_evidence,
        release_registry_evidence=registry_evidence,
    )
