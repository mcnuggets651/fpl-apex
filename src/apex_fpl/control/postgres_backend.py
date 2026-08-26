"""Durable shared PostgreSQL control-plane adapters for Apex V2.

The adapters deliberately keep deployment identity inside the database rather than deriving
it from a DSN, hostname, environment label or credential.  This makes qualification bind to
the logical persisted control plane while allowing connection rotation and failover without
silently changing identity.

Schema bootstrap is explicit.  Production runtime credentials may therefore be restricted
to DML after an administrator has initialised the schema.
"""

from __future__ import annotations

from hashlib import sha256
import json
import re
from typing import Final
from uuid import uuid4

import psycopg
from psycopg import sql

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactRef
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    ImmutableReleaseConflict,
    ReleaseKey,
    ReleaseRecord,
    normalize_release_record,
    parse_release_record_bytes,
    release_record_bytes,
)


_SCHEMA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ARTIFACT_COMPONENT: Final[str] = "artifact-store"
_REGISTRY_COMPONENT: Final[str] = "release-registry"


def _schema_name(value: str) -> str:
    name = str(value).strip()
    if not _SCHEMA.fullmatch(name):
        raise ValueError("PostgreSQL schema must be a simple SQL identifier")
    return name


def _artifact_digest(artifact_id: str) -> str:
    algorithm, separator, digest = str(artifact_id).partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"invalid artifact id: {artifact_id!r}")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"invalid sha256 digest: {digest!r}") from exc
    return digest.lower()


def _backend_identity(component: str, instance_id: str) -> str:
    prefix = {
        _ARTIFACT_COMPONENT: "apex.production.postgres-artifact-store.v1",
        _REGISTRY_COMPONENT: "apex.production.postgres-release-registry.v1",
    }[component]
    return f"{prefix}:{instance_id}"


def _table(schema: str, name: str):
    return sql.Identifier(schema, name)


