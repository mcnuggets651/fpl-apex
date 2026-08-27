"""PostgreSQL publication primitive linearized against the current authority root.

The generic control-plane ports cannot provide a cross-registry transaction because they may
be backed by unrelated stores. The production PostgreSQL adapters are deliberately different:
release and authority-root pointers live in the same schema. This module uses that fact to lock
the season root pointer and compare-and-swap the release pointer in one database transaction.

No credential or DSN value is returned, persisted, logged or included in an Apex identity.
"""

from __future__ import annotations

from typing import Final

import psycopg
from psycopg import sql

from apex_fpl.control.postgres_authority_root_registry import PostgresAuthorityRootRegistry
from apex_fpl.control.postgres_backend import PostgresReleaseRegistry
from apex_fpl.control.release_registry import CompareAndSwapConflict, ReleaseKey


_RELEASE_PREFIX: Final[str] = "apex.production.postgres-release-registry.v1:"
_ROOT_PREFIX: Final[str] = "apex.production.postgres-authority-root-registry.v1:"


class RootAtomicPublicationConflict(RuntimeError):
    """Publication could not linearize under the exact expected authority root."""


def _root_digest(root_id: str) -> str:
    algorithm, separator, digest = str(root_id).partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("expected authority root ID must be sha256 identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("expected authority root digest is invalid") from exc
    return digest.lower()


def is_postgres_release_registry(registry: object) -> bool:
    """Return whether publication is targeting the real PostgreSQL release adapter."""

    return isinstance(registry, PostgresReleaseRegistry)


def _require_same_control_plane(
    release_registry: PostgresReleaseRegistry,
    authority_root_registry: object,
) -> PostgresAuthorityRootRegistry:
    if not isinstance(authority_root_registry, PostgresAuthorityRootRegistry):
        raise RootAtomicPublicationConflict(
            "PostgreSQL release publication requires PostgreSQL AuthorityRootRegistry"
        )
    if not release_registry.backend_id.startswith(_RELEASE_PREFIX):
        raise RootAtomicPublicationConflict(
            "release registry is not a production PostgreSQL backend"
        )
    if not authority_root_registry.backend_id.startswith(_ROOT_PREFIX):
        raise RootAtomicPublicationConflict(
            "authority-root registry is not a production PostgreSQL backend"
        )

    # Runtime construction supplies the same DSN/schema to all three production adapters.
    # Exact comparison is intentionally conservative: equivalent-but-differently-spelled DSNs
    # fail closed rather than silently losing the cross-registry transaction guarantee.
    if (
        release_registry.schema != authority_root_registry.schema
        or release_registry._dsn != authority_root_registry._dsn
    ):
        raise RootAtomicPublicationConflict(
            "release and authority-root registries are not the same PostgreSQL control plane"
        )
    return authority_root_registry


def compare_and_swap_release_under_authority_root(
    release_registry: PostgresReleaseRegistry,
    authority_root_registry: object,
    key: ReleaseKey,
    *,
    expected_release_id: str | None,
    new_release_id: str,
    expected_root_id: str,
) -> None:
    """CAS the release pointer while holding a row lock on the exact season root pointer.

    The root ``SELECT ... FOR UPDATE`` and release-pointer CAS execute on one connection and
    transaction. A concurrent authority-root CAS therefore cannot commit between root
    verification and release publication. It either linearizes before this transaction (and
    publication fails) or after this transaction commits (and answer-time root replay then
    determines whether the release remains actionable).
    """

    root_registry = _require_same_control_plane(release_registry, authority_root_registry)
    if key.season != str(key.season).strip() or not key.season:
        raise ValueError("release key season is invalid")
    new_release_id = str(new_release_id).strip()
    if not new_release_id:
        raise ValueError("new_release_id is required")
    expected_root_digest = _root_digest(expected_root_id)
    schema = release_registry.schema

    with psycopg.connect(release_registry._dsn) as conn:
        with conn.cursor() as cursor:
            # This lock is the linearization boundary shared with
            # PostgresAuthorityRootRegistry.compare_and_swap_current(), whose UPDATE of the
            # same row must wait for this transaction to finish.
            cursor.execute(
                sql.SQL(
                    "SELECT root_id FROM {} WHERE season = %s FOR UPDATE"
                ).format(sql.Identifier(schema, "authority_root_pointers")),
                (key.season,),
            )
            root_row = cursor.fetchone()
            current_root_digest = None if root_row is None else str(root_row[0]).strip()
            if current_root_digest != expected_root_digest:
                raise RootAtomicPublicationConflict(
                    "production authority root changed before atomic release publication"
                )

            cursor.execute(
                sql.SQL("SELECT 1 FROM {} WHERE release_id = %s").format(
                    sql.Identifier(schema, "releases")
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
                    ).format(sql.Identifier(schema, "release_pointers")),
                    (key.season, key.entry, key.gameweek, new_release_id),
                )
            else:
                cursor.execute(
                    sql.SQL(
                        "UPDATE {} SET release_id = %s, updated_at = CURRENT_TIMESTAMP "
                        "WHERE season = %s AND entry = %s AND gameweek = %s "
                        "AND release_id = %s RETURNING release_id"
                    ).format(sql.Identifier(schema, "release_pointers")),
                    (
                        new_release_id,
                        key.season,
                        key.entry,
                        key.gameweek,
                        str(expected_release_id),
                    ),
                )
            if cursor.fetchone() is None:
                raise CompareAndSwapConflict(
                    f"stale release writer for {key}: expected {expected_release_id!r}"
                )

            # Re-read under the same root lock before commit. This is redundant for PostgreSQL
            # row locking but retained as an executable invariant against future SQL changes.
            cursor.execute(
                sql.SQL("SELECT root_id FROM {} WHERE season = %s").format(
                    sql.Identifier(schema, "authority_root_pointers")
                ),
                (key.season,),
            )
            final_root_row = cursor.fetchone()
            final_root_digest = (
                None if final_root_row is None else str(final_root_row[0]).strip()
            )
            if final_root_digest != expected_root_digest:
                raise RootAtomicPublicationConflict(
                    "production authority root changed inside atomic publication transaction"
                )

    # Credential-safe adapter relationship sanity check. The object is otherwise intentionally
    # unused after transaction commit; retaining the local name makes the verified pairing clear.
    assert root_registry.schema == release_registry.schema
