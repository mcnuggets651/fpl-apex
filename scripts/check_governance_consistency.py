#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path


AUTHORITY = "docs/APEX_OPERATING_MANUAL.md"
REQUIRED_REDIRECTS = (
    "docs/CHATGPT_USAGE.md",
    "docs/CHATGPT_APEX_QUERY_POLICY.md",
    "docs/CURRENT_STATE.md",
    "docs/APEX_ROADMAP.md",
    "docs/KNOWN_ISSUES.md",
)


def main() -> None:
    failures: list[str] = []
    authority = Path(AUTHORITY)
    if not authority.exists():
        failures.append(f"missing authority document: {AUTHORITY}")
    for name in REQUIRED_REDIRECTS:
        text = Path(name).read_text(encoding="utf-8")
        if "APEX_OPERATING_MANUAL.md" not in text:
            failures.append(f"{name} does not redirect to {AUTHORITY}")
    workflow = Path(".github/workflows/pinnacle.yml").read_text(encoding="utf-8")
    if "apex_answer_context.json" not in workflow:
        failures.append("production workflow does not publish apex_answer_context.json")
    if failures:
        raise SystemExit("\n".join(failures))


if __name__ == "__main__":
    main()
