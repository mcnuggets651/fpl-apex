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
    load_artifact_store_probe_evidence,
    load_release_registry_probe_evidence,
    verify_backend_qualification_evidence,
    verify_stored_backend_qualification_evidence,
)
from apex_fpl.control.postgres_backend import (
    PostgresArtifactStore,
    PostgresReleaseRegistry,
    initialize_postgres_control_plane,
)
from apex_fpl.control.release_registry import FileSystemReleaseRegistry
from apex_fpl.core.backend_qualification import ArtifactStoreProbeEvidence
from apex_fpl.core.canonical import canonical_json_bytes


DSN = os.environ.get("APEX_TEST_POSTGRES_DSN")


def _schema() -> str:
    return f"apex_qualification_{uuid4().hex}"


def _drop(schema: str) -> None:
    assert DSN is not None
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


@pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
def test_postgres_backend_qualification_is_derived_from_fresh_instance_behavior() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        registry = PostgresReleaseRegistry(DSN, schema=schema)
        scope = "2026-2027:63984:2:production"
        verified = derive_backend_qualification_from_probes(
            artifact_store=store,
            release_registry=registry,
            qualification_scope=scope,
            probe_nonce=uuid4().hex,
        )
        assert verified.qualification.qualified is True
        assert verified.artifact_store_evidence.supported is True
        assert verified.release_registry_evidence.supported is True

        replayed = verify_backend_qualification_evidence(
            verified.qualification,
            artifact_store=store.reopen(),
            release_registry=registry.reopen(),
        )
        assert replayed.qualification.semantic_payload() == verified.qualification.semantic_payload()
        assert (
            load_artifact_store_probe_evidence(
                verified.qualification.artifact_store_qualification_artifact_id,
                store=store,
            ).semantic_payload()
            == verified.artifact_store_evidence.semantic_payload()
        )
        assert (
            load_release_registry_probe_evidence(
                verified.qualification.release_registry_qualification_artifact_id,
                store=store,
            ).semantic_payload()
            == verified.release_registry_evidence.semantic_payload()
        )
    finally:
        _drop(schema)


@pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
def test_backend_qualification_booleans_cannot_diverge_from_retained_probe_evidence() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        registry = PostgresReleaseRegistry(DSN, schema=schema)
        verified = derive_backend_qualification_from_probes(
            artifact_store=store,
            release_registry=registry,
            qualification_scope="2026-2027:63984:2:production",
            probe_nonce=uuid4().hex,
        )
        forged = replace(verified.qualification, atomic_compare_and_swap=False)
        with pytest.raises(ValueError, match="not derived from retained probes"):
            verify_stored_backend_qualification_evidence(forged, store=store)
    finally:
        _drop(schema)


@pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
def test_backend_qualification_cannot_replay_through_another_control_plane_identity() -> None:
    assert DSN is not None
    source_schema = _schema()
    other_schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=source_schema)
        source_store = PostgresArtifactStore(DSN, schema=source_schema)
        source_registry = PostgresReleaseRegistry(DSN, schema=source_schema)
        verified = derive_backend_qualification_from_probes(
            artifact_store=source_store,
            release_registry=source_registry,
            qualification_scope="2026-2027:63984:2:production",
            probe_nonce=uuid4().hex,
        )

        initialize_postgres_control_plane(DSN, schema=other_schema)
        other_store = PostgresArtifactStore(DSN, schema=other_schema)
        other_registry = PostgresReleaseRegistry(DSN, schema=other_schema)
        # Copying qualification bytes is insufficient: live backend identity must also match.
        for artifact_id in (
            verified.qualification.artifact_store_qualification_artifact_id,
            verified.qualification.release_registry_qualification_artifact_id,
        ):
            other_store.put_bytes(source_store.read_bytes(artifact_id))
        probe_payload = source_store.read_bytes(
            verified.artifact_store_evidence.probe_artifact_id
        )
        other_store.put_bytes(probe_payload)
        with pytest.raises(ValueError, match="different backend"):
            verify_backend_qualification_evidence(
                verified.qualification,
                artifact_store=other_store,
                release_registry=other_registry,
            )
    finally:
        _drop(source_schema)
        _drop(other_schema)


def test_reference_filesystem_behavior_probe_cannot_become_production_qualified(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    registry = FileSystemReleaseRegistry(tmp_path / "releases")
    verified = derive_backend_qualification_from_probes(
        artifact_store=store,
        release_registry=registry,
        qualification_scope="2026-2027:63984:2:production",
        probe_nonce=uuid4().hex,
    )
    assert verified.artifact_store_evidence.supported is True
    assert verified.release_registry_evidence.supported is True
    assert verified.qualification.qualified is False


def test_probe_evidence_rejects_string_boolean_laundering() -> None:
    with pytest.raises(ValueError, match="must be boolean"):
        ArtifactStoreProbeEvidence(
            backend_id="apex.production.test-artifact-store.v1",
            qualification_scope="2026-2027:63984:2:production",
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
    verified = derive_backend_qualification_from_probes(
        artifact_store=store,
        release_registry=FileSystemReleaseRegistry(tmp_path / "releases"),
        qualification_scope="2026-2027:63984:2:production",
        probe_nonce=uuid4().hex,
    )
    evidence_id = verified.qualification.artifact_store_qualification_artifact_id
    payload = load_artifact_store_probe_evidence(evidence_id, store=store).semantic_payload()
    payload["shared_visibility"] = False
    forged = canonical_json_bytes(
        {
            "schema_name": "apex-artifact-store-operational-probe-evidence",
            "schema_version": 1,
            "evidence_id": verified.artifact_store_evidence.evidence_id,
            "payload": payload,
        }
    )
    forged_id = store.put_bytes(forged).artifact_id
    with pytest.raises(ValueError, match="semantic identity mismatch"):
        load_artifact_store_probe_evidence(forged_id, store=store)
