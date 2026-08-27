"""Durable PostgreSQL authority-root history and season-level CAS pointer."""

from __future__ import annotations

import re
from uuid import uuid4

import psycopg
from psycopg import sql

from apex_fpl.control.authority_root_registry import (
    AuthorityRootCompareAndSwapConflict,
    ImmutableAuthorityRootConflict,
    authority_root_bytes,
    parse_authority_root_bytes,
)
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot


_SCHEMA = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMPONENT = "authority-root-registry"
_PREFIX = "apex.production.postgres-authority-root-registry.v1"


def _schema_name(value: str) -> str:
    name = str(value).strip()
    if not _SCHEMA.fullmatch(name):
        raise ValueError("PostgreSQL schema must be a simple SQL identifier")
    return name


def _table(schema: str, name: str):
    return sql.Identifier(schema, name)


def _digest(root_id: str) -> str:
    algorithm, separator, digest = str(root_id).partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("authority root ID must be sha256 identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("authority root digest is invalid") from exc
    return digest.lower()


def initialize_postgres_authority_root_registry(
    dsn: str,
    *,
    schema: str = "apex_v2",
) -> None:
    """Administrative migration for the dedicated authority-root control plane.

    The base Apex PostgreSQL control plane must already exist. Runtime credentials do not
    require DDL after this one-time migration.
    """

    schema = _schema_name(schema)
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql.SQL("SELECT 1 FROM {} WHERE component = %s").format(
                    _table(schema, "backend_identity")
                ),
                ("artifact-store",),
            )
            if cursor.fetchone() is None:
                raise RuntimeError("base Apex PostgreSQL control plane is not initialised")
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        root_id CHAR(64) PRIMARY KEY,
                        body BYTEA NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                ).format(_table(schema, "authority_roots"))
            )
            cursor.execute(
                sql.SQL(
                    """
                    CREATE TABLE IF NOT EXISTS {} (
                        season TEXT PRIMARY KEY,
                        root_id CHAR(64) NOT NULL REFERENCES {} (root_id),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                    )
                    """
                ).format(
                    _table(schema, "authority_root_pointers"),
                    _table(schema, "authority_roots"),
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
            trigger_name = sql.Identifier("apex_reject_authority_roots_mutation")
            roots_table = _table(schema, "authority_roots")
            cursor.execute(
                sql.SQL("DROP TRIGGER IF EXISTS {} ON {}").format(trigger_name, roots_table)
            )
            cursor.execute(
                sql.SQL(
                    "CREATE TRIGGER {} BEFORE UPDATE OR DELETE ON {} "
                    "FOR EACH ROW EXECUTE FUNCTION {}()"
                ).format(trigger_name, roots_table, function_name)
            )
            cursor.execute(
                sql.SQL(
                    "INSERT INTO {} (component, instance_id) VALUES (%s, %s) "
                    "ON CONFLICT (component) DO NOTHING"
                ).format(_table(schema, "backend_identity")),
                (_COMPONENT, uuid4().hex),
            )
        conn.commit()


def _load_instance_id(dsn: str, schema: str) -> str:
    try:
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT instance_id FROM {} WHERE component = %s").format(
                        _table(schema, "backend_identity")
                    ),
                    (_COMPONENT,),
                )
                row = cursor.fetchone()
    except (psycopg.errors.InvalidSchemaName, psycopg.errors.UndefinedTable) as exc:
        raise RuntimeError("PostgreSQL authority-root registry is not initialised") from exc
    if row is None or not isinstance(row[0], str) or not row[0].strip():
        raise RuntimeError("PostgreSQL authority-root registry is not initialised")
    return row[0].strip()


class PostgresAuthorityRootRegistry:
    """Immutable root history plus transactional season-level current-pointer CAS."""

    def __init__(self, dsn: str, *, schema: str = "apex_v2"):
        self._dsn = str(dsn)
        if not self._dsn.strip():
            raise ValueError("PostgreSQL DSN is required")
        self.schema = _schema_name(schema)
        self.backend_id = f"{_PREFIX}:{_load_instance_id(self._dsn, self.schema)}"

    def reopen(self) -> "PostgresAuthorityRootRegistry":
        return PostgresAuthorityRootRegistry(self._dsn, schema=self.schema)

    def append(self, root: ProductionAuthorityRoot) -> ProductionAuthorityRoot:
        digest = _digest(root.root_id)
        body = authority_root_bytes(root)
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL(
                        "INSERT INTO {} (root_id, body) VALUES (%s, %s) "
                        "ON CONFLICT (root_id) DO NOTHING"
                    ).format(_table(self.schema, "authority_roots")),
                    (digest, body),
                )
                cursor.execute(
                    sql.SQL("SELECT body FROM {} WHERE root_id = %s").format(
                        _table(self.schema, "authority_roots")
                    ),
                    (digest,),
                )
                row = cursor.fetchone()
            conn.commit()
        if row is None or bytes(row[0]) != body:
            raise ImmutableAuthorityRootConflict(root.root_id)
        return root

    def read_root(self, root_id: str) -> ProductionAuthorityRoot:
        digest = _digest(root_id)
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT body FROM {} WHERE root_id = %s").format(
                        _table(self.schema, "authority_roots")
                    ),
                    (digest,),
                )
                row = cursor.fetchone()
        if row is None:
            raise FileNotFoundError(f"unknown authority root: {root_id}")
        return parse_authority_root_bytes(bytes(row[0]), expected_root_id=str(root_id))

    def current_root_id(self, season: str) -> str | None:
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    sql.SQL("SELECT root_id FROM {} WHERE season = %s").format(
                        _table(self.schema, "authority_root_pointers")
                    ),
                    (str(season),),
                )
                row = cursor.fetchone()
        return None if row is None else f"sha256:{str(row[0]).strip()}"

    def current_root(self, season: str) -> ProductionAuthorityRoot | None:
        root_id = self.current_root_id(season)
        return None if root_id is None else self.read_root(root_id)

    def compare_and_swap_current(
        self,
        season: str,
        *,
        expected_root_id: str | None,
        new_root_id: str,
    ) -> None:
        new_root = self.read_root(new_root_id)
        if new_root.season != str(season):
            raise ValueError("authority root cannot be selected for a different season")
        if new_root.parent_root_artifact_id != expected_root_id:
            raise ValueError("authority root parent must equal CAS expected current root")
        new_digest = _digest(new_root_id)
        expected_digest = None if expected_root_id is None else _digest(expected_root_id)
        with psycopg.connect(self._dsn) as conn:
            with conn.cursor() as cursor:
                if expected_digest is None:
                    cursor.execute(
                        sql.SQL(
                            "INSERT INTO {} (season, root_id) VALUES (%s, %s) "
                            "ON CONFLICT (season) DO NOTHING RETURNING root_id"
                        ).format(_table(self.schema, "authority_root_pointers")),
                        (str(season), new_digest),
                    )
                else:
                    cursor.execute(
                        sql.SQL(
                            "UPDATE {} SET root_id = %s, updated_at = CURRENT_TIMESTAMP "
                            "WHERE season = %s AND root_id = %s RETURNING root_id"
                        ).format(_table(self.schema, "authority_root_pointers")),
                        (new_digest, str(season), expected_digest),
                    )
                updated = cursor.fetchone()
                if updated is None:
                    conn.rollback()
                    current = self.current_root_id(season)
                    raise AuthorityRootCompareAndSwapConflict(
                        f"stale authority-root writer for {season}: expected "
                        f"{expected_root_id!r}, found {current!r}"
                    )
            conn.commit()
