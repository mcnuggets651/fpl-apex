#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
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
        "apex-v2/intent/2026-2027/33784086615-1",
        "apex-v2/intent/2026-2027/33809325241-1",
    }
)


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
