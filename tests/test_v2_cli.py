from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import apex.cli as cli


runner = CliRunner()


class _FakeStore:
    def __init__(self):
        self.calls = []

    def create_once(self, tag, files, **kwargs):
        self.calls.append((tag, files, kwargs))
        return SimpleNamespace(html_url="https://example.invalid/release")


def test_intent_accepts_exact_production_option_shape(tmp_path: Path, monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(cli, "_store", lambda: store)
    output = tmp_path / "intent.json"

    result = runner.invoke(
        cli.app,
        [
            "intent",
            "--run-id",
            "run-1",
            "--season",
            "2026-2027",
            "--gameweek",
            "0",
            "--code-sha",
            "abc123",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-1"
    assert payload["code_sha"] == "abc123"
    assert store.calls[0][0] == "apex-v2/intent/2026-2027/run-1"
    assert store.calls[0][2]["target_commitish"] == "abc123"


def test_publish_accepts_exact_production_option_shape(tmp_path: Path, monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(cli, "_store", lambda: store)
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    (snapshot / "manifest.json").write_text("{}\n", encoding="utf-8")
    decision = tmp_path / "decision_bundle.json"
    decision.write_text("{}\n", encoding="utf-8")
    artifact_dir = tmp_path / "artifacts"

    result = runner.invoke(
        cli.app,
        [
            "publish",
            str(snapshot),
            str(decision),
            "--season",
            "2026-2027",
            "--gameweek",
            "2",
            "--run-id",
            "run-1",
            "--code-sha",
            "abc123",
            "--artifact-dir",
            str(artifact_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert store.calls[0][0] == "apex-v2/final/2026-2027/run-1"
    assert store.calls[0][2]["target_commitish"] == "abc123"
    assert (artifact_dir / "bundle.tar.gz").is_file()
    assert (artifact_dir / "attestation.json").is_file()
