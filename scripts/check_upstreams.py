#!/usr/bin/env python3
"""Verify that every pinned public upstream commit is still resolvable on GitHub."""
from __future__ import annotations
import json
import os
from pathlib import Path

import requests


def github_headers(token: str | None = None) -> dict[str, str]:
    headers = {
        "User-Agent": "apex-fpl-upstream-check",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def verify_upstreams(lock: dict, *, token: str | None = None) -> list[str]:
    """Return resolution failures for each lock entry without weakening the gate."""
    failed: list[str] = []
    headers = github_headers(token)
    for name, item in lock["sources"].items():
        repo, sha = item["repository"], item["commit"]
        url = f"https://api.github.com/repos/{repo}/commits/{sha}"
        response = requests.get(url, timeout=20, headers=headers)
        if response.status_code != 200:
            remaining = response.headers.get("X-RateLimit-Remaining")
            suffix = f" (rate-limit remaining={remaining})" if remaining is not None else ""
            failed.append(f"{name}: {repo}@{sha} -> HTTP {response.status_code}{suffix}")
        else:
            print(f"OK {name}: {repo}@{sha[:12]}")
    return failed


def main() -> None:
    lock = json.loads(Path("upstreams.lock.json").read_text())
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    failed = verify_upstreams(lock, token=token)
    if failed:
        raise SystemExit("\n".join(failed))


if __name__ == "__main__":
    main()
