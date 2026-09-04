#!/usr/bin/env python3
"""Fail when a repository change omits the canonical FPL Apex master ledger.

The guard is intentionally strict: every tracked change must update
``docs/FPL_APEX_MASTER_STATE.md`` in the same change, except a change whose only
tracked path is the master ledger itself.

CI base selection is derived from GitHub's event payload when available. A base
can be supplied explicitly for local/adversarial testing.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

MASTER = "docs/FPL_APEX_MASTER_STATE.md"
REQUIRED_AGENT_FILES = ("AGENTS.md", "CLAUDE.md")


def git(*args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc.stdout.strip()


def validate_static_contract(root: Path) -> None:
    master = root / MASTER
    if not master.is_file():
        raise RuntimeError(f"missing canonical master state: {MASTER}")
    text = master.read_text(encoding="utf-8")
    required_master_markers = (
        "APEX_V2_AUTHORITY.json",
        "PRODUCTION PIPELINE PASSED; PRIVATE QUERY ACCEPTANCE BLOCKED BY GITHUB BILLING",
        "NEVER_MERGE_OR_ADVANCE",
        "c0ae9f6e1b21c1839f4dc575a3ff14d48d48f437",
        "99cc7b51b0cff45462b567084cb1844cfe0a456f",
        "33850307770-1",
        "same-change",
    )
    missing = [marker for marker in required_master_markers if marker not in text]
    if missing:
        raise RuntimeError(f"master state missing required continuity markers: {missing}")

    for path in REQUIRED_AGENT_FILES:
        agent = root / path
        if not agent.is_file():
            raise RuntimeError(f"missing required agent contract: {path}")
        body = agent.read_text(encoding="utf-8")
        if MASTER not in body:
            raise RuntimeError(f"{path} does not require reading {MASTER}")


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

    base_ref = os.environ.get("GITHUB_BASE_REF")
    if base_ref:
        for candidate in (f"origin/{base_ref}", base_ref):
            if git("rev-parse", "--verify", candidate, check=False):
                return git("merge-base", "HEAD", candidate)

    if git("rev-parse", "--verify", "HEAD^", check=False):
        return "HEAD^"
    return None


def changed_paths(base: str, head: str) -> list[str]:
    # Two-dot diff is correct for both a PR base SHA and github.event.before:
    # it asks what this checked-out head changed relative to the supplied base.
    out = git("diff", "--name-only", f"{base}..{head}")
    return [line.strip() for line in out.splitlines() if line.strip()]


def enforce(paths: list[str]) -> None:
    tracked = sorted(set(paths))
    if not tracked:
        return
    if tracked == [MASTER]:
        return
    if MASTER not in tracked:
        preview = "\n  - ".join(tracked[:80])
        suffix = "\n  - …" if len(tracked) > 80 else ""
        raise RuntimeError(
            "FPL Apex master-state continuity violation. Every tracked repository "
            f"change must update {MASTER} in the same change. Changed paths:\n  - "
            f"{preview}{suffix}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", help="base commit/ref to compare against")
    parser.add_argument("--head", default="HEAD", help="head commit/ref (default: HEAD)")
    parser.add_argument(
        "--paths",
        nargs="*",
        help="explicit changed paths; bypass git diff (for tests/diagnostics)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(git("rev-parse", "--show-toplevel"))
    validate_static_contract(root)

    if args.paths is not None:
        paths = args.paths
        base_desc = "explicit paths"
    else:
        base = args.base or event_base()
        if not base:
            print("master-state static contract OK; no comparable base available")
            return 0
        # Make an explicit SHA/ref failure clear instead of silently skipping.
        git("rev-parse", "--verify", base)
        git("rev-parse", "--verify", args.head)
        paths = changed_paths(base, args.head)
        base_desc = base

    enforce(paths)
    print(
        f"master-state continuity OK: {MASTER} covers {len(set(paths))} changed path(s) "
        f"against {base_desc}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
