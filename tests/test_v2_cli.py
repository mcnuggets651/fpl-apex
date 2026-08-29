from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import apex.cli as cli
import apex.runtime.publication as publication


runner = CliRunner()


class _FakeStore:
    def __init__(self):
        self.calls = []

    def create_once(self, tag, files, **kwargs):
        self.calls.append((tag, files, kwargs))
        return SimpleNamespace(
            html_url="https://example.invalid/release",
            immutable=True,
        )


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
    assert set(payload) == set(publication.INTENT_FIELDS_V1)
    assert payload["run_id"] == "run-1"
    assert payload["code_sha"] == "abc123"
    assert store.calls[0][0] == "apex-v2/intent/2026-2027/run-1"
    assert set(store.calls[0][1]) == {"intent.json"}
    assert store.calls[0][2]["target_commitish"] == "abc123"


def _material(tmp_path: Path, *, authenticated: bool):
    public = {}
    for name in publication.PUBLIC_RELEASE_ASSETS_V1:
        path = tmp_path / "public" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"public-safe")
        public[name] = path
    private = {}
    if authenticated:
        for name in publication.PRIVATE_RELEASE_ASSETS_V1:
            path = tmp_path / "private" / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"private-only")
            private[name] = path
    return SimpleNamespace(
        public_files=public,
        private_files=private,
        diagnostics_files={},
        public_attempt_id="public-attempt",
        private_attempt_id="private-attempt" if authenticated else None,
        authenticated_manager_state=authenticated,
    )


def test_publish_exposes_only_six_public_assets(tmp_path: Path, monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(cli, "_store", lambda: store)
    material = _material(tmp_path, authenticated=False)
    monkeypatch.setattr(
        publication,
        "build_publication_materials",
        lambda *args, **kwargs: material,
    )

    result = runner.invoke(
        cli.app,
        [
            "publish",
            str(tmp_path / "snapshot"),
            str(tmp_path / "decision_bundle.json"),
            "--season",
            "2026-2027",
            "--gameweek",
            "3",
            "--run-id",
            "run-1",
            "--code-sha",
            "abc123",
            "--artifact-dir",
            str(tmp_path / "artifacts"),
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(store.calls) == 1
    tag, files, kwargs = store.calls[0]
    assert tag == "apex-v2/final/2026-2027/run-1"
    assert frozenset(files) == publication.PUBLIC_RELEASE_ASSETS_V1
    assert "decision_bundle.json" not in files
    assert "bundle.tar.gz" not in files
    assert kwargs["target_commitish"] == "abc123"


def test_authenticated_publish_fails_before_public_if_private_store_missing(
    tmp_path: Path,
    monkeypatch,
):
    public_store = _FakeStore()
    monkeypatch.setattr(cli, "_store", lambda: public_store)
    material = _material(tmp_path, authenticated=True)
    monkeypatch.setattr(
        publication,
        "build_publication_materials",
        lambda *args, **kwargs: material,
    )
    monkeypatch.delenv("APEX_PRIVATE_GITHUB_REPOSITORY", raising=False)
    monkeypatch.delenv("APEX_PRIVATE_GITHUB_TOKEN", raising=False)

    result = runner.invoke(
        cli.app,
        [
            "publish",
            str(tmp_path / "snapshot"),
            str(tmp_path / "decision_bundle.json"),
            "--season",
            "2026-2027",
            "--gameweek",
            "3",
            "--run-id",
            "run-1",
            "--code-sha",
            "abc123",
        ],
    )

    assert result.exit_code != 0
    assert public_store.calls == []


def test_authenticated_publish_persists_private_before_public(
    tmp_path: Path,
    monkeypatch,
):
    public_store = _FakeStore()
    private_store = _FakeStore()
    monkeypatch.setattr(cli, "_store", lambda: public_store)
    monkeypatch.setattr(cli, "_private_store", lambda: private_store)
    material = _material(tmp_path, authenticated=True)
    monkeypatch.setattr(
        publication,
        "build_publication_materials",
        lambda *args, **kwargs: material,
    )

    result = runner.invoke(
        cli.app,
        [
            "publish",
            str(tmp_path / "snapshot"),
            str(tmp_path / "decision_bundle.json"),
            "--season",
            "2026-2027",
            "--gameweek",
            "3",
            "--run-id",
            "run-1",
            "--code-sha",
            "abc123",
        ],
    )

    assert result.exit_code == 0, result.output
    assert len(private_store.calls) == 1
    assert frozenset(private_store.calls[0][1]) == publication.PRIVATE_RELEASE_ASSETS_V1
    assert len(public_store.calls) == 1
    assert frozenset(public_store.calls[0][1]) == publication.PUBLIC_RELEASE_ASSETS_V1
