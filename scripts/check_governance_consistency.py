#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml


AUTHORITY_MANIFEST = Path("docs/APEX_V2_AUTHORITY.json")
FROZEN_SHA = "99cc7b51b0cff45462b567084cb1844cfe0a456f"
SEASON = "2026-2027"
ENTRY_ID = 63984
SERVING_PROVIDER = "airsenal"
SERVING_WORKFLOW = ".github/workflows/apex-v2-daily-production.yml"

SERVING_PRODUCTION_WORKFLOWS = {"apex-v2-daily-production.yml"}
OPERATIONS_RESEARCH_WORKFLOWS = {
    "apex-v2-auth-keepalive.yml",
    "apex-v2-daily-evaluation.yml",
    "apex-v2-deadline-watch.yml",
    "apex-v2-decision-quality.yml",
    "apex-v2-direct-auth-diagnostic.yml",
    "apex-v2-ops-contract.yml",
    "apex-v2-owner-brief.yml",
    "apex-v2-prospective-tournament.yml",
    "apex-v2-shadow-health.yml",
    "apex.yml",
    "joint-path-promotion-audit.yml",
    "production-readiness.yml",
    "projection-policy-audit.yml",
    "projection-shadow-audit.yml",
    "team-strength-validation.yml",
    "understat-player-production-ab.yml",
}
LEGACY_EXECUTABLE_WORKFLOWS = {
    "pinnacle.yml",
    "airsenal.yml",
    "refresh-core-pin.yml",
    "gw1-final-2026.yml",
}
REQUIRED_ARCHIVED_WORKFLOWS = {
    "bootstrap-publish.yml",
    "publish-apex.yml",
    "fixture-blend-decision-audit.yml",
    "joint-initial-path-audit.yml",
    "solver-parity.yml",
    "understat-player-predictive-audit.yml",
    *LEGACY_EXECUTABLE_WORKFLOWS,
}
CANONICAL_AUTHORITY_DOCS = (
    Path("README.md"),
    Path("PROJECT_STATUS.md"),
    Path("docs/CURRENT_STATE.md"),
    Path("docs/APEX_MASTER_CONTEXT.md"),
    Path("docs/APEX_OPERATING_MANUAL.md"),
    Path("docs/KNOWN_ISSUES.md"),
    Path("docs/CHATGPT_USAGE.md"),
    Path("docs/CHATGPT_APEX_QUERY_POLICY.md"),
    Path("docs/APEX_ROADMAP.md"),
)
STALE_CURRENT_CLAIMS = {
    "pinnacle production claim": re.compile(
        r"pinnacle\s+(?:is|as)\s+(?:the\s+)?(?:current\s+)?production recommendation",
        re.IGNORECASE,
    ),
    "legacy runner production claim": re.compile(
        r"(?:the\s+)?only production (?:command|entrypoint)\s+is[^\n]*run_apex\.py",
        re.IGNORECASE,
    ),
    "old production sha claim": re.compile(
        r"latest production publication:\s*`?a147754", re.IGNORECASE
    ),
    "old GW1 baseline claim": re.compile(
        r"post-PR\s*#25 publication at\s*`?a147754", re.IGNORECASE
    ),
    "old architecture freeze claim": re.compile(
        r"architecture freeze after PR\s*#64", re.IGNORECASE
    ),
    "legacy Pinnacle startup rule": re.compile(
        r"read\s+`?data/generated/pinnacle_latest\.json`?\s+first", re.IGNORECASE
    ),
}


def _text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def _git_text(ref: str, path: str) -> str:
    """Read a file from an exact Git object, fetching that SHA if a shallow clone lacks it."""
    target = f"{ref}:{path}"
    shown = subprocess.run(
        ["git", "show", target],
        capture_output=True,
        text=True,
        check=False,
    )
    if shown.returncode == 0:
        return shown.stdout

    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if fetched.returncode != 0:
        raise RuntimeError(
            f"unable to fetch frozen authority ref {ref}: {fetched.stderr.strip()}"
        )
    shown = subprocess.run(
        ["git", "show", target],
        capture_output=True,
        text=True,
        check=False,
    )
    if shown.returncode != 0:
        raise RuntimeError(
            f"unable to read frozen authority file {target}: {shown.stderr.strip()}"
        )
    return shown.stdout


def _load_manifest() -> dict:
    if not AUTHORITY_MANIFEST.exists():
        raise SystemExit(f"missing V2 authority manifest: {AUTHORITY_MANIFEST}")
    return json.loads(AUTHORITY_MANIFEST.read_text(encoding="utf-8"))


