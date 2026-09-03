#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import yaml


AUTHORITY = Path("docs/APEX_V2_AUTHORITY.json")
FROZEN_SHA = "99cc7b51b0cff45462b567084cb1844cfe0a456f"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SEASON = "2026-2027"
ENTRY_ID = 63984
SERVING_PROVIDER = "airsenal"
SERVING_WORKFLOW = ".github/workflows/apex-v2-daily-production.yml"

SERVING = {"apex-v2-daily-production.yml"}
NON_SERVING_ACTIVE = {
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
    "production-readiness.yml",
    "projection-policy-audit.yml",
    "team-strength-validation.yml",
}
RETIRED = {
    "pinnacle.yml",
    "airsenal.yml",
    "refresh-core-pin.yml",
    "gw1-final-2026.yml",
    "joint-path-promotion-audit.yml",
    "projection-shadow-audit.yml",
    "understat-player-production-ab.yml",
}
REQUIRED_ARCHIVE = {
    *RETIRED,
    "bootstrap-publish.yml",
    "publish-apex.yml",
    "fixture-blend-decision-audit.yml",
    "joint-initial-path-audit.yml",
    "solver-parity.yml",
    "understat-player-predictive-audit.yml",
}
AUTHORITY_DOCS = (
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
STALE_PATTERNS = {
    "Pinnacle current production": re.compile(
        r"pinnacle\s+(?:is|as)\s+(?:the\s+)?(?:current\s+)?production recommendation",
        re.IGNORECASE,
    ),
    "run_apex current production": re.compile(
        r"(?:the\s+)?only production (?:command|entrypoint)\s+is[^\n]*run_apex\.py",
        re.IGNORECASE,
    ),
    "old production SHA": re.compile(
        r"latest production publication:\s*`?a147754", re.IGNORECASE
    ),
    "old GW1 state": re.compile(
        r"post-PR\s*#25 publication at\s*`?a147754", re.IGNORECASE
    ),
    "old architecture freeze": re.compile(
        r"architecture freeze after PR\s*#64", re.IGNORECASE
    ),
    "legacy Pinnacle startup": re.compile(
        r"read\s+`?data/generated/pinnacle_latest\.json`?\s+first", re.IGNORECASE
    ),
}


def text(path: str | Path) -> str:
    return Path(path).read_text(encoding="utf-8")


def ensure_commit(ref: str) -> None:
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return
    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", ref],
        capture_output=True,
        text=True,
        check=False,
    )
    if fetched.returncode != 0:
        raise RuntimeError(f"cannot fetch core SHA {ref}: {fetched.stderr.strip()}")
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{ref}^{{commit}}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"not a commit: {ref}")


def git_text(ref: str, path: str) -> str:
    ensure_commit(ref)
    target = f"{ref}:{path}"
    result = subprocess.run(
        ["git", "show", target], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"cannot read core file {target}: {result.stderr.strip()}")
    return result.stdout


def check_manifest(failures: list[str]) -> dict:
    if not AUTHORITY.exists():
        failures.append(f"missing authority manifest: {AUTHORITY}")
        return {}
    manifest = json.loads(AUTHORITY.read_text(encoding="utf-8"))
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
    for key, wanted in expected.items():
        if manifest.get(key) != wanted:
            failures.append(
                f"authority manifest drifted: {key}: {manifest.get(key)!r} != {wanted!r}"
            )
    production_sha = str(manifest.get("production_core_sha") or "")
    if not SHA40.fullmatch(production_sha):
        failures.append("authority manifest production_core_sha is not a lowercase 40-char SHA")

    research = manifest.get("research") or {}
    if research.get("production_influence") != "NONE":
        failures.append("research production influence is not NONE")
    if research.get("serving_authorized") is not False:
        failures.append("research is serving-authorized")
    if research.get("automatic_promotion") is not False:
        failures.append("automatic challenger promotion is enabled")
    legacy = manifest.get("legacy") or {}
    if legacy.get("status") != "HISTORICAL_NON_SERVING":
        failures.append("legacy authority is not HISTORICAL_NON_SERVING")
    declared_archive = set(legacy.get("archived_workflows") or [])
    expected_archive = {f"archive/workflows/{name}" for name in RETIRED}
    if declared_archive != expected_archive:
        failures.append(
            "authority manifest archived workflows drifted: "
            f"expected={sorted(expected_archive)} actual={sorted(declared_archive)}"
        )
    return manifest


