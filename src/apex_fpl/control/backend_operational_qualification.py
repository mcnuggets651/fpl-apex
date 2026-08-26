"""Two-plane qualification for production control-plane backends.

Plane A is machine-verifiable live behavior: fresh-adapter shared visibility, stable persisted
identity, immutable release replay and stale-writer-safe compare-and-swap. Plane B is retained
deployment/operations evidence for durability properties that a fresh database probe cannot
honestly prove: retention, access control, credential separation, backup, restore, disaster
recovery, availability and geographic durability.

Production qualification requires both planes. A GitHub Actions PostgreSQL service can prove
Plane A only and therefore cannot become production authority merely by passing integration
tests. All evidence is content-addressed and replayed fail-closed.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.backend_ports import (
    ProductionReleaseRegistry,
    ReopenableArtifactStore,
    ReopenableReleaseRegistry,
)
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    ImmutableReleaseConflict,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)
from apex_fpl.core.backend_qualification import (
    ArtifactStoreProbeEvidence,
    BackendDeploymentEvidenceItem,
    BackendDeploymentQualificationEvidence,
    ReleaseRegistryProbeEvidence,
)
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.production import ProductionBackendQualification


_ARTIFACT_ROLE = "ARTIFACT_STORE"
_REGISTRY_ROLE = "RELEASE_REGISTRY"


@dataclass(frozen=True, slots=True)
class VerifiedBackendMechanicalQualification:
    """Replayable live/mechanical evidence. This object is never production qualification."""

    artifact_store_evidence: ArtifactStoreProbeEvidence
    artifact_store_evidence_artifact_id: str
    release_registry_evidence: ReleaseRegistryProbeEvidence
    release_registry_evidence_artifact_id: str

    @property
    def qualification_scope(self) -> str:
        if (
            self.artifact_store_evidence.qualification_scope
            != self.release_registry_evidence.qualification_scope
        ):
            raise ValueError("backend mechanical probe scopes disagree")
        return self.artifact_store_evidence.qualification_scope

    @property
    def supported(self) -> bool:
        return self.artifact_store_evidence.supported and self.release_registry_evidence.supported


@dataclass(frozen=True, slots=True)
class VerifiedBackendQualification:
    """Fully replayed production backend qualification across both evidence planes."""

    qualification: ProductionBackendQualification
    artifact_store_evidence: ArtifactStoreProbeEvidence
    release_registry_evidence: ReleaseRegistryProbeEvidence
    deployment_evidence: BackendDeploymentQualificationEvidence
    artifact_store_mechanical_evidence_artifact_id: str
    release_registry_mechanical_evidence_artifact_id: str
    deployment_evidence_artifact_id: str


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
) -> VerifiedBackendMechanicalQualification:
    """Run Plane A only. The result deliberately cannot authorize production."""

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
    return VerifiedBackendMechanicalQualification(
        artifact_store_evidence=artifact_evidence,
        artifact_store_evidence_artifact_id=artifact_evidence_id,
        release_registry_evidence=registry_evidence,
        release_registry_evidence_artifact_id=registry_evidence_id,
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


def store_backend_deployment_evidence_item(
    *,
    store: ArtifactStore,
    artifact_store_backend_id: str,
    release_registry_backend_id: str,
    qualification_scope: str,
    deployment_id: str,
    evidence_kind: str,
    issuer: str,
    observed_at: str,
    outcome: str,
    source_artifact_ids: tuple[str, ...],
) -> BackendDeploymentEvidenceItem:
    """Seal one typed operational observation backed by retained source artifacts."""

    sources = tuple(sorted({str(item).strip() for item in source_artifact_ids if str(item).strip()}))
    if not sources:
        raise ValueError("deployment observation requires retained source artifacts")
    for artifact_id in sources:
        if not store.verify(artifact_id):
            raise ValueError(f"deployment observation source is missing/corrupt: {artifact_id}")
    prototype = BackendDeploymentEvidenceItem(
        evidence_kind=evidence_kind,
        evidence_artifact_id="pending",
        issuer=issuer,
        observed_at=observed_at,
        outcome=outcome,
    )
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-backend-deployment-observation",
                "schema_version": 1,
                "artifact_store_backend_id": _scope(artifact_store_backend_id),
                "release_registry_backend_id": _scope(release_registry_backend_id),
                "qualification_scope": _scope(qualification_scope),
                "deployment_id": _scope(deployment_id),
                "evidence_kind": prototype.evidence_kind,
                "issuer": prototype.issuer,
                "observed_at": prototype.observed_at,
                "outcome": prototype.outcome,
                "source_artifact_ids": list(sources),
            }
        ),
        media_type="application/json",
        schema_name="apex-backend-deployment-observation",
        schema_version="1",
    )
    return BackendDeploymentEvidenceItem(
        evidence_kind=prototype.evidence_kind,
        evidence_artifact_id=ref.artifact_id,
        issuer=prototype.issuer,
        observed_at=prototype.observed_at,
        outcome=prototype.outcome,
    )


def _verify_deployment_observation(
    item: BackendDeploymentEvidenceItem,
    *,
    evidence: BackendDeploymentQualificationEvidence,
    store: ArtifactStore,
) -> None:
    if not store.verify(item.evidence_artifact_id):
        raise ValueError("deployment observation artifact is missing/corrupt")
    raw = _canonical_object(
        store.read_bytes(item.evidence_artifact_id),
        label="backend deployment observation",
    )
    expected = {
        "schema_name": "apex-backend-deployment-observation",
        "schema_version": 1,
        "artifact_store_backend_id": evidence.artifact_store_backend_id,
        "release_registry_backend_id": evidence.release_registry_backend_id,
        "qualification_scope": evidence.qualification_scope,
        "deployment_id": evidence.deployment_id,
        "evidence_kind": item.evidence_kind,
        "issuer": item.issuer,
        "observed_at": item.observed_at,
        "outcome": item.outcome,
    }
    if any(raw.get(key) != value for key, value in expected.items()):
        raise ValueError("deployment observation does not match qualification evidence")
    sources = raw.get("source_artifact_ids")
    if not isinstance(sources, list) or not sources or any(not isinstance(item, str) for item in sources):
        raise ValueError("deployment observation has invalid source artifact list")
    if len(sources) != len(set(sources)):
        raise ValueError("deployment observation source artifacts are duplicated")
    for artifact_id in sources:
        if not store.verify(artifact_id):
            raise ValueError(f"deployment observation source is missing/corrupt: {artifact_id}")


def store_backend_deployment_qualification_evidence(
    evidence: BackendDeploymentQualificationEvidence,
    *,
    store: ArtifactStore,
) -> str:
    """Store Plane B after independently replaying every retained observation."""

    for item in evidence.evidence_items:
        _verify_deployment_observation(item, evidence=evidence, store=store)
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-backend-deployment-qualification-evidence",
                "schema_version": 1,
                "evidence_id": evidence.evidence_id,
                "payload": evidence.semantic_payload(),
            }
        ),
        media_type="application/json",
        schema_name="apex-backend-deployment-qualification-evidence",
        schema_version="1",
    )
    return ref.artifact_id


def load_backend_deployment_qualification_evidence(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> BackendDeploymentQualificationEvidence:
    raw = _canonical_object(
        store.read_bytes(artifact_id),
        label="backend deployment qualification evidence",
    )
    if (
        raw.get("schema_name") != "apex-backend-deployment-qualification-evidence"
        or raw.get("schema_version") != 1
    ):
        raise ValueError("unsupported backend deployment qualification evidence schema")
    payload = raw.get("payload")
    declared = raw.get("evidence_id")
    if not isinstance(payload, dict) or not isinstance(declared, str):
        raise ValueError("backend deployment qualification payload/identity is invalid")
    raw_items = payload.get("evidence_items")
    if not isinstance(raw_items, list):
        raise ValueError("backend deployment qualification evidence_items must be list")
    items: list[BackendDeploymentEvidenceItem] = []
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            raise ValueError("backend deployment evidence item must be object")
        items.append(
            BackendDeploymentEvidenceItem(
                evidence_kind=str(raw_item.get("evidence_kind") or ""),
                evidence_artifact_id=str(raw_item.get("evidence_artifact_id") or ""),
                issuer=str(raw_item.get("issuer") or ""),
                observed_at=str(raw_item.get("observed_at") or ""),
                outcome=str(raw_item.get("outcome") or ""),
                schema_version=raw_item.get("schema_version"),  # type: ignore[arg-type]
            )
        )
    evidence = BackendDeploymentQualificationEvidence(
        artifact_store_backend_id=str(payload.get("artifact_store_backend_id") or ""),
        release_registry_backend_id=str(payload.get("release_registry_backend_id") or ""),
        qualification_scope=str(payload.get("qualification_scope") or ""),
        deployment_id=str(payload.get("deployment_id") or ""),
        environment_class=str(payload.get("environment_class") or ""),
        evaluated_at=str(payload.get("evaluated_at") or ""),
        evidence_items=tuple(items),
        schema_version=payload.get("schema_version"),  # type: ignore[arg-type]
    )
    if evidence.evidence_id != declared:
        raise ValueError("backend deployment qualification semantic identity mismatch")
    if payload.get("complete") is not evidence.complete or payload.get("supported") is not evidence.supported:
        raise ValueError("backend deployment qualification derived status mismatch")
    for item in evidence.evidence_items:
        _verify_deployment_observation(item, evidence=evidence, store=store)
    return evidence


def _store_qualification_binding(
    *,
    store: ArtifactStore,
    role: str,
    backend_id: str,
    qualification_scope: str,
    mechanical_evidence_artifact_id: str,
    deployment_evidence_artifact_id: str,
) -> str:
    if role not in {_ARTIFACT_ROLE, _REGISTRY_ROLE}:
        raise ValueError("unsupported backend qualification role")
    ref = store.put_bytes(
        canonical_json_bytes(
            {
                "schema_name": "apex-backend-production-qualification-binding",
                "schema_version": 1,
                "role": role,
                "backend_id": _scope(backend_id),
                "qualification_scope": _scope(qualification_scope),
                "mechanical_evidence_artifact_id": _scope(mechanical_evidence_artifact_id),
                "deployment_evidence_artifact_id": _scope(deployment_evidence_artifact_id),
            }
        ),
        media_type="application/json",
        schema_name="apex-backend-production-qualification-binding",
        schema_version="1",
    )
    return ref.artifact_id


def _load_qualification_binding(
    artifact_id: str,
    *,
    store: ArtifactStore,
    expected_role: str,
) -> dict[str, str]:
    raw = _canonical_object(
        store.read_bytes(artifact_id),
        label="backend production qualification binding",
    )
    if (
        raw.get("schema_name") != "apex-backend-production-qualification-binding"
        or raw.get("schema_version") != 1
        or raw.get("role") != expected_role
    ):
        raise ValueError("unsupported backend production qualification binding")
    result: dict[str, str] = {}
    for key in (
        "backend_id",
        "qualification_scope",
        "mechanical_evidence_artifact_id",
        "deployment_evidence_artifact_id",
    ):
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"backend qualification binding {key} is invalid")
        result[key] = value.strip()
    return result


def derive_production_backend_qualification(
    mechanical: VerifiedBackendMechanicalQualification,
    *,
    deployment_evidence_artifact_id: str,
    store: ArtifactStore,
) -> VerifiedBackendQualification:
    """Combine independently retained Plane A and Plane B evidence into production qualification."""

    deployment = load_backend_deployment_qualification_evidence(
        deployment_evidence_artifact_id,
        store=store,
    )
    artifact_evidence = mechanical.artifact_store_evidence
    registry_evidence = mechanical.release_registry_evidence
    scope = mechanical.qualification_scope
    if deployment.artifact_store_backend_id != artifact_evidence.backend_id:
        raise ValueError("deployment evidence artifact-store backend identity mismatch")
    if deployment.release_registry_backend_id != registry_evidence.backend_id:
        raise ValueError("deployment evidence release-registry backend identity mismatch")
    if deployment.qualification_scope != scope:
        raise ValueError("deployment evidence qualification scope mismatch")

    artifact_binding = _store_qualification_binding(
        store=store,
        role=_ARTIFACT_ROLE,
        backend_id=artifact_evidence.backend_id,
        qualification_scope=scope,
        mechanical_evidence_artifact_id=mechanical.artifact_store_evidence_artifact_id,
        deployment_evidence_artifact_id=deployment_evidence_artifact_id,
    )
    registry_binding = _store_qualification_binding(
        store=store,
        role=_REGISTRY_ROLE,
        backend_id=registry_evidence.backend_id,
        qualification_scope=scope,
        mechanical_evidence_artifact_id=mechanical.release_registry_evidence_artifact_id,
        deployment_evidence_artifact_id=deployment_evidence_artifact_id,
    )
    qualification = ProductionBackendQualification(
        artifact_store_backend_id=artifact_evidence.backend_id,
        release_registry_backend_id=registry_evidence.backend_id,
        artifact_store_qualification_artifact_id=artifact_binding,
        release_registry_qualification_artifact_id=registry_binding,
        durable_shared_artifact_store=(artifact_evidence.supported and deployment.supported),
        durable_shared_release_registry=(
            registry_evidence.stable_backend_identity
            and registry_evidence.shared_visibility
            and deployment.supported
        ),
        atomic_compare_and_swap=(
            registry_evidence.stale_writer_conflict_observed
            and registry_evidence.successful_cas_transition
        ),
        immutable_release_history=(
            registry_evidence.immutable_replay
            and registry_evidence.forged_identity_rejected
        ),
        qualification_scope=scope,
    )
    return VerifiedBackendQualification(
        qualification=qualification,
        artifact_store_evidence=artifact_evidence,
        release_registry_evidence=registry_evidence,
        deployment_evidence=deployment,
        artifact_store_mechanical_evidence_artifact_id=(
            mechanical.artifact_store_evidence_artifact_id
        ),
        release_registry_mechanical_evidence_artifact_id=(
            mechanical.release_registry_evidence_artifact_id
        ),
        deployment_evidence_artifact_id=deployment_evidence_artifact_id,
    )


def verify_stored_backend_qualification_evidence(
    qualification: ProductionBackendQualification,
    *,
    store: ArtifactStore,
) -> VerifiedBackendQualification:
    artifact_binding = _load_qualification_binding(
        qualification.artifact_store_qualification_artifact_id,
        store=store,
        expected_role=_ARTIFACT_ROLE,
    )
    registry_binding = _load_qualification_binding(
        qualification.release_registry_qualification_artifact_id,
        store=store,
        expected_role=_REGISTRY_ROLE,
    )
    if artifact_binding["backend_id"] != qualification.artifact_store_backend_id:
        raise ValueError("artifact-store qualification binding backend identity mismatch")
    if registry_binding["backend_id"] != qualification.release_registry_backend_id:
        raise ValueError("release-registry qualification binding backend identity mismatch")
    if artifact_binding["qualification_scope"] != qualification.qualification_scope:
        raise ValueError("artifact-store qualification binding scope mismatch")
    if registry_binding["qualification_scope"] != qualification.qualification_scope:
        raise ValueError("release-registry qualification binding scope mismatch")
    deployment_id = artifact_binding["deployment_evidence_artifact_id"]
    if registry_binding["deployment_evidence_artifact_id"] != deployment_id:
        raise ValueError("backend qualification bindings do not share deployment evidence")

    artifact_evidence = load_artifact_store_probe_evidence(
        artifact_binding["mechanical_evidence_artifact_id"],
        store=store,
    )
    registry_evidence = load_release_registry_probe_evidence(
        registry_binding["mechanical_evidence_artifact_id"],
        store=store,
    )
    deployment = load_backend_deployment_qualification_evidence(deployment_id, store=store)
    if artifact_evidence.backend_id != qualification.artifact_store_backend_id:
        raise ValueError("artifact-store probe evidence backend identity mismatch")
    if registry_evidence.backend_id != qualification.release_registry_backend_id:
        raise ValueError("release-registry probe evidence backend identity mismatch")
    if deployment.artifact_store_backend_id != qualification.artifact_store_backend_id:
        raise ValueError("deployment evidence artifact-store backend identity mismatch")
    if deployment.release_registry_backend_id != qualification.release_registry_backend_id:
        raise ValueError("deployment evidence release-registry backend identity mismatch")
    if artifact_evidence.qualification_scope != qualification.qualification_scope:
        raise ValueError("artifact-store probe evidence scope mismatch")
    if registry_evidence.qualification_scope != qualification.qualification_scope:
        raise ValueError("release-registry probe evidence scope mismatch")
    if deployment.qualification_scope != qualification.qualification_scope:
        raise ValueError("deployment evidence scope mismatch")

    expected = ProductionBackendQualification(
        artifact_store_backend_id=qualification.artifact_store_backend_id,
        release_registry_backend_id=qualification.release_registry_backend_id,
        artifact_store_qualification_artifact_id=(
            qualification.artifact_store_qualification_artifact_id
        ),
        release_registry_qualification_artifact_id=(
            qualification.release_registry_qualification_artifact_id
        ),
        durable_shared_artifact_store=(artifact_evidence.supported and deployment.supported),
        durable_shared_release_registry=(
            registry_evidence.stable_backend_identity
            and registry_evidence.shared_visibility
            and deployment.supported
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
        raise ValueError(
            "production backend qualification is not derived from retained mechanical and deployment evidence"
        )
    return VerifiedBackendQualification(
        qualification=qualification,
        artifact_store_evidence=artifact_evidence,
        release_registry_evidence=registry_evidence,
        deployment_evidence=deployment,
        artifact_store_mechanical_evidence_artifact_id=(
            artifact_binding["mechanical_evidence_artifact_id"]
        ),
        release_registry_mechanical_evidence_artifact_id=(
            registry_binding["mechanical_evidence_artifact_id"]
        ),
        deployment_evidence_artifact_id=deployment_id,
    )


def verify_backend_qualification_evidence(
    qualification: ProductionBackendQualification,
    *,
    artifact_store: ArtifactStore,
    release_registry: ProductionReleaseRegistry,
) -> VerifiedBackendQualification:
    verified = verify_stored_backend_qualification_evidence(
        qualification,
        store=artifact_store,
    )
    actual_artifact_backend = _backend_id(artifact_store, label="ArtifactStore")
    actual_registry_backend = _backend_id(release_registry, label="ReleaseRegistry")
    if verified.artifact_store_evidence.backend_id != actual_artifact_backend:
        raise ValueError("artifact-store probe evidence belongs to a different backend")
    if verified.release_registry_evidence.backend_id != actual_registry_backend:
        raise ValueError("release-registry probe evidence belongs to a different backend")
    if verified.deployment_evidence.artifact_store_backend_id != actual_artifact_backend:
        raise ValueError("deployment evidence belongs to a different ArtifactStore backend")
    if verified.deployment_evidence.release_registry_backend_id != actual_registry_backend:
        raise ValueError("deployment evidence belongs to a different ReleaseRegistry backend")
    return verified
