from __future__ import annotations

import pytest

import apex_fpl.control.production_backend_runtime as runtime_module
from apex_fpl.control.production_backend_runtime import load_production_backend_runtime


class _FakeArtifactStore:
    def __init__(self, dsn: str, *, schema: str):
        assert dsn == "postgresql://secret-user:secret-pass@example/apex"
        self.schema = schema
        self.backend_id = "apex.production.postgres-artifact-store.v1:artifact-instance"


class _FakeReleaseRegistry:
    def __init__(self, dsn: str, *, schema: str):
        assert dsn == "postgresql://secret-user:secret-pass@example/apex"
        self.schema = schema
        self.backend_id = "apex.production.postgres-release-registry.v1:registry-instance"


def test_production_backend_runtime_has_no_filesystem_fallback() -> None:
    with pytest.raises(RuntimeError, match="no filesystem fallback"):
        load_production_backend_runtime({})


def test_production_backend_identity_output_never_contains_dsn_or_credentials(monkeypatch) -> None:
    monkeypatch.setattr(runtime_module, "PostgresArtifactStore", _FakeArtifactStore)
    monkeypatch.setattr(runtime_module, "PostgresReleaseRegistry", _FakeReleaseRegistry)
    runtime = load_production_backend_runtime(
        {
            "APEX_PRODUCTION_POSTGRES_DSN": "postgresql://secret-user:secret-pass@example/apex",
            "APEX_PRODUCTION_POSTGRES_SCHEMA": "apex_prod",
        }
    )
    payload = runtime.identity_payload()
    text = repr(payload)
    assert payload["schema"] == "apex_prod"
    assert payload["backend_kind"] == "POSTGRESQL"
    assert "secret-user" not in text
    assert "secret-pass" not in text
    assert "postgresql://" not in text


def test_connection_failure_is_normalized_without_dsn_leak(monkeypatch) -> None:
    class _FailingStore:
        def __init__(self, dsn: str, *, schema: str):
            raise RuntimeError(f"driver failure for {dsn} schema={schema}")

    monkeypatch.setattr(runtime_module, "PostgresArtifactStore", _FailingStore)
    with pytest.raises(RuntimeError, match="unavailable or uninitialised") as exc:
        load_production_backend_runtime(
            {"APEX_PRODUCTION_POSTGRES_DSN": "postgresql://top-secret@example/apex"}
        )
    assert "top-secret" not in str(exc.value)
    assert exc.value.__cause__ is None
    assert exc.value.__context__ is None


def test_empty_production_schema_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(runtime_module, "PostgresArtifactStore", _FakeArtifactStore)
    monkeypatch.setattr(runtime_module, "PostgresReleaseRegistry", _FakeReleaseRegistry)
    with pytest.raises(RuntimeError, match="cannot be empty"):
        load_production_backend_runtime(
            {
                "APEX_PRODUCTION_POSTGRES_DSN": "postgresql://secret-user:secret-pass@example/apex",
                "APEX_PRODUCTION_POSTGRES_SCHEMA": "   ",
            }
        )