def check_core_ancestry(manifest: dict, failures: list[str]) -> None:
    production_sha = str(manifest.get("production_core_sha") or "")
    if not SHA40.fullmatch(production_sha):
        return
    try:
        ensure_commit(FROZEN_SHA)
        ensure_commit(production_sha)
    except RuntimeError as exc:
        failures.append(str(exc))
        return
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", FROZEN_SHA, production_sha],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        failures.append(
            "production_core_sha is not a descendant of immutable PR #90 base: "
            f"{production_sha} !>= {FROZEN_SHA}"
        )


def check_production_config(manifest: dict, failures: list[str]) -> None:
    production_sha = str(manifest.get("production_core_sha") or "")
    if not SHA40.fullmatch(production_sha):
        return
    try:
        config = yaml.safe_load(git_text(production_sha, "config/apex_v2.yaml"))
    except (RuntimeError, yaml.YAMLError) as exc:
        failures.append(f"cannot validate production config: {exc}")
        return
    if config.get("season") != manifest.get("season"):
        failures.append("manifest season disagrees with production config")
    if config.get("entry_id") != manifest.get("entry_id"):
        failures.append("manifest entry_id disagrees with production config")
    if config.get("max_horizon") != 8:
        failures.append("production max_horizon is not 8")

    providers = {row["id"]: row for row in config.get("providers") or []}
    declared = manifest.get("provider_constitution") or {}
    if set(providers) != set(declared):
        failures.append(
            f"provider set drifted: production={sorted(providers)} manifest={sorted(declared)}"
        )
        return
    for provider_id, expected in declared.items():
        actual = providers[provider_id]
        if actual.get("role") != expected.get("role"):
            failures.append(f"provider role drifted: {provider_id}")
        if actual.get("serve_authorized") is not expected.get("serve_authorized"):
            failures.append(f"provider serve_authorized drifted: {provider_id}")
        if actual.get("requested_horizons") != expected.get("horizons"):
            failures.append(f"provider horizons drifted: {provider_id}")
    serving = [
        provider_id
        for provider_id, row in providers.items()
        if row.get("serve_authorized") is True
    ]
    if serving != [SERVING_PROVIDER]:
        failures.append(
            f"production config does not have exactly AIrsenal serving: {serving}"
        )


def check_workflows(manifest: dict, failures: list[str]) -> None:
    active_dir = Path(".github/workflows")
    active = {path.name for path in active_dir.glob("*.yml")}
    expected = SERVING | NON_SERVING_ACTIVE
    if active != expected:
        failures.append(
            f"active workflow surface drifted: expected={sorted(expected)} actual={sorted(active)}"
        )
    lingering = sorted(active & RETIRED)
    if lingering:
        failures.append(f"retired workflows remain executable: {lingering}")

    archived = {path.name for path in Path("archive/workflows").glob("*.yml")}
    missing = sorted(REQUIRED_ARCHIVE - archived)
    if missing:
        failures.append(f"required workflow forensics missing: {missing}")
    archive_readme = Path("archive/workflows/README.md")
    if not archive_readme.exists() or "intentionally inert" not in text(archive_readme):
        failures.append("workflow archive is not explicitly inert")

    production = text(manifest.get("canonical_production_workflow", SERVING_WORKFLOW))
    for needle in (
        "production_core_sha",
        "frozen_engine_sha",
        'cron: "17 4 * * *"',
        "group: apex-v2-fpl-auth",
        "cancel-in-progress: false",
        "apex-v2 private-store-preflight",
        "apex-v2 official-hash",
        'FPL_TEAM_ID: "1"',
        "run_airsenal_worker.py",
        "--horizon 8",
        'APEX_ALLOW_NETWORK_DURING_SOLVE: "0"',
        "apex-v2 solve",
        "apex-v2 publish",
    ):
        if needle not in production:
            failures.append(f"V2 production contract missing: {needle}")
    for forbidden in ("git push", "scripts/run_apex.py", "run_pinnacle.py"):
        if forbidden in production:
            failures.append(
                f"V2 production revived legacy/direct-main behavior: {forbidden}"
            )

    ci = text(active_dir / "apex.yml")
    for job in ("test:", "contract:", "readiness:"):
        if job not in ci:
            failures.append(f"required Apex CI context missing: {job[:-1]}")
    if 'authority["production_core_sha"]' not in ci:
        failures.append("Apex CI does not resolve authority production_core_sha")


