from __future__ import annotations

import hashlib
import importlib.metadata
import json
import platform
import re
import sys
from pathlib import Path

_EXACT_REQUIREMENT = re.compile(r"^([A-Za-z0-9_.-]+)==([^\s]+)$")
_ACTION_PIN = re.compile(r"uses:\s*([^\s@]+)@([0-9a-f]{40})")
_SHA40 = re.compile(r"^[0-9a-f]{40}$")


def canonical_package_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_exact_lock(path: Path) -> dict[str, str]:
    locked: dict[str, str] = {}
    for line_number, raw in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        match = _EXACT_REQUIREMENT.fullmatch(line)
        if match is None:
            raise ValueError(f"lock line {line_number} is not an exact name==version pin: {line}")
        name = canonical_package_name(match.group(1))
        if name in locked:
            raise ValueError(f"duplicate dependency lock entry: {name}")
        locked[name] = match.group(2)
    if not locked:
        raise ValueError("dependency lock is empty")
    return locked


def installed_distributions() -> dict[str, str]:
    installed: dict[str, str] = {}
    for distribution in importlib.metadata.distributions():
        name = distribution.metadata.get("Name")
        if not name:
            continue
        installed[canonical_package_name(name)] = distribution.version
    return installed


def verify_installed_against_lock(
    lock: dict[str, str],
    *,
    allow_unlocked: frozenset[str] = frozenset({"apex-fpl"}),
) -> tuple[str, ...]:
    installed = installed_distributions()
    errors: list[str] = []
    for name, expected in sorted(lock.items()):
        actual = installed.get(name)
        if actual is None:
            errors.append(f"missing locked distribution: {name}=={expected}")
        elif actual != expected:
            errors.append(f"version mismatch: {name} expected {expected}, installed {actual}")
    allowed = {canonical_package_name(name) for name in allow_unlocked}
    unexpected = sorted(set(installed) - set(lock) - allowed)
    if unexpected:
        errors.append("unlocked installed distributions: " + ", ".join(unexpected))
    return tuple(errors)


def action_pins(workflow_path: Path) -> tuple[dict[str, str], ...]:
    text = Path(workflow_path).read_text(encoding="utf-8")
    pins = {
        (repository, sha)
        for repository, sha in _ACTION_PIN.findall(text)
    }
    return tuple(
        {"repository": repository, "sha": sha}
        for repository, sha in sorted(pins)
    )


def _file_record(path: Path, root: Path) -> dict[str, str]:
    return {
        "path": Path(path).relative_to(root).as_posix(),
        "sha256": sha256_file(path),
    }


def build_provenance(
    root: Path,
    *,
    engine_sha: str,
    lock_path: Path,
    workflow_path: Path,
    upstreams_path: Path | None = None,
) -> dict:
    root = Path(root).resolve()
    if _SHA40.fullmatch(engine_sha) is None:
        raise ValueError("engine_sha must be an exact lowercase 40-hex Git SHA")
    lock_path = Path(lock_path).resolve()
    workflow_path = Path(workflow_path).resolve()
    lock = read_exact_lock(lock_path)
    errors = verify_installed_against_lock(lock)
    if errors:
        raise RuntimeError("; ".join(errors))

    files = [
        _file_record(root / "pyproject.toml", root),
        _file_record(lock_path, root),
        _file_record(workflow_path, root),
    ]
    if upstreams_path is not None and Path(upstreams_path).is_file():
        files.append(_file_record(Path(upstreams_path).resolve(), root))

    return {
        "schema_version": 1,
        "engine_sha": engine_sha,
        "python": {
            "implementation": platform.python_implementation(),
            "version": platform.python_version(),
            "executable_version": sys.version.split()[0],
        },
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "files": sorted(files, key=lambda item: item["path"]),
        "github_actions": list(action_pins(workflow_path)),
        "dependencies": [
            {"name": name, "version": version}
            for name, version in sorted(lock.items())
        ],
    }


def build_cyclonedx_sbom(provenance: dict) -> dict:
    engine_sha = str(provenance["engine_sha"])
    components = []
    for dependency in provenance["dependencies"]:
        name = dependency["name"]
        version = dependency["version"]
        components.append(
            {
                "type": "library",
                "name": name,
                "version": version,
                "purl": f"pkg:pypi/{name}@{version}",
            }
        )
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "metadata": {
            "component": {
                "type": "application",
                "name": "apex-fpl-v2",
                "version": engine_sha[:12],
                "properties": [
                    {"name": "apex.engine.sha", "value": engine_sha},
                ],
            }
        },
        "components": components,
    }


def write_reproducibility_artifacts(
    root: Path,
    output_dir: Path,
    *,
    engine_sha: str,
    lock_path: Path,
    workflow_path: Path,
    upstreams_path: Path | None = None,
) -> tuple[Path, Path]:
    provenance = build_provenance(
        root,
        engine_sha=engine_sha,
        lock_path=lock_path,
        workflow_path=workflow_path,
        upstreams_path=upstreams_path,
    )
    sbom = build_cyclonedx_sbom(provenance)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    provenance_path = output_dir / "provenance.json"
    sbom_path = output_dir / "sbom.cdx.json"
    provenance_path.write_text(
        json.dumps(provenance, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    sbom_path.write_text(
        json.dumps(sbom, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return provenance_path, sbom_path
