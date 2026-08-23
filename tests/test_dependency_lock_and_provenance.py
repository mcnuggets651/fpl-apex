from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from pathlib import Path
import re

import pytest

from apex_fpl.control.provenance import BuildManifest


ROOT = Path(__file__).resolve().parents[1]
PIN = re.compile(r"^[A-Za-z0-9_.-]+==[^=\s]+$")


def _pins(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        assert PIN.fullmatch(line), line
        name, version = line.split("==", 1)
        result[name.casefold()] = version
    return result


def test_dependency_locks_are_fully_exact_and_runtime_is_subset_of_ci() -> None:
    runtime = _pins(ROOT / "requirements.runtime.lock")
    ci = _pins(ROOT / "requirements.lock")
    assert runtime
    assert runtime.items() <= ci.items()
    for required in (
        "requests",
        "pandas",
        "numpy",
        "scipy",
        "pyyaml",
        "typer",
        "rich",
        "tabulate",
    ):
        assert required in runtime
    for required in ("pytest", "pytest-cov", "ruff", "setuptools", "wheel"):
        assert required in ci


def test_build_system_tools_are_exactly_pinned() -> None:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert '"setuptools==84.0.0"' in text
    assert '"wheel==0.48.0"' in text
    assert "setuptools>=" not in text


def test_docker_base_and_dependency_install_are_immutable() -> None:
    text = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert (
        "python:3.12.14-slim-bookworm@sha256:"
        "a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
    ) in text
    assert "--no-deps -r requirements.runtime.lock" in text
    assert "--no-build-isolation" in text
    assert "pip install --upgrade" not in text


def test_build_manifest_identity_is_content_bound() -> None:
    digest = "sha256:" + "a" * 64
    manifest = BuildManifest(
        source_sha="b" * 40,
        dependency_lock_digest=digest,
        runtime_digest="sha256:" + "c" * 64,
        base_image_digest="sha256:" + "d" * 64,
        builder_identity="github-actions:test",
        built_at="2026-08-23T20:00:00Z",
        sbom_artifact_id="sha256:" + "e" * 64,
        provenance_artifact_id="sha256:" + "f" * 64,
        action_pins=(("actions/checkout", "1" * 40),),
    )
    changed = replace(manifest, runtime_digest="sha256:" + "9" * 64)
    assert manifest.build_manifest_id.startswith("sha256:")
    assert manifest.build_manifest_id != changed.build_manifest_id


def test_build_manifest_rejects_mutable_or_short_identity() -> None:
    with pytest.raises(ValueError, match="source_sha"):
        BuildManifest(
            source_sha="main",
            dependency_lock_digest="sha256:" + "a" * 64,
            runtime_digest="sha256:" + "b" * 64,
            base_image_digest="sha256:" + "c" * 64,
            builder_identity="builder",
            built_at="time",
            sbom_artifact_id="sha256:" + "d" * 64,
            provenance_artifact_id="sha256:" + "e" * 64,
        )


def test_runtime_lock_digest_is_stable_bytes() -> None:
    digest = sha256((ROOT / "requirements.runtime.lock").read_bytes()).hexdigest()
    assert len(digest) == 64
