from __future__ import annotations

from dataclasses import replace
import os
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from apex_fpl.control.postgres_backend import (
    PostgresArtifactStore,
    PostgresReleaseRegistry,
    initialize_postgres_control_plane,
)
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)


DSN = os.environ.get("APEX_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")


def _schema() -> str:
    return f"apex_test_{uuid4().hex}"


def _drop(schema: str) -> None:
    assert DSN is not None
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


def _record(*, season: str, runtime: str, manifest: str) -> ReleaseRecord:
    return ReleaseRecord(
        season=season,
        entry=63984,
        gameweek=2,
        bundle_id=None,
        world_id=None,
        runtime_digest=runtime,
        created_at="2026-08-26T03:00:00+00:00",
        valid_until=None,
        status=ReleaseStatus.CERTIFIED,
        ready_to_act=False,
        safe_to_act=False,
        artifact_manifest_id=manifest,
    ).with_release_id()


def test_postgres_backend_requires_explicit_initialisation_and_persists_identity() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        with pytest.raises(RuntimeError, match="not initialised"):
            PostgresArtifactStore(DSN, schema=schema)
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        registry = PostgresReleaseRegistry(DSN, schema=schema)
        assert store.reopen().backend_id == store.backend_id
        assert registry.reopen().backend_id == registry.backend_id
        assert store.backend_id.startswith("apex.production.postgres-artifact-store.v1:")
        assert registry.backend_id.startswith("apex.production.postgres-release-registry.v1:")
        assert "127.0.0.1" not in store.backend_id
        assert "apex-ci" not in store.backend_id
    finally:
        _drop(schema)


def test_postgres_artifact_store_is_content_addressed_and_shared_across_connections() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        writer = PostgresArtifactStore(DSN, schema=schema)
        reader = writer.reopen()
        first = writer.put_bytes(
            b"immutable-apex-postgres-artifact",
            media_type="application/octet-stream",
            schema_name="test-artifact",
            schema_version="1",
        )
        second = reader.put_bytes(b"immutable-apex-postgres-artifact")
        assert first.artifact_id == second.artifact_id
        assert reader.read_bytes(first.artifact_id) == b"immutable-apex-postgres-artifact"
        assert reader.verify(first.artifact_id) is True
    finally:
        _drop(schema)


def test_postgres_immutable_tables_reject_update_and_delete() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        ref = store.put_bytes(b"immutable-row")
        digest = ref.artifact_id.split(":", 1)[1]
        with psycopg.connect(DSN) as conn:
            with conn.cursor() as cursor:
                with pytest.raises(psycopg.Error, match="cannot be mutated"):
                    cursor.execute(
                        sql.SQL("UPDATE {} SET content = %s WHERE digest = %s").format(
                            sql.Identifier(schema, "artifacts")
                        ),
                        (b"corrupt", digest),
                    )
            conn.rollback()
        assert store.read_bytes(ref.artifact_id) == b"immutable-row"
    finally:
        _drop(schema)


def test_postgres_release_registry_replays_exactly_and_rejects_forged_identity() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        registry = PostgresReleaseRegistry(DSN, schema=schema)
        manifest = store.put_bytes(b"release-manifest").artifact_id
        record = _record(season="2026-2027", runtime="runtime-a", manifest=manifest)
        stored = registry.append(record)
        assert stored.release_id is not None
        assert registry.reopen().read_release(stored.release_id) == stored

        forged = replace(stored, runtime_digest="runtime-forged", release_id=stored.release_id)
        with pytest.raises(ValueError, match="declared identity"):
            registry.append(forged)
        assert registry.read_release(stored.release_id) == stored
    finally:
        _drop(schema)


def test_postgres_release_pointer_compare_and_swap_is_stale_writer_safe() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=schema)
        store = PostgresArtifactStore(DSN, schema=schema)
        first_registry = PostgresReleaseRegistry(DSN, schema=schema)
        second_registry = first_registry.reopen()
        manifest = store.put_bytes(b"cas-manifest").artifact_id
        first = first_registry.append(
            _record(season="2026-2027", runtime="runtime-first", manifest=manifest)
        )
        second = first_registry.append(
            _record(season="2026-2027", runtime="runtime-second", manifest=manifest)
        )
        assert first.release_id is not None and second.release_id is not None
        key = ReleaseKey("2026-2027", 63984, 2)

        first_registry.compare_and_swap_current(
            key,
            expected_release_id=None,
            new_release_id=first.release_id,
        )
        with pytest.raises(CompareAndSwapConflict):
            second_registry.compare_and_swap_current(
                key,
                expected_release_id=None,
                new_release_id=second.release_id,
            )
        second_registry.compare_and_swap_current(
            key,
            expected_release_id=first.release_id,
            new_release_id=second.release_id,
        )
        assert first_registry.current_release_id(key) == second.release_id
    finally:
        _drop(schema)


def test_different_postgres_control_planes_do_not_share_backend_identity() -> None:
    assert DSN is not None
    first_schema = _schema()
    second_schema = _schema()
    try:
        initialize_postgres_control_plane(DSN, schema=first_schema)
        initialize_postgres_control_plane(DSN, schema=second_schema)
        assert (
            PostgresArtifactStore(DSN, schema=first_schema).backend_id
            != PostgresArtifactStore(DSN, schema=second_schema).backend_id
        )
        assert (
            PostgresReleaseRegistry(DSN, schema=first_schema).backend_id
            != PostgresReleaseRegistry(DSN, schema=second_schema).backend_id
        )
    finally:
        _drop(first_schema)
        _drop(second_schema)
