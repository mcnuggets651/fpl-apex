#!/usr/bin/env python3
"""Validate the canonical FPL Apex capability registry and PR change surface.

The registry is deliberately semantic. It points to machine authority for movable
serving facts instead of copying them. This checker therefore validates:

* schema, IDs, dependency references and non-research dependency cycles;
* ref-aware entry-point existence on main / authority-selected immutable refs;
* coverage of every active GitHub Actions workflow and ``scripts/apex_v2_*.py``;
* serving and research boundary contracts;
* decision-index linkage to the append-only prose decision register;
* PR changed paths against declared ``Apex-Capabilities`` metadata.

JSON is valid YAML, so the ``.yaml`` registry/index intentionally use the JSON
subset and can be parsed with the Python standard library. This keeps the
continuity checker dependency-free.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

REGISTRY_PATH = Path("docs/APEX_CAPABILITY_REGISTRY.yaml")
AUTHORITY_PATH = Path("docs/APEX_V2_AUTHORITY.json")
DECISION_INDEX_PATH = Path("docs/APEX_DECISION_INDEX.yaml")
DECISION_REGISTER_PATH = Path("docs/APEX_DECISIONS.md")
MASTER_PATH = "docs/FPL_APEX_MASTER_STATE.md"

ID_RE = re.compile(r"^(GOV|PROD|OPS|RES|PRIV|INT|LEG)-\d{3}$")
DECISION_RE = re.compile(r"^D\d{3}$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# These are the constitution's own control files. They are not duplicated in
# every capability change_surface merely to make the checker self-hosting.
CONSTITUTION_CONTROL_SURFACE = {
    "docs/APEX_CAPABILITY_REGISTRY.yaml": "GOV-003",
    "docs/APEX_DECISION_INDEX.yaml": "GOV-003",
    "docs/APEX_DECISIONS.md": "GOV-003",
    "docs/APEX_ARCHITECTURE.md": "GOV-003",
    "scripts/check_capability_registry.py": "GOV-003",
    "ops_tests/test_capability_registry_contract.py": "GOV-003",
    ".github/pull_request_template.md": "GOV-003",
    MASTER_PATH: "GOV-002",
    "docs/APEX_V2_AUTHORITY.json": "GOV-001",
}


class ContractError(RuntimeError):
    pass


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and proc.returncode != 0:
        raise ContractError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def load_json_yaml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ContractError(f"missing required registry/index file: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ContractError(f"{path} must use the JSON subset of YAML: {exc}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"{path} root must be an object")
    return value


def require_nonempty(value: Any, field: str, cap_id: str) -> None:
    if value is None or value == "" or value == []:
        raise ContractError(f"{cap_id}: required field {field} is empty")


def capabilities_by_id(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    caps = registry.get("capabilities")
    if not isinstance(caps, list) or not caps:
        raise ContractError("registry capabilities must be a non-empty list")
    result: dict[str, dict[str, Any]] = {}
    for cap in caps:
        if not isinstance(cap, dict):
            raise ContractError("every capability must be an object")
        cap_id = cap.get("id")
        if not isinstance(cap_id, str) or not ID_RE.fullmatch(cap_id):
            raise ContractError(f"invalid capability id: {cap_id!r}")
        if cap_id in result:
            raise ContractError(f"duplicate capability id: {cap_id}")
        result[cap_id] = cap
    return result


def validate_schema(registry: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if registry.get("schema_version") != 1:
        raise ContractError("unsupported capability registry schema_version")
    if registry.get("machine_authority") != str(AUTHORITY_PATH):
        raise ContractError("registry must reference the canonical machine authority")
    if registry.get("master_state") != MASTER_PATH:
        raise ContractError("registry must reference the canonical master state")
    if registry.get("decision_index") != str(DECISION_INDEX_PATH):
        raise ContractError("registry must reference the canonical decision index")
    if registry.get("system_map") != "docs/APEX_ARCHITECTURE.md":
        raise ContractError("registry must reference the single current system map")

    enums = registry.get("enums") or {}
    lifecycle_allowed = set(enums.get("lifecycle") or [])
    plane_allowed = set(enums.get("plane") or [])
    visibility_allowed = set(enums.get("visibility") or [])
    caps = capabilities_by_id(registry)

    required = (
        "name", "purpose", "lifecycle", "plane", "visibility", "owning_repo",
        "authority_refs", "entry_points", "inputs", "outputs", "dependencies",
        "private_data", "invariants", "failure_behavior", "runbooks", "tests",
        "runtime_acceptance", "change_surface", "change_control", "decision_refs",
        "known_limitations", "replacement",
    )
    for cap_id, cap in caps.items():
        for field in required:
            if field not in cap:
                raise ContractError(f"{cap_id}: missing field {field}")
        if cap["lifecycle"] not in lifecycle_allowed:
            raise ContractError(f"{cap_id}: invalid lifecycle {cap['lifecycle']!r}")
        if cap["plane"] not in plane_allowed:
            raise ContractError(f"{cap_id}: invalid plane {cap['plane']!r}")
        if cap["visibility"] not in visibility_allowed:
            raise ContractError(f"{cap_id}: invalid visibility {cap['visibility']!r}")
        for dep in cap["dependencies"]:
            if dep not in caps:
                raise ContractError(f"{cap_id}: unknown dependency {dep}")
        replacement = cap.get("replacement")
        if replacement is not None and replacement not in caps:
            raise ContractError(f"{cap_id}: unknown replacement {replacement}")
        for decision in cap["decision_refs"]:
            if not isinstance(decision, str) or not DECISION_RE.fullmatch(decision):
                raise ContractError(f"{cap_id}: invalid decision reference {decision!r}")

        if cap.get("serving_authorized") is True and cap["lifecycle"] == "active":
            for field in (
                "authority_refs", "runbooks", "tests", "failure_behavior",
                "runtime_acceptance", "invariants",
            ):
                require_nonempty(cap.get(field), field, cap_id)

        if cap["plane"] == "research" and cap["lifecycle"] == "active":
            boundary = cap.get("production_boundary")
            if boundary != {
                "production_influence": "NONE",
                "serve_authorized": False,
                "automatic_promotion": False,
            }:
                raise ContractError(
                    f"{cap_id}: active research capability must explicitly declare "
                    "production_influence=NONE, serve_authorized=false and automatic_promotion=false"
                )
            if cap.get("serving_authorized") is not False:
                raise ContractError(f"{cap_id}: research capability cannot be serving-authorized")

        if cap["lifecycle"] in {"historical", "retired"} and cap.get("serving_authorized") is True:
            raise ContractError(f"{cap_id}: historical/retired capability cannot serve")

    # Dependency cycles are invalid for runtime/governance capabilities. Research
    # relationships can be mutually descriptive (provider <-> tournament), so
    # research-only cycles are intentionally excluded from runtime ordering.
    runtime_nodes = {cid for cid, cap in caps.items() if cap["plane"] != "research"}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str, chain: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            raise ContractError("dependency cycle: " + " -> ".join(chain + [node]))
        visiting.add(node)
        for dep in caps[node]["dependencies"]:
            if dep in runtime_nodes:
                visit(dep, chain + [node])
        visiting.remove(node)
        visited.add(node)

    for node in sorted(runtime_nodes):
        visit(node, [])
    return caps


def authority_ref_sha(ref_name: str, authority: dict[str, Any]) -> str:
    mapping = {
        "authority:production_core_sha": "production_core_sha",
        "authority:frozen_engine_sha": "frozen_engine_sha",
    }
    key = mapping.get(ref_name)
    if not key:
        raise ContractError(f"unknown ref resolver: {ref_name}")
    sha = authority.get(key)
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ContractError(f"authority field {key} is not a valid SHA")
    return sha


def validate_entry_points(
    registry: dict[str, Any], caps: dict[str, dict[str, Any]], *, validate_refs: bool
) -> None:
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    resolvers = registry.get("ref_resolvers") or {}
    for cap_id, cap in caps.items():
        for entry in cap["entry_points"]:
            if not isinstance(entry, dict):
                raise ContractError(f"{cap_id}: entry point must be an object")
            ref = entry.get("ref")
            path = entry.get("path")
            if ref not in resolvers or not isinstance(path, str) or not path:
                raise ContractError(f"{cap_id}: invalid entry point {entry!r}")
            if ref == "main":
                if not Path(path).exists():
                    raise ContractError(f"{cap_id}: main entry point missing: {path}")
            elif ref.startswith("authority:") and validate_refs:
                sha = authority_ref_sha(ref, authority)
                probe = subprocess.run(
                    ["git", "cat-file", "-e", f"{sha}:{path}"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if probe.returncode != 0:
                    raise ContractError(
                        f"{cap_id}: ref-aware entry point missing or ref not fetched: {ref} {path} ({sha})"
                    )
            elif ref == "private:main":
                # Public CI owns the semantic declaration only. The private repo
                # validates its own paths in the follow-up private contract.
                continue


def registry_workflows(caps: dict[str, dict[str, Any]]) -> dict[str, set[str]]:
    owners: dict[str, set[str]] = {}
    for cap_id, cap in caps.items():
        for entry in cap["entry_points"]:
            path = entry.get("path", "")
            if entry.get("ref") == "main" and path.startswith(".github/workflows/"):
                owners.setdefault(path, set()).add(cap_id)
    return owners


def validate_active_surface(caps: dict[str, dict[str, Any]]) -> None:
    owners = registry_workflows(caps)
    active = sorted(
        str(path)
        for path in Path(".github/workflows").glob("*")
        if path.is_file() and path.suffix in {".yml", ".yaml"}
    )
    missing = [path for path in active if path not in owners]
    if missing:
        raise ContractError(f"active workflows missing capability registration: {missing}")

    for path, cap_ids in owners.items():
        if not Path(path).is_file():
            continue
        for cap_id in cap_ids:
            if caps[cap_id]["lifecycle"] == "retired":
                raise ContractError(f"retired capability {cap_id} owns active workflow {path}")

    registered_scripts: dict[str, set[str]] = {}
    for cap_id, cap in caps.items():
        for entry in cap["entry_points"]:
            path = entry.get("path", "")
            if entry.get("ref") == "main" and path.startswith("scripts/apex_v2_") and path.endswith(".py"):
                registered_scripts.setdefault(path, set()).add(cap_id)
    operational = sorted(str(path) for path in Path("scripts").glob("apex_v2_*.py"))
    missing_scripts = [path for path in operational if path not in registered_scripts]
    if missing_scripts:
        raise ContractError(f"operational apex_v2 scripts missing capability registration: {missing_scripts}")


def validate_no_movable_state(registry: dict[str, Any]) -> None:
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    authority = json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    forbidden_values = [
        authority.get("production_core_sha"),
        authority.get("frozen_engine_sha"),
    ]
    for value in forbidden_values:
        if isinstance(value, str) and value in text:
            raise ContractError(
                "capability registry copied a movable/authority SHA instead of using a symbolic authority reference"
            )
    if re.search(r"\b338\d{7,}\b", text):
        raise ContractError("capability registry must not contain workflow/run IDs")
    for forbidden_key in ("current_squad", "bank_gbp", "free_transfers", "latest_release_id", "provider_health"):
        if forbidden_key in text:
            raise ContractError(f"capability registry must not become a live-state dashboard: {forbidden_key}")


def validate_decision_index(caps: dict[str, dict[str, Any]]) -> None:
    index = load_json_yaml(DECISION_INDEX_PATH)
    if index.get("schema_version") != 1:
        raise ContractError("unsupported decision-index schema_version")
    allowed_status = set(index.get("statuses") or [])
    decisions = index.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise ContractError("decision index must contain decisions")
    prose = DECISION_REGISTER_PATH.read_text(encoding="utf-8")
    seen: set[str] = set()
    for item in decisions:
        decision_id = item.get("id")
        if not isinstance(decision_id, str) or not DECISION_RE.fullmatch(decision_id):
            raise ContractError(f"invalid decision index id: {decision_id!r}")
        if decision_id in seen:
            raise ContractError(f"duplicate decision index id: {decision_id}")
        seen.add(decision_id)
        if item.get("status") not in allowed_status:
            raise ContractError(f"{decision_id}: invalid status")
        if f"## {decision_id} " not in prose:
            raise ContractError(f"{decision_id}: missing from append-only prose decision register")
        for cap_id in item.get("capabilities") or []:
            if cap_id not in caps:
                raise ContractError(f"{decision_id}: unknown capability {cap_id}")
        for superseder in item.get("superseded_by") or []:
            if not isinstance(superseder, str) or not DECISION_RE.fullmatch(superseder):
                raise ContractError(f"{decision_id}: invalid superseded_by {superseder!r}")
    prose_ids = set(re.findall(r"^## (D\d{3})\b", prose, flags=re.MULTILINE))
    missing = sorted(prose_ids - seen)
    if missing:
        raise ContractError(f"decision register entries missing machine index: {missing}")


def event_base() -> str | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if event_path and Path(event_path).is_file():
        try:
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            event = {}
        pull = event.get("pull_request") or {}
        base = (pull.get("base") or {}).get("sha")
        if base:
            return str(base)
        before = event.get("before")
        if before and before != "0" * 40:
            return str(before)
    if os.environ.get("GITHUB_BASE_REF"):
        ref = f"origin/{os.environ['GITHUB_BASE_REF']}"
        if git("rev-parse", "--verify", ref, check=False):
            return git("merge-base", "HEAD", ref)
    return None


def event_pr_body() -> str | None:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path or not Path(event_path).is_file():
        return None
    try:
        event = json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    pull = event.get("pull_request")
    if not isinstance(pull, dict):
        return None
    return str(pull.get("body") or "")


def parse_metadata(body: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in body.splitlines():
        match = re.match(r"^(Apex-[A-Za-z-]+):\s*(.*?)\s*$", line.strip())
        if match:
            result[match.group(1)] = match.group(2)
    return result


def path_capabilities(path: str, caps: dict[str, dict[str, Any]]) -> set[str]:
    mapped: set[str] = set()
    fixed = CONSTITUTION_CONTROL_SURFACE.get(path)
    if fixed:
        mapped.add(fixed)
    for cap_id, cap in caps.items():
        for pattern in cap.get("change_surface") or []:
            if fnmatch.fnmatch(path, pattern):
                mapped.add(cap_id)
    return mapped


def validate_changed_surface(
    caps: dict[str, dict[str, Any]], *, base: str | None, explicit_paths: list[str] | None
) -> None:
    if explicit_paths is not None:
        changed = sorted(set(explicit_paths))
    elif base:
        changed = sorted(
            line for line in git("diff", "--name-only", "--no-renames", f"{base}...HEAD").splitlines() if line
        )
    else:
        return
    if not changed:
        return

    mappings = {path: path_capabilities(path, caps) for path in changed}
    unmapped = sorted(path for path, cap_ids in mappings.items() if not cap_ids)
    if unmapped:
        raise ContractError(f"changed paths are outside every registered capability change_surface: {unmapped}")

    body = event_pr_body()
    if body is None:
        return
    metadata = parse_metadata(body)
    required_meta = (
        "Apex-Capabilities",
        "Apex-Authority-Changed",
        "Apex-Invariants-Changed",
        "Apex-Decisions-Reopened",
    )
    missing_meta = [key for key in required_meta if not metadata.get(key)]
    if missing_meta:
        raise ContractError(f"PR is missing capability metadata: {missing_meta}")

    declared = {
        token.strip()
        for token in metadata["Apex-Capabilities"].split(",")
        if token.strip()
    }
    unknown = sorted(declared - set(caps))
    if unknown:
        raise ContractError(f"PR declares unknown capabilities: {unknown}")
    if not declared:
        raise ContractError("PR must declare at least one Apex capability")

    undeclared_paths = sorted(
        path for path, cap_ids in mappings.items() if not (cap_ids & declared)
    )
    if undeclared_paths:
        detail = {path: sorted(mappings[path]) for path in undeclared_paths}
        raise ContractError(f"changed paths not covered by declared capabilities: {detail}")

    unused = sorted(
        cap_id
        for cap_id in declared
        if not any(cap_id in cap_ids for cap_ids in mappings.values())
    )
    if unused:
        raise ContractError(f"PR over-declares unaffected capabilities: {unused}")

    authority_changed = metadata["Apex-Authority-Changed"].lower()
    if authority_changed not in {"yes", "no"}:
        raise ContractError("Apex-Authority-Changed must be yes or no")
    touched_authority = str(AUTHORITY_PATH) in changed
    if touched_authority != (authority_changed == "yes"):
        raise ContractError(
            "Apex-Authority-Changed metadata does not match whether docs/APEX_V2_AUTHORITY.json changed"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="base commit/ref for change-surface validation")
    parser.add_argument("--paths", nargs="*", help="explicit changed paths for tests")
    parser.add_argument(
        "--skip-ref-paths",
        action="store_true",
        help="skip immutable-ref path existence checks (schema/surface checks still run)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry = load_json_yaml(REGISTRY_PATH)
    caps = validate_schema(registry)
    validate_no_movable_state(registry)
    validate_entry_points(registry, caps, validate_refs=not args.skip_ref_paths)
    validate_active_surface(caps)
    validate_decision_index(caps)
    validate_changed_surface(caps, base=args.base or event_base(), explicit_paths=args.paths)
    print(
        f"Apex capability registry OK: {len(caps)} capabilities, "
        f"{len(registry_workflows(caps))} active workflow bindings"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ContractError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