def check_non_serving_boundaries(failures: list[str]) -> None:
    keepalive = text(".github/workflows/apex-v2-auth-keepalive.yml")
    for needle in (
        'cron: "22 */6 * * *"',
        "contents: read",
        "group: apex-v2-fpl-auth",
        "--mode keepalive",
    ):
        if needle not in keepalive:
            failures.append(f"auth keepalive missing: {needle}")
    for forbidden in (
        "apex-v2 acquire",
        "apex-v2 solve",
        "apex-v2 publish",
        "contents: write",
    ):
        if forbidden in keepalive:
            failures.append(f"auth keepalive crossed boundary: {forbidden}")

    deadline = text(".github/workflows/apex-v2-deadline-watch.yml")
    for needle in (
        'cron: "11,41 * * * *"',
        "actions: write",
        "--min-minutes 90",
        "--max-minutes 150",
    ):
        if needle not in deadline:
            failures.append(f"deadline watch missing: {needle}")
    for forbidden in (
        "FPL_REFRESH_TOKEN",
        "FPL_SESSION_COOKIE",
        "apex-v2 solve",
        "apex-v2 publish",
        "contents: write",
    ):
        if forbidden in deadline:
            failures.append(f"deadline watch crossed boundary: {forbidden}")

    shadow = text(".github/workflows/apex-v2-shadow-health.yml")
    for forbidden in (
        "FPL_SESSION_COOKIE",
        "FPL_X_API_AUTHORIZATION",
        "FPL_REFRESH_TOKEN",
        "contents: write",
        "apex-v2 solve",
        "apex-v2 publish",
    ):
        if forbidden in shadow:
            failures.append(f"shadow health crossed boundary: {forbidden}")

    # Tournament/research stays bound to the immutable evaluator lineage. It is
    # explicitly non-serving and must not become an alternate promotion path.
    tournament = text(".github/workflows/apex-v2-prospective-tournament.yml")
    for needle in (
        FROZEN_SHA,
        'workflows: ["Apex V2 Daily Production"]',
        "apex_v2_tournament_contract.py",
        "apex_v2_tournament_scoring.py",
    ):
        if needle not in tournament:
            failures.append(f"tournament contract missing: {needle}")
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
            failures.append(f"tournament crossed serving boundary: {forbidden}")

    contract = text("scripts/apex_v2_tournament_contract.py")
    for needle in (
        "LAST_VALID_COMMON_PREDEADLINE_SEAL",
        '"production_influence": "NONE"',
        '"serve_authorized": False',
    ):
        if needle not in contract:
            failures.append(f"tournament governance missing: {needle}")

    decision = text(".github/workflows/apex-v2-decision-quality.yml")
    for needle in (
        "max-parallel: 8",
        "timeout-minutes: 50",
        "--mode prepare",
        "--mode solve-task",
        "--mode assemble",
        "--mode postoutcome",
    ):
        if needle not in decision:
            failures.append(f"decision-quality contract missing: {needle}")
    for forbidden in ("contents: write", "apex-v2 acquire", "apex-v2 publish"):
        if forbidden in decision:
            failures.append(f"decision-quality crossed boundary: {forbidden}")
    controller = text("scripts/apex_v2_decision_lab_parallel.py")
    for needle in (
        'TASK_PREFIX = "apex-v2/private-decision-lab-task"',
        '"production_influence": "NONE"',
        '"serving_authorized": False',
        "decision-lab task finished after deadline and will not be sealed",
    ):
        if needle not in controller:
            failures.append(f"decision-quality no-hindsight invariant missing: {needle}")


def check_docs(failures: list[str]) -> None:
    required = (
        "Apex V2",
        FROZEN_SHA,
        "AIrsenal",
        "apex-v2-daily-production.yml",
        "APEX_V2_AUTHORITY.json",
    )
    for path in AUTHORITY_DOCS:
        body = text(path)
        for token in required:
            if token not in body:
                failures.append(f"authority doc missing {token}: {path}")
        for label, pattern in STALE_PATTERNS.items():
            if pattern.search(body):
                failures.append(f"authority doc revived stale claim ({label}): {path}")

    manual = text("docs/APEX_OPERATING_MANUAL.md")
    for needle in (
        "adverse-evidence-only",
        "NEVER merge or advance PR #90",
        "immutable",
    ):
        if needle not in manual:
            failures.append(f"operating manual lost authority rule: {needle}")


def main() -> None:
    failures: list[str] = []
    manifest = check_manifest(failures)
    check_core_ancestry(manifest, failures)
    check_production_config(manifest, failures)
    check_workflows(manifest, failures)
    check_non_serving_boundaries(failures)
    check_docs(failures)
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
