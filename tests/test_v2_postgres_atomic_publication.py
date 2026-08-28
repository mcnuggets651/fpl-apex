from __future__ import annotations

import os
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest

from apex_fpl.control.postgres_atomic_publication import (
    RootAtomicPublicationConflict,
    compare_and_swap_release_under_authority_root,
)
from apex_fpl.control.postgres_authority_root_registry import (
    PostgresAuthorityRootRegistry,
    initialize_postgres_authority_root_registry,
)
from apex_fpl.control.postgres_backend import (
    PostgresArtifactStore,
    PostgresReleaseRegistry,
    initialize_postgres_control_plane,
)
from apex_fpl.control.release_registry import ReleaseKey, ReleaseRecord, ReleaseStatus
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot


DSN = os.environ.get("APEX_TEST_POSTGRES_DSN")
pytestmark = pytest.mark.skipif(not DSN, reason="APEX_TEST_POSTGRES_DSN is not configured")
SEASON = "2026-2027"
KEY = ReleaseKey(SEASON, 63984, 2)


def _schema() -> str:
    return f"apex_atomic_{uuid4().hex}"


def _drop(schema: str) -> None:
    assert DSN is not None
    with psycopg.connect(DSN, autocommit=True) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema))
            )


def _sha(char: str) -> str:
    return f"sha256:{char * 64}"


def _root(*, generation: int, parent: str | None = None) -> ProductionAuthorityRoot:
    char = "1" if generation == 1 else "2"
    return ProductionAuthorityRoot(
        season=SEASON,
        generation=generation,
        parent_root_artifact_id=parent,
        champion_generation_artifact_id=_sha(char),
        ruleset_artifact_id=_sha("3"),
        ruleset_id=_sha("4"),
        learning_policy_registry_artifact_id=_sha("5"),
        learning_policy_id=_sha("6"),
        outcome_truth_registry_artifact_id=_sha("7"),
        outcome_truth_registry_id=_sha("8"),
        build_manifest_artifact_id=_sha("9"),
        build_manifest_id=_sha("a"),
        change_control_artifact_id=_sha("b"),
        authorized_by="postgres-atomic-publication-test",
        authorized_at="2026-08-27T12:00:00Z",
        valid_from="2026-08-27T12:00:00Z",
        valid_until="2026-09-30T12:00:00Z",
        reason=f"synthetic root generation {generation}",
    )


def _record(*, runtime: str, manifest: str) -> ReleaseRecord:
    return ReleaseRecord(
        season=SEASON,
        entry=KEY.entry,
        gameweek=KEY.gameweek,
        bundle_id=None,
        world_id=None,
        runtime_digest=runtime,
        created_at="2026-08-27T12:10:00Z",
        valid_until="2026-08-28T12:10:00Z",
        status=ReleaseStatus.PUBLISHED,
        ready_to_act=True,
        safe_to_act=True,
        artifact_manifest_id=manifest,
    ).with_release_id()


def _control_plane(schema: str):
    assert DSN is not None
    initialize_postgres_control_plane(DSN, schema=schema)
    initialize_postgres_authority_root_registry(DSN, schema=schema)
    return (
        PostgresArtifactStore(DSN, schema=schema),
        PostgresReleaseRegistry(DSN, schema=schema),
        PostgresAuthorityRootRegistry(DSN, schema=schema),
    )


def test_atomic_publication_commits_release_under_exact_current_root() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        store, releases, roots = _control_plane(schema)
        root = _root(generation=1)
        roots.append(root)
        roots.compare_and_swap_current(SEASON, expected_root_id=None, new_root_id=root.root_id)
        manifest = store.put_bytes(b"atomic-publication-manifest").artifact_id
        record = releases.append(_record(runtime="runtime-a", manifest=manifest))
        assert record.release_id is not None

        compare_and_swap_release_under_authority_root(
            releases,
            roots,
            KEY,
            expected_release_id=None,
            new_release_id=record.release_id,
            expected_root_id=root.root_id,
        )

        assert releases.current_release_id(KEY) == record.release_id
        assert roots.current_root_id(SEASON) == root.root_id
    finally:
        _drop(schema)


def test_atomic_publication_rejects_root_that_already_moved() -> None:
    assert DSN is not None
    schema = _schema()
    try:
        store, releases, roots = _control_plane(schema)
        first = _root(generation=1)
        second = _root(generation=2, parent=first.root_id)
        roots.append(first)
        roots.compare_and_swap_current(SEASON, expected_root_id=None, new_root_id=first.root_id)
        roots.append(second)
        roots.compare_and_swap_current(
            SEASON,
            expected_root_id=first.root_id,
            new_root_id=second.root_id,
        )
        manifest = store.put_bytes(b"stale-root-manifest").artifact_id
        record = releases.append(_record(runtime="runtime-b", manifest=manifest))
        assert record.release_id is not None

        with pytest.raises(
            RootAtomicPublicationConflict,
            match="authority root changed before atomic release publication",
        ):
            compare_and_swap_release_under_authority_root(
                releases,
                roots,
                KEY,
                expected_release_id=None,
                new_release_id=record.release_id,
                expected_root_id=first.root_id,
            )

        assert releases.current_release_id(KEY) is None
        assert roots.current_root_id(SEASON) == second.root_id
    finally:
        _drop(schema)


def test_atomic_publication_rejects_different_postgres_control_plane() -> None:
    assert DSN is not None
    release_schema = _schema()
    root_schema = _schema()
    try:
        store, releases, _ = _control_plane(release_schema)
        _, _, other_roots = _control_plane(root_schema)
        root = _root(generation=1)
        other_roots.append(root)
        other_roots.compare_and_swap_current(
            SEASON,
            expected_root_id=None,
            new_root_id=root.root_id,
        )
        manifest = store.put_bytes(b"cross-plane-manifest").artifact_id
        record = releases.append(_record(runtime="runtime-c", manifest=manifest))
        assert record.release_id is not None

        with pytest.raises(
            RootAtomicPublicationConflict,
            match="not the same PostgreSQL control plane",
        ):
            compare_and_swap_release_under_authority_root(
                releases,
                other_roots,
                KEY,
                expected_release_id=None,
                new_release_id=record.release_id,
                expected_root_id=root.root_id,
            )

        assert releases.current_release_id(KEY) is None
    finally:
        _drop(release_schema)
        _drop(root_schema)
