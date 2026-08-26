"""Fail-closed runtime selection for the V2 production control plane.

Production operations must never silently fall back to the reference filesystem adapters.
The PostgreSQL DSN is read only from the process environment, is never included in returned
identity/report payloads, and is never persisted as Apex backend identity.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Mapping

from apex_fpl.control.postgres_backend import PostgresArtifactStore, PostgresReleaseRegistry


PRODUCTION_POSTGRES_DSN_ENV = "APEX_PRODUCTION_POSTGRES_DSN"
PRODUCTION_POSTGRES_SCHEMA_ENV = "APEX_PRODUCTION_POSTGRES_SCHEMA"
DEFAULT_PRODUCTION_POSTGRES_SCHEMA = "apex_v2"


@dataclass(frozen=True, slots=True)
class ProductionBackendRuntime:
    artifact_store: PostgresArtifactStore
    release_registry: PostgresReleaseRegistry
    schema: str

    def identity_payload(self) -> dict[str, object]:
        """Credential-safe identity witness suitable for operator output and retained evidence."""

        return {
            "schema_name": "apex-production-backend-runtime-identity",
            "schema_version": 1,
            "backend_kind": "POSTGRESQL",
            "schema": self.schema,
            "artifact_store_backend_id": self.artifact_store.backend_id,
            "release_registry_backend_id": self.release_registry.backend_id,
        }


def load_production_backend_runtime(
    environ: Mapping[str, str] | None = None,
) -> ProductionBackendRuntime:
    """Resolve the real production backend without any reference/local fallback.

    Schema/bootstrap is intentionally an administrative operation. This loader only opens an
    already-initialised control plane and fails closed if the production DSN is missing, invalid
    or points at an uninitialised schema.
    """

    env = os.environ if environ is None else environ
    dsn = str(env.get(PRODUCTION_POSTGRES_DSN_ENV, "")).strip()
    if not dsn:
        raise RuntimeError(
            f"{PRODUCTION_POSTGRES_DSN_ENV} is required; production backend selection "
            "has no filesystem fallback"
        )
    schema = str(
        env.get(PRODUCTION_POSTGRES_SCHEMA_ENV, DEFAULT_PRODUCTION_POSTGRES_SCHEMA)
    ).strip()
    if not schema:
        raise RuntimeError(f"{PRODUCTION_POSTGRES_SCHEMA_ENV} cannot be empty")

    try:
        artifact_store = PostgresArtifactStore(dsn, schema=schema)
        release_registry = PostgresReleaseRegistry(dsn, schema=schema)
    except Exception as exc:  # normalize credential/connection/bootstrap failures at trust boundary
        raise RuntimeError(
            "production PostgreSQL control plane is unavailable or uninitialised"
        ) from exc

    if not artifact_store.backend_id.startswith("apex.production.postgres-artifact-store.v1:"):
        raise RuntimeError("production ArtifactStore identity is not a PostgreSQL production ID")
    if not release_registry.backend_id.startswith(
        "apex.production.postgres-release-registry.v1:"
    ):
        raise RuntimeError("production ReleaseRegistry identity is not a PostgreSQL production ID")

    return ProductionBackendRuntime(
        artifact_store=artifact_store,
        release_registry=release_registry,
        schema=schema,
    )
