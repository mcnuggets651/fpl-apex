#!/usr/bin/env python3
"""Verify that every pinned public upstream commit is still resolvable on GitHub."""
from __future__ import annotations
import json
from pathlib import Path
import requests

lock = json.loads(Path("upstreams.lock.json").read_text())
failed = []
for name, item in lock["sources"].items():
    repo, sha = item["repository"], item["commit"]
    url = f"https://api.github.com/repos/{repo}/commits/{sha}"
    r = requests.get(url, timeout=20, headers={"User-Agent": "apex-fpl-upstream-check"})
    if r.status_code != 200:
        failed.append(f"{name}: {repo}@{sha} -> HTTP {r.status_code}")
    else:
        print(f"OK {name}: {repo}@{sha[:12]}")
if failed:
    raise SystemExit("\n".join(failed))