def _check_manifest(failures: list[str]) -> dict:
    manifest = _load_manifest()
    expected = {
        "schema_version": 1,
        "season": SEASON,
        "entry_id": ENTRY_ID,
        "frozen_engine_sha": FROZEN_SHA,
        "frozen_engine_pr": 90,
        "frozen_engine_pr_policy": "NEVER_MERGE_OR_ADVANCE",
        "serving_provider": SERVING_PROVIDER,
        "serving_horizons": list(range(1, 9)),
        "canonical_production_workflow": SERVING_WORKFLOW,
        "canonical_release_prefix": "apex-v2",
        "operations_control_plane_branch": "main",
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            failures.append(
                f"authority manifest drifted: {key} expected={value!r} actual={manifest.get(key)!r}"
            )
    research = manifest.get("research") or {}
    if research.get("production_influence") != "NONE":
        failures.append("authority manifest permits research production influence")
    if research.get("serving_authorized") is not False:
        failures.append("authority manifest permits research serving")
    if research.get("automatic_promotion") is not False:
        failures.append("authority manifest permits automatic challenger promotion")
    return manifest


def _check_frozen_config(manifest: dict, failures: list[str]) -> None:
    try:
        config = yaml.safe_load(_git_text(FROZEN_SHA, "config/apex_v2.yaml"))
    except (RuntimeError, yaml.YAMLError) as exc:
        failures.append(f"unable to validate exact frozen V2 config: {exc}")
        return

    if config.get("season") != manifest.get("season"):
        failures.append("authority manifest season disagrees with frozen config")
    if config.get("entry_id") != manifest.get("entry_id"):
        failures.append("authority manifest entry disagrees with frozen config")
    if config.get("max_horizon") != 8:
        failures.append("frozen V2 max horizon drifted from 8")

    providers = {row["id"]: row for row in config.get("providers") or []}
    declared = manifest.get("provider_constitution") or {}
    if set(providers) != set(declared):
        failures.append(
            f"provider constitution differs from frozen config: config={sorted(providers)} manifest={sorted(declared)}"
        )
        return
    for provider_id, expected in declared.items():
        actual = providers[provider_id]
        if actual.get("role") != expected.get("role"):
            failures.append(f"provider role drifted for {provider_id}")
        if actual.get("serve_authorized") is not expected.get("serve_authorized"):
            failures.append(f"provider serving authority drifted for {provider_id}")
        if actual.get("requested_horizons") != expected.get("horizons"):
            failures.append(f"provider horizon contract drifted for {provider_id}")
    serving = [pid for pid, row in providers.items() if row.get("serve_authorized") is True]
    if serving != [SERVING_PROVIDER]:
        failures.append(f"exactly AIrsenal must serve; actual={serving}")


def _check_workflow_surface(manifest: dict, failures: list[str]) -> None:
    active_dir = Path(".github/workflows")
    active = {path.name for path in active_dir.glob("*.yml")}
    expected = SERVING_PRODUCTION_WORKFLOWS | OPERATIONS_RESEARCH_WORKFLOWS
    if active != expected:
        failures.append(
            "active workflow surface drifted: "
            f"expected={sorted(expected)} actual={sorted(active)}"
        )
    lingering = sorted(LEGACY_EXECUTABLE_WORKFLOWS & active)
    if lingering:
        failures.append(f"legacy publisher remains executable: {lingering}")

    archive_dir = Path("archive/workflows")
    archived = {path.name for path in archive_dir.glob("*.yml")}
    missing = sorted(REQUIRED_ARCHIVED_WORKFLOWS - archived)
    if missing:
        failures.append(f"required historical workflows missing from archive: {missing}")
    if not (archive_dir / "README.md").exists():
        failures.append("workflow archive manifest is missing")

    production = _text(manifest["canonical_production_workflow"])
    for needle in (
        FROZEN_SHA,
        'cron: "17 4 * * *"',
        "permissions:\n  contents: read",
        "apex-v2 private-store-preflight",
        "apex-v2 official-hash",
        "apex-v2 acquire",
        "APEX_ALLOW_NETWORK_DURING_SOLVE",
        "apex-v2 solve",
        "apex-v2 publish",
    ):
        if needle not in production:
            failures.append(f"V2 production workflow missing authority contract: {needle}")
    for forbidden in (
        "contents: write",
        "git push",
        "scripts/run_apex.py",
        "run_pinnacle.py",
    ):
        if forbidden in production:
            failures.append(f"V2 production workflow crossed legacy/write boundary: {forbidden}")

    ci = _text(active_dir / "apex.yml")
    for check_name in ("test:", "contract:", "readiness:"):
        if check_name not in ci:
            failures.append(f"required main CI context missing: {check_name[:-1]}")


def _check_research_boundaries(failures: list[str]) -> None:
    shadow = _text(".github/workflows/apex-v2-shadow-health.yml")
    for needle in (
        "contents: read",
        FROZEN_SHA,
        "dastan-pin-health",
        "pitchside-health",
        "openfpl-readiness",
    ):
        if needle not in shadow:
            failures.append(f"shadow-health safety contract missing: {needle}")
    for forbidden in (
        "FPL_SESSION_COOKIE",
        "FPL_X_API_AUTHORIZATION",
        "FPL_REFRESH_TOKEN",
        "APEX_PRIVATE_GITHUB_TOKEN",
        "contents: write",
        "apex-v2 solve",
        "apex-v2 publish",
    ):
        if forbidden in shadow:
            failures.append(f"shadow-health workflow crossed serving boundary: {forbidden}")

    tournament = _text(".github/workflows/apex-v2-prospective-tournament.yml")
    for needle in (
        FROZEN_SHA,
        'workflows: ["Apex V2 Daily Production"]',
        "apex_v2_tournament_contract.py",
        "apex_v2_tournament_scoring.py",
    ):
        if needle not in tournament:
            failures.append(f"prospective tournament workflow missing safety contract: {needle}")
    for forbidden in (
        "FPL_SESSION_COOKIE",
        "FPL_X_API_AUTHORIZATION",
        "FPL_REFRESH_TOKEN",
        "apex-v2 acquire",
        "apex-v2 solve",
        "apex-v2 publish",
        "run_airsenal_worker.py",
    ):
        if forbidden in tournament:
            failures.append(f"prospective tournament crossed serving boundary: {forbidden}")

    tournament_contract = _text("scripts/apex_v2_tournament_contract.py")
    for needle in (
        "LAST_VALID_COMMON_PREDEADLINE_SEAL",
        '"production_influence": "NONE"',
        '"serve_authorized": False',
        "COMMON_FORECAST_INTERSECTION",
    ):
        if needle not in tournament_contract:
            failures.append(f"prospective tournament governance contract missing: {needle}")

    decision_quality = _text(".github/workflows/apex-v2-decision-quality.yml")
    if "timeout-minutes: 50" not in decision_quality:
        failures.append("decision-quality exact task runtime contract is not 50 minutes")
    if "max-parallel: 8" not in decision_quality:
        failures.append("decision-quality parallel task contract drifted")
    decision_controller = _text("scripts/apex_v2_decision_lab_parallel.py")
    for needle in (
        'TASK_PREFIX = "apex-v2/private-decision-lab-task"',
        '"production_influence": "NONE"',
        '"serving_authorized": False',
        "decision-lab task finished after deadline and will not be sealed",
    ):
        if needle not in decision_controller:
            failures.append(f"decision-quality no-hindsight contract missing: {needle}")


def _check_authority_docs(failures: list[str]) -> None:
    required_tokens = (
        "Apex V2",
        FROZEN_SHA,
        "AIrsenal",
        "apex-v2-daily-production.yml",
        "APEX_V2_AUTHORITY.json",
    )
    for path in CANONICAL_AUTHORITY_DOCS:
        text = _text(path)
        for token in required_tokens:
            if token not in text:
                failures.append(f"canonical authority doc missing V2 token: {path}: {token}")
        for label, pattern in STALE_CURRENT_CLAIMS.items():
            if pattern.search(text):
                failures.append(f"canonical authority doc revived stale claim ({label}): {path}")

    operating = _text("docs/APEX_OPERATING_MANUAL.md")
    if "adverse-evidence-only" not in operating:
        failures.append("operating manual lost the EV-first adverse-evidence-only policy")
    if "NEVER merge or advance PR #90" not in operating:
        failures.append("operating manual lost the frozen PR #90 prohibition")
    if "immutable" not in operating.casefold():
        failures.append("operating manual no longer describes immutable production authority")


def main() -> None:
    failures: list[str] = []
    manifest = _check_manifest(failures)
    _check_frozen_config(manifest, failures)
    _check_workflow_surface(manifest, failures)
    _check_research_boundaries(failures)
    _check_authority_docs(failures)

    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
