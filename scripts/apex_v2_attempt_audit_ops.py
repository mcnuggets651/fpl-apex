#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Iterable

# Immutable historical production attempts proven from their GitHub Actions run
# records to have completed with conclusion=failure. They intentionally have no
# matching final release and must remain in the audit trail. Any missing final not
# listed here remains a hard operational failure.
ACKNOWLEDGED_FAILED_INTENTS = frozenset(
    {
        "apex-v2/intent/2026-2027/33242604422-1",
        "apex-v2/intent/2026-2027/33257608630-1",
        "apex-v2/intent/2026-2027/33260512411-1",
        "apex-v2/intent/2026-2027/33265747805-1",
        "apex-v2/intent/2026-2027/33272866621-1",
        "apex-v2/intent/2026-2027/33312221205-1",
    }
)

# The frozen release store creates these records as mutable drafts before it
# uploads/verifies assets and publishes them immutably. GitHub's authenticated
# List Releases endpoint includes drafts. The frozen attempt-tag auditor does not
# inspect draft/immutable metadata, so the operations controller must reject an
# unfinished release before trusting the tag-only audit.
AUDITED_RELEASE_KINDS = frozenset({"intent", "final", "outcome", "evaluation"})


class AttemptAuditOpsError(RuntimeError):
    """The immutable attempt audit could not be safely classified."""


@dataclass(frozen=True)
class ClassifiedAudit:
    payload: dict[str, Any]
    acknowledged_missing_finals: tuple[str, ...]
    unacknowledged_missing_finals: tuple[str, ...]


def _run_frozen_audit(prefix: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["apex-v2", "audit-attempts", "--prefix", prefix],
        capture_output=True,
        text=True,
        check=False,
    )


def _load_public_releases() -> list[dict[str, Any]]:
    repo = str(os.environ.get("GITHUB_REPOSITORY") or "").strip()
    token = str(os.environ.get("GITHUB_TOKEN") or "").strip()
    if not repo or not token:
        raise AttemptAuditOpsError(
            "GITHUB_REPOSITORY and GITHUB_TOKEN are required for release-integrity audit"
        )
    try:
        from apex.runtime.releases import GitHubReleaseStore

        rows = GitHubReleaseStore(repo, token).list_releases()
    except Exception as exc:
        raise AttemptAuditOpsError(
            "Could not read authoritative GitHub release metadata"
        ) from exc
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AttemptAuditOpsError("GitHub release metadata has invalid shape")
    return rows


def validate_release_integrity(
    releases: Iterable[dict[str, Any]],
    *,
    prefix: str = "apex-v2",
) -> tuple[str, ...]:
    """Reject mutable/incomplete releases that could poison tag-only logic.

    Every V2 intent/final/outcome/evaluation record is created through the frozen
    `GitHubReleaseStore.create_once(require_immutable=True)` contract. Therefore a
    record in one of these namespaces is valid operational evidence only when it
    is published (not draft), not a prerelease, and GitHub reports it immutable.
    """

    governed_prefixes = tuple(f"{prefix}/{kind}/" for kind in sorted(AUDITED_RELEASE_KINDS))
    invalid: list[str] = []
    seen: set[str] = set()
    for release in releases:
        if not isinstance(release, dict):
            raise AttemptAuditOpsError("GitHub release metadata contains a non-object row")
        tag = str(release.get("tag_name") or "")
        if not tag.startswith(governed_prefixes):
            continue
        if not tag or tag in seen:
            invalid.append(f"{tag or '<missing-tag>'}:duplicate-or-missing-tag")
            continue
        seen.add(tag)
        if release.get("draft") is not False:
            invalid.append(f"{tag}:draft")
        if release.get("prerelease") is not False:
            invalid.append(f"{tag}:prerelease")
        if release.get("immutable") is not True:
            invalid.append(f"{tag}:not-immutable")
        if not release.get("published_at"):
            invalid.append(f"{tag}:missing-published-at")
    if invalid:
        raise AttemptAuditOpsError(
            "Unpublished/mutable Apex V2 release state detected: " + ", ".join(sorted(invalid))
        )
    return tuple(sorted(seen))


def _parse_payload(stdout: str) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise AttemptAuditOpsError("Frozen attempt audit did not emit valid JSON") from exc
    if not isinstance(payload, dict):
        raise AttemptAuditOpsError("Frozen attempt audit payload is not an object")
    missing = payload.get("missing_finals")
    if not isinstance(missing, list) or any(not isinstance(row, str) for row in missing):
        raise AttemptAuditOpsError("Frozen attempt audit payload has invalid missing_finals")
    return payload


def classify_audit(
    payload: dict[str, Any],
    *,
    acknowledged: Iterable[str] = ACKNOWLEDGED_FAILED_INTENTS,
) -> ClassifiedAudit:
    allowed = frozenset(acknowledged)
    missing = tuple(sorted(set(payload.get("missing_finals", []))))
    acknowledged_missing = tuple(row for row in missing if row in allowed)
    unacknowledged_missing = tuple(row for row in missing if row not in allowed)
    return ClassifiedAudit(
        payload=payload,
        acknowledged_missing_finals=acknowledged_missing,
        unacknowledged_missing_finals=unacknowledged_missing,
    )


def evaluate_result(
    result: subprocess.CompletedProcess[str],
    *,
    acknowledged: Iterable[str] = ACKNOWLEDGED_FAILED_INTENTS,
) -> ClassifiedAudit:
    payload = _parse_payload(result.stdout or "")
    classified = classify_audit(payload, acknowledged=acknowledged)

    # Frozen CLI contract: 0 means no missing finals; 2 means missing finals were
    # detected. Any other exit is an audit/runtime failure and cannot be waived.
    if result.returncode not in {0, 2}:
        raise AttemptAuditOpsError(
            f"Frozen attempt audit exited unexpectedly with code {result.returncode}"
        )
    if result.returncode == 0 and payload.get("missing_finals"):
        raise AttemptAuditOpsError(
            "Frozen attempt audit returned success while reporting missing finals"
        )
    if result.returncode == 2 and not payload.get("missing_finals"):
        raise AttemptAuditOpsError(
            "Frozen attempt audit returned orphan status without missing finals"
        )
    return classified


def _render(classified: ClassifiedAudit) -> str:
    payload = dict(classified.payload)
    payload["acknowledged_historical_failures"] = list(
        classified.acknowledged_missing_finals
    )
    payload["unacknowledged_missing_finals"] = list(
        classified.unacknowledged_missing_finals
    )
    payload["operationally_clear"] = not classified.unacknowledged_missing_finals
    return json.dumps(payload, indent=2, sort_keys=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", default="apex-v2")
    args = parser.parse_args()

    try:
        validate_release_integrity(_load_public_releases(), prefix=args.prefix)
    except Exception as exc:
        print(f"Apex V2 release-integrity operations failure: {exc}", file=sys.stderr)
        return 1

    result = _run_frozen_audit(args.prefix)
    try:
        classified = evaluate_result(result)
    except Exception as exc:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        print(f"Apex V2 attempt-audit operations failure: {exc}", file=sys.stderr)
        return 1

    print(_render(classified))
    if classified.unacknowledged_missing_finals:
        print(
            "Unacknowledged immutable production orphan(s) detected; evaluation is blocked.",
            file=sys.stderr,
        )
        return 2

    if classified.acknowledged_missing_finals:
        print(
            "Only explicitly acknowledged historical failed attempts are orphaned; "
            "continuing evaluation without deleting or rewriting history.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
