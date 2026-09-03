from __future__ import annotations

import json
import platform
import re
import tomllib
from pathlib import Path

import pytest

from apex.runtime import provenance as provenance_module
from apex.runtime.provenance import (
    build_cyclonedx_sbom,
    build_provenance,
    canonical_package_name,
    read_exact_lock,
    verify_installed_against_lock,
)

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "requirements-v2.lock"
WORKFLOW = ROOT / ".github/workflows/apex-v2-ci.yml"


def _requirement_name(spec: str) -> str:
    name = re.split(r"[<>=!~@\[\s]", spec, maxsplit=1)[0]
    return canonical_package_name(name)


def test_v2_lock_covers_runtime_dev_and_build_dependencies_exactly():
    lock = read_exact_lock(LOCK)
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    declared = {
        _requirement_name(spec)
        for spec in pyproject["project"]["dependencies"]
    }
    declared.update(
        _requirement_name(spec)
        for spec in pyproject["project"]["optional-dependencies"]["dev"]
    )
    build_requires = pyproject["build-system"]["requires"]
    assert build_requires == ["setuptools==80.9.0", "wheel==0.45.1"]
    declared.update(_requirement_name(spec) for spec in build_requires)
    assert declared <= set(lock)
    assert lock["pip"] == "26.2.1"


def test_v2_ci_uses_exact_python_and_sealed_install_path():
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert 'python-version: "3.12.14"' in workflow
    assert "pip==26.2.1" in workflow
    assert "setuptools==80.9.0" in workflow
    assert "wheel==0.45.1" in workflow
    assert "--no-build-isolation" in workflow
    assert "-c requirements-v2.lock" in workflow
    assert "check_v2_dependency_lock.py" in workflow
    assert "build_v2_provenance.py" in workflow
    assert "provenance.json" in workflow
    assert "sbom.cdx.json" in workflow


def test_environment_verifier_rejects_missing_and_mismatched_locked_packages(
    monkeypatch,
):
    monkeypatch.setattr(
        provenance_module,
        "installed_distributions",
        lambda: {
            "numpy": "2.5.1",
            "apex-fpl": "0.2.0.dev0",
        },
    )
    errors = verify_installed_against_lock(
        {
            "numpy": "2.5.2",
            "setuptools": "80.9.0",
        }
    )
    assert "version mismatch: numpy expected 2.5.2, installed 2.5.1" in errors
    assert "missing locked distribution: setuptools==80.9.0" in errors


def test_provenance_and_sbom_bind_candidate_environment(monkeypatch):
    # Structure generation is independent of the runner's package inventory.
    # Exact installed-vs-lock enforcement has its own negative test above and is
    # exercised for real by the pinned Apex V2 CI workflow before provenance is built.
    monkeypatch.setattr(
        provenance_module,
        "verify_installed_against_lock",
        lambda lock: (),
    )
    engine_sha = "a" * 40
    provenance = build_provenance(
        ROOT,
        engine_sha=engine_sha,
        lock_path=LOCK,
        workflow_path=WORKFLOW,
        upstreams_path=ROOT / "upstreams.lock.json",
    )
    assert provenance["engine_sha"] == engine_sha
    assert provenance["python"]["version"] == platform.python_version()
    paths = {entry["path"] for entry in provenance["files"]}
    assert {
        "pyproject.toml",
        "requirements-v2.lock",
        ".github/workflows/apex-v2-ci.yml",
        "upstreams.lock.json",
    } <= paths
    assert provenance["github_actions"]
    assert all(
        re.fullmatch(r"[0-9a-f]{40}", item["sha"])
        for item in provenance["github_actions"]
    )

    sbom = build_cyclonedx_sbom(provenance)
    assert sbom["bomFormat"] == "CycloneDX"
    assert sbom["specVersion"] == "1.6"
    assert sbom["metadata"]["component"]["properties"] == [
        {"name": "apex.engine.sha", "value": engine_sha}
    ]
    locked = read_exact_lock(LOCK)
    components = {
        component["name"]: component["version"]
        for component in sbom["components"]
    }
    assert components == locked


def test_exact_lock_parser_rejects_inexact_and_duplicate_entries(tmp_path: Path):
    inexact = tmp_path / "inexact.lock"
    inexact.write_text("numpy>=2\n", encoding="utf-8")
    with pytest.raises(ValueError, match="exact"):
        read_exact_lock(inexact)

    duplicate = tmp_path / "duplicate.lock"
    duplicate.write_text("PyYAML==6.0.3\npyyaml==6.0.3\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        read_exact_lock(duplicate)


def test_written_provenance_json_contains_no_nan(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(
        provenance_module,
        "verify_installed_against_lock",
        lambda lock: (),
    )
    provenance = build_provenance(
        ROOT,
        engine_sha="b" * 40,
        lock_path=LOCK,
        workflow_path=WORKFLOW,
        upstreams_path=ROOT / "upstreams.lock.json",
    )
    encoded = json.dumps(provenance, allow_nan=False, sort_keys=True)
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
