from __future__ import annotations

import json
from types import SimpleNamespace

from typer.testing import CliRunner

import apex_fpl.v2_operations_cli as cli


class _Authority:
    def __init__(self, *, current: bool) -> None:
        self.publication_eligible = current
        self.authority_id = "sha256:" + ("a" * 64)
        self._current = current

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-answer-authority",
            "schema_version": 1,
            "season": "2026-2027",
            "entry": 63984,
            "gameweek": 2,
            "status": "CURRENT" if self._current else "UNAVAILABLE",
            "release_id": "sha256:" + ("b" * 64) if self._current else None,
            "bundle_id": "sha256:" + ("c" * 64) if self._current else None,
            "world_id": "sha256:" + ("d" * 64) if self._current else None,
            "runtime_digest": "runtime" if self._current else None,
            "artifact_manifest_id": "sha256:" + ("e" * 64) if self._current else None,
            "blockers": [] if self._current else ["no current V2 production release"],
            "publication_eligible": self._current,
            "ready_to_act": self._current,
            "safe_to_act": self._current,
        }


def _runtime() -> SimpleNamespace:
    return SimpleNamespace(
        artifact_store=object(),
        release_registry=object(),
        authority_root_registry=object(),
    )


def test_authority_status_passes_complete_production_adapter_bundle(monkeypatch) -> None:
    runtime = _runtime()
    captured: dict[str, object] = {}

    def fake_resolve(**kwargs):
        captured.update(kwargs)
        return _Authority(current=True)

    monkeypatch.setattr(cli, "load_production_backend_runtime", lambda: runtime)
    monkeypatch.setattr(cli, "resolve_production_answer_authority", fake_resolve)

    as_of = "2026-08-27T21:00:00+00:00"
    result = CliRunner().invoke(
        cli.app,
        [
            "authority-status",
            "--season",
            "2026-2027",
            "--entry",
            "63984",
            "--gameweek",
            "2",
            "--as-of",
            as_of,
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["artifact_store"] is runtime.artifact_store
    assert captured["production_registry"] is runtime.release_registry
    assert captured["authority_root_registry"] is runtime.authority_root_registry
    assert captured["as_of"] == as_of
    payload = json.loads(result.output)
    assert payload["status"] == "CURRENT"
    assert payload["publication_eligible"] is True
    assert payload["as_of"] == as_of


def test_authority_status_exits_two_without_exposing_actionable_payload(monkeypatch) -> None:
    runtime = _runtime()
    monkeypatch.setattr(cli, "load_production_backend_runtime", lambda: runtime)
    monkeypatch.setattr(
        cli,
        "resolve_production_answer_authority",
        lambda **_: _Authority(current=False),
    )

    result = CliRunner().invoke(
        cli.app,
        [
            "authority-status",
            "--season",
            "2026-2027",
            "--entry",
            "63984",
            "--gameweek",
            "2",
            "--as-of",
            "2026-08-27T21:00:00+00:00",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["status"] == "UNAVAILABLE"
    assert payload["publication_eligible"] is False
    assert payload["bundle_id"] is None
    assert payload["release_id"] is None