def initialize_postgres_control_plane(dsn: str, *, schema: str = "apex_v2") -> None:
    """Create the immutable control-plane schema and persisted backend identities.

    This is an administrative operation.  Runtime production roles do not need CREATE,
    ALTER, UPDATE or DELETE privileges after bootstrap.
    """

    schema = _schema_name(schema)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        component TEXT PRIMARY KEY,
                        instance_id TEXT NOT NULL UNIQUE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                ).format(_table(schema, "backend_identity"))
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        digest CHAR(64) PRIMARY KEY,
                        content BYTEA NOT NULL,
                        size BIGINT NOT NULL CHECK (size >= 0),
                        media_type TEXT NOT NULL,
                        schema_name TEXT NULL,
                        schema_version TEXT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                ).format(_table(schema, "artifacts"))
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        release_id CHAR(64) PRIMARY KEY,
                        body BYTEA NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                ).format(_table(schema, "releases"))
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        season TEXT NOT NULL,
                        entry BIGINT NOT NULL CHECK (entry > 0),
                        gameweek INTEGER NOT NULL CHECK (gameweek > 0),
                        release_id CHAR(64) NOT NULL REFERENCES {} (release_id),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        PRIMARY KEY (season, entry, gameweek)
                    )
                    """
                ).format(
                    _table(schema, "release_pointers"),
                    _table(schema, "releases"),
                )
            )

            function_name = sql.Identifier(schema, "reject_immutable_mutation")
            cursor.execute(
                sql.SQL(
                    """
                    CREATE OR REPLACE FUNCTION {}() RETURNS trigger
                    LANGUAGE plpgsql AS $$
                    BEGIN
                        RAISE EXCEPTION 'Apex immutable control-plane row cannot be mutated';
                    END;
                    $$
                    """
                ).format(function_name)
            )
            for table_name in ("backend_identity", "artifacts", "releases"):
                trigger_name = sql.Identifier(f"apex_reject_{table_name}_mutation")
                table_name_sql = _table(schema, table_name)
                cursor.execute(
                    sql.SQL("DROP TRIGGER IF EXISTS {} ON {}").format(
                        trigger_name,
                        table_name_sql,
                    )
                )
                cursor.execute(
                    sql.SQL(
                        "CREATE TRIGGER {} BEFORE UPDATE OR DELETE ON {} "
                        "FOR EACH ROW EXECUTE FUNCTION {}()"
                    ).format(trigger_name, table_name_sql, function_name)
                )

            for component in (_ARTIFACT_COMPONENT, _REGISTRY_COMPONENT):
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {} (component, instance_id) VALUES (%s, %s) "
                        "ON CONFLICT (component) DO NOTHING"
                    ).format(_table(schema, "backend_identity")),
                    (component, uuid4().hex),
                )
        conn.commit()


def _load_instance_id(dsn: str, schema: str, component: str) -> str:
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT instance_id FROM {} WHERE component = %s").format(
                    _table(schema, "backend_identity")
                ),
                (component,),
            )
            row = cursor.fetchone()
    if row is None or not isinstance(row[0], str) or not row[0].strip():
        raise RuntimeError(
            "PostgreSQL Apex control plane is not initialised; run "
            "initialize_postgres_control_plane with administrative credentials"
        )
    return row[0].strip()


class PostgresArtifactStore:
    """Immutable SHA-256 ArtifactStore backed by one shared PostgreSQL control plane."""

    def __init__(self, dsn: str, *, schema: str = "apex_v2"):
        self._dsn = str(dsn)
        if not self._dsn.strip():
            raise ValueError("PostgreSQL DSN is required")
        self.schema = _schema_name(schema)
        instance_id = _load_instance_id(self._dsn, self.schema, _ARTIFACT_COMPONENT)
        self.backend_id = _backend_identity(_ARTIFACT_COMPONENT, instance_id)

    def reopen(self) -> "PostgresArtifactStore":
        """Return a fresh connection-owning adapter for shared-visibility qualification."""

        return PostgresArtifactStore(self._dsn, schema=self.schema)

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        schema_name: str | None = None,
        schema_version: str | None = None,
    ) -> ArtifactRef:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        digest = sha256(content).hexdigest()
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {} "
                        "(digest, content, size, media_type, schema_name, schema_version) "
                        "VALUES (%s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (digest) DO NOTHING"
                    ).format(_table(self.schema, "artifacts")),
                    (
                        digest,
                        content,
                        len(content),
                        str(media_type),
                        None if schema_name is None else str(schema_name),
                        None if schema_version is None else str(schema_version),
                    ),
                )
                cursor.execute(
                    sql.SQL("SELECT content FROM {} WHERE digest = %s").format(
                        _table(self.schema, "artifacts")
                    ),
                    (digest,),
                )
                row = cursor.fetchone()
            conn.commit()
        if row is None or bytes(row[0]) != content:
            raise ArtifactIntegrityError(f"content collision or corruption at sha256:{digest}")
        return ArtifactRef(
            digest=digest,
            size=len(content),
            media_type=str(media_type),
            schema_name=None if schema_name is None else str(schema_name),
            schema_version=None if schema_version is None else str(schema_version),
        )

    def read_bytes(self, artifact_id: str) -> bytes:
        digest = _artifact_digest(artifact_id)
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT content FROM {} WHERE digest = %s").format(
                        _table(self.schema, "artifacts")
                    ),
                    (digest,),
                )
                row = cursor.fetchone()
        if row is None:
            raise FileNotFoundError(f"unknown artifact: {artifact_id}")
        content = bytes(row[0])
        if sha256(content).hexdigest() != digest:
            raise ArtifactIntegrityError(f"artifact failed integrity check: {artifact_id}")
        return content

    def verify(self, artifact_id: str) -> bool:
        try:
            self.read_bytes(artifact_id)
        except (FileNotFoundError, ArtifactIntegrityError, ValueError):
            return False
        return True


class PostgresReleaseRegistry:
    """Immutable ReleaseRecord history plus transactional current-pointer CAS."""

    def __init__(self, dsn: str, *, schema: str = "apex_v2"):
        self._dsn = str(dsn)
        if not self._dsn.strip():
            raise ValueError("PostgreSQL DSN is required")
        self.schema = _schema_name(schema)
        instance_id = _load_instance_id(self._dsn, self.schema, _REGISTRY_COMPONENT)
        self.backend_id = _backend_identity(_REGISTRY_COMPONENT, instance_id)

    def reopen(self) -> "PostgresReleaseRegistry":
        return PostgresReleaseRegistry(self._dsn, schema=self.schema)

    def append(self, record: ReleaseRecord) -> ReleaseRecord:
        normalized = normalize_release_record(record)
        assert normalized.release_id is not None
        body = release_record_bytes(normalized)
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {} (release_id, body) VALUES (%s, %s) "
                        "ON CONFLICT (release_id) DO NOTHING"
                    ).format(_table(self.schema, "releases")),
                    (normalized.release_id, body),
                )
                cursor.execute(
                    sql.SQL("SELECT body FROM {} WHERE release_id = %s").format(
                        _table(self.schema, "releases")
                    ),
                    (normalized.release_id,),
                )
                row = cursor.fetchone()
            conn.commit()
        if row is None or bytes(row[0]) != body:
            raise ImmutableReleaseConflict(normalized.release_id)
        return normalized

    def read_release(self, release_id: str) -> ReleaseRecord:
        value = str(release_id).strip()
        if not value:
            raise ValueError("release_id is required")
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT body FROM {} WHERE release_id = %s").format(
                        _table(self.schema, "releases")
                    ),
                    (value,),
                )
                row = cursor.fetchone()
        if row is None:
            raise FileNotFoundError(f"unknown release: {value}")
        return parse_release_record_bytes(bytes(row[0]), expected_release_id=value)

    def current_release_id(self, key: ReleaseKey) -> str | None:
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "SELECT release_id FROM {} "
                        "WHERE season = %s AND entry = %s AND gameweek = %s"
                    ).format(_table(self.schema, "release_pointers")),
                    (key.season, key.entry, key.gameweek),
                )
                row = cursor.fetchone()
        return None if row is None else str(row[0]).strip()

    def current_release(self, key: ReleaseKey) -> ReleaseRecord | None:
        release_id = self.current_release_id(key)
        return None if release_id is None else self.read_release(release_id)

    def compare_and_swap_current(
        self,
        key: ReleaseKey,
        *,
        expected_release_id: str | None,
        new_release_id: str,
    ) -> None:
        new_release_id = str(new_release_id).strip()
        if not new_release_id:
            raise ValueError("new_release_id is required")
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT 1 FROM {} WHERE release_id = %s").format(
                        _table(self.schema, "releases")
                    ),
                    (new_release_id,),
                )
                if cursor.fetchone() is None:
                    raise FileNotFoundError(f"unknown release: {new_release_id}")

                if expected_release_id is None:
                    cursor.execute(
                        sql.SQL(
                            "INSERT INTO {} (season, entry, gameweek, release_id) "
                            "VALUES (%s, %s, %s, %s) "
                            "ON CONFLICT (season, entry, gameweek) DO NOTHING "
                            "RETURNING release_id"
                        ).format(_table(self.schema, "release_pointers")),
                        (key.season, key.entry, key.gameweek, new_release_id),
                    )
                else:
                    cursor.execute(
                        sql.SQL(
                            "UPDATE {} SET release_id = %s, updated_at = CURRENT_TIMESTAMP "
                            "WHERE season = %s AND entry = %s AND gameweek = %s "
                            "AND release_id = %s RETURNING release_id"
                        ).format(_table(self.schema, "release_pointers")),
                        (
                            new_release_id,
                            key.season,
                            key.entry,
                            key.gameweek,
                            str(expected_release_id),
                        ),
                    )
                updated = cursor.fetchone()
                if updated is None:
                    conn.rollback()
                    current = self.current_release_id(key)
                    raise CompareAndSwapConflict(
                        f"stale writer for {key}: expected {expected_release_id!r}, "
                        f"found {current!r}"
                    )
            conn.commit()
