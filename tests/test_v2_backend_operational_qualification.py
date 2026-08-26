from __future__ import annotations

from dataclasses import replace
import os
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.backend_operational_qualification import (
    derive_backend_qualification_from_probes,
    derive_production_backend_qualification,
    load_artifact_store_probe_evidence,
    load_backend_deployment_qualification_evidence,
    store_backend_deployment_evidence_item,
    store_backend_deployment_qualification_evidence,
    verify_backend_qualification_evidence,
    verify_stored_backend_qualification_evidence,
)
from apex_fpl.control.postgres_backend import (
    PostgresArtifactStore,
    PostgresReleaseRegistry,
    initialize_postgres_control_plane,
)
from apex_fpl.control.release_registry import FileSystemReleaseRegistry
from apex_fpl.core.backend_qualification import (
    REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS,
    ArtifactStoreProbeEvidence,
    BackendDeploymentQualificationEvidence,
)
from apex_fpl.core.canonical import canonical_json_bytes

from backend_qualification_helpers import synthetic_production_backend_qualification


DSN = os.environ.get("APEX_TEST_POSTGRES_DSN")
SCOPE = "2026-2027:63984:2:production"


def _schema() -> str:
    return f"apex_qualification_{uuid4().hex}"


def _drop(schema: str) -> None:
    assert DSN is not None
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


def _deployment_evidence(
    *,
    store,
    mechanical,
    environment_class: str = "PRODUCTION",
    kinds: frozenset[str] = REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS,
):
    deployment_id = f"synthetic-test-deployment:{uuid4().hex}"
    items = []
    for kind in sorted(kinds):
        source = store.put_bytes(f"synthetic-source:{deployment_id}:{kind}".encode()).artifact_id
        items.append(
            store_backend_deployment_evidence_item(
                store=store,
                artifact_store_backend_id=mechanical.artifact_store_evidence.backend_id,
                release_registry_backend_id=mechanical.release_registry_evidence.backend_id,
                qualification_scope=SCOPE,
                deployment_id=deployment_id,
                evidence_kind=kind,
                issuer="synthetic-test-fixture",
                observed_at="2026-08-25T05:00:00Z",
                outcome="PASS",
                source_artifact_ids=(source,),
            )
        )
    evidence = BackendDeploymentQualificationEvidence(
        artifact_store_backend_id=mechanical.artifact_store_evidence.backend_id,
        release_registry_backend_id=mechanical.release_registry_evidence.backend_id,
        qualification_scope=SCOPE,
        deployment_id=deployment_id,
        environment_class=environment_class,
        evaluated_at="2026-08-25T05:30:00Z",
        evidence_items=tuple(items),
    )
    artifact_id = store_backend_deployment_qualification_evidence(evidence, store=store)
    return evidence, artifact_id


@pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
def test_postgres_fresh_connection_probes_are_mechanical_evidence_only() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        registry = PostgresReleaseRegistry(DSN, schema=schema)
        mechanical = derive_backend_qualification_from_probes(
            artifact_store=store,
            release_registry=registry,
            qualification_scope=SCOPE,
            probe_nonce=uuid4().hex,
        )
        assert mechanical.supported is True
        assert mechanical.artifact_store_evidence.supported is True
        assert mechanical.release_registry_evidence.supported is True
        # Deliberately no ProductionBackendQualification is produced by Plane A.
        assert not hasattr(mechanical, "qualification")
    finally:
        _drop(schema)


@pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
def test_postgres_full_qualification_requires_independent_deployment_plane() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        registry = PostgresReleaseRegistry(DSN, schema=schema)
        verified = synthetic_production_backend_qualification(
            store=store,
            registry=registry,
            qualification_scope=SCOPE,
        )
        assert verified.qualification.qualified is True
        assert verified.deployment_evidence.supported is True
        replayed = verify_backend_qualification_evidence(
            verified.qualification,
            artifact_store=store.reopen(),
            release_registry=registry.reopen(),
        )
        assert replayed.qualification.semantic_payload() == verified.qualification.semantic_payload()
        assert replayed.deployment_evidence.evidence_id == verified.deployment_evidence.evidence_id
        assert (
            load_artifact_store_probe_evidence(
                verified.artifact_store_mechanical_evidence_artifact_id,
                store=store,
            ).semantic_payload()
            == verified.artifact_store_evidence.semantic_payload()
        )
    finally:
        _drop(schema)


@pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
def test_backend_qualification_booleans_cannot_diverge_from_retained_two_plane_evidence() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        registry = PostgresReleaseRegistry(DSN, schema=schema)
        verified = synthetic_production_backend_qualification(
            store=store,
            registry=registry,
            qualification_scope=SCOPE,
        )
        forged = replace(verified.qualification, atomic_compare_and_swap=False)
        with pytest.raises(ValueError, match="not derived from retained mechanical and deployment"):
            verify_stored_backend_qualification_evidence(forged, store=store)
    finally:
        _drop(schema)


@pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
def test_backend_qualification_cannot_replay_through_another_registry_identity() -> None:
    assert DSN is not None
    source_schema = _schema()
    other_schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=source_schema)
        source_store = PostgresArtifactStore(DSN, schema=source_schema)
        source_registry = PostgresReleaseRegistry(DSN, schema=source_schema)
        verified = synthetic_production_backend_qualification(
            store=source_store,
            registry=source_registry,
            qualification_scope=SCOPE,
        )
        initialize_postgres_control_plane(DSN, schema=other_schema)
        other_registry = PostgresReleaseRegistry(DSN, schema=other_schema)
        with pytest.raises(ValueError, match="different backend"):
            verify_backend_qualification_evidence(
                verified.qualification,
                artifact_store=source_store,
                release_registry=other_registry,
            )
    finally:
        _drop(source_schema)
        _drop(other_schema)


def test_reference_filesystem_can_pass_mechanical_probe_but_never_production_qualify(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "releases")
    mechanical = derive_backend_qualification_from_probes(
        artifact_store=store,
        release_registry=registry,
        qualification_scope=SCOPE,
        probe_nonce=uuid4().hex,
    )
    assert mechanical.supported is True
    deployment, deployment_artifact = _deployment_evidence(store=store, mechanical=mechanical)
    assert deployment.supported is True
    verified = derive_production_backend_qualification(
        mechanical,
        deployment_evidence_artifact_id=deployment_artifact,
        store=store,
    )
    assert verified.qualification.qualified is False


def test_test_environment_deployment_evidence_cannot_production_qualify(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "releases")
    mechanical = derive_backend_qualification_from_probes(
        artifact_store=store,
        release_registry=registry,
        qualification_scope=SCOPE,
        probe_nonce=uuid4().hex,
    )
    deployment, deployment_artifact = _deployment_evidence(
        store=store,
        mechanical=mechanical,
        environment_class="TEST",
    )
    assert deployment.supported is False
    verified = derive_production_backend_qualification(
        mechanical,
        deployment_evidence_artifact_id=deployment_artifact,
        store=store,
    )
    assert verified.qualification.qualified is False


def test_incomplete_deployment_evidence_cannot_production_qualify(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "releases")
    mechanical = derive_backend_qualification_from_probes(
        artifact_store=store,
        release_registry=registry,
        qualification_scope=SCOPE,
        probe_nonce=uuid4().hex,
    )
    kinds = frozenset(sorted(REQUIRED_BACKEND_DEPLOYMENT_EVIDENCE_KINDS)[:-1])
    deployment, deployment_artifact = _deployment_evidence(
        store=store,
        mechanical=mechanical,
        kinds=kinds,
    )
    assert deployment.complete is False
    verified = derive_production_backend_qualification(
        mechanical,
        deployment_evidence_artifact_id=deployment_artifact,
        store=store,
    )
    assert verified.qualification.qualified is False


def test_random_bytes_cannot_be_laundered_as_deployment_qualification(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    random_id = store.put_bytes(b"not-deployment-qualification").artifact_id
    with pytest.raises(ValueError, match="not valid UTF-8 JSON"):
        load_backend_deployment_qualification_evidence(random_id, store=store)


def test_probe_evidence_rejects_string_boolean_laundering() -> None:
    with pytest.raises(ValueError, match="must be boolean"):
        ArtifactStoreProbeEvidence(
            backend_id="apex.production.test-artifact-store.v1",
            qualification_scope=SCOPE,
            probe_artifact_id="sha256:" + "a" * 64,
            probe_content_sha256="b" * 64,
            reopened_backend_id="apex.production.test-artifact-store.v1",
            reopened_read_sha256="b" * 64,
            stable_backend_identity="true",  # type: ignore[arg-type]
            shared_visibility=True,
            integrity_verified=True,
        )


def test_canonical_probe_wrapper_cannot_change_payload_without_changing_identity(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    mechanical = derive_backend_qualification_from_probes(
        artifact_store=store,
        release_registry=FileSystemReleaseRegistry(tmp_path / "releases"),
        qualification_scope=SCOPE,
        probe_nonce=uuid4().hex,
    )
    evidence_id = mechanical.artifact_store_evidence_artifact_id
    payload = load_artifact_store_probe_evidence(evidence_id, store=store).semantic_payload()
    payload["shared_visibility"] = False
    forged = canonical_json_bytes(
        {
            "schema_name": "apex-artifact-store-operational-probe-evidence",
            "schema_version": 1,
            "evidence_id": mechanical.artifact_store_evidence.evidence_id,
            "payload": payload,
        }
    )
    forged_id = store.put_bytes(forged).artifact_id
    with pytest.raises(ValueError, match="semantic identity mismatch"):
        load_artifact_store_probe_evidence(forged_id, store=store)
