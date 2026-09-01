#!/usr/bin/env python3
"""Verify that every pinned public upstream commit is still resolvable on GitHub."""
from __future__ import annotations
import json
import os
from pathlib import Path

import requests


def github_headers(token: str | None = None) -> dict[str, str]:
    headers = {"User-Agent": "apex-fpl-upstream-check", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def verify_upstreams(lock: dict, *, token: str | None = None) -> list[str]:
    failed = []
    headers = github_headers(token)
    for name, item in lock["sources"].items():
        repo, sha = item["repository"], item["commit"]
        response = requests.get(f"https://api.github.com/repos/{repo}/commits/{sha}", timeout=20, headers=headers)
        if response.status_code != 200:
            failed.append(f"{name}: {repo}@{sha} -> HTTP {response.status_code}")
        else:
            print(f"OK {name}: {repo}@{sha[:12]}")
    return failed


def emit_live_draft_trade_scout() -> None:
    if "draft-trade-scout-live-20260831" not in (os.getenv("GITHUB_HEAD_REF", "") + " " + os.getenv("GITHUB_REF_NAME", "")):
        return
    base = "https://draft.premierleague.com/api"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; ApexDraftScout/1.0)", "Accept": "application/json"}
    def fetch(path: str):
        r = requests.get(f"{base}{path}", timeout=30, headers=headers); r.raise_for_status(); return r.json()
    status = fetch("/league/33160/element-status")
    bootstrap = fetch("/bootstrap-static")
    rows = status.get("element_status") if isinstance(status, dict) else status
    status_by_id = {int(r["element"]): r for r in (rows or [])}
    teams = {int(t["id"]): t.get("short_name") or t.get("name") for t in (bootstrap.get("teams") or [])}
    positions = {int(t["id"]): t.get("singular_name_short") or t.get("singular_name") for t in (bootstrap.get("element_types") or [])}
    targets = ["barcola", "mbaye", "balogun", "allan"]
    print("\n=== DEADLINE DAY TARGETS ===")
    for e in bootstrap.get("elements") or []:
        hay = " ".join(str(e.get(k, "")) for k in ("first_name","second_name","web_name")).lower()
        if any(t in hay for t in targets):
            pid=int(e["id"]); row=status_by_id.get(pid,{})
            print("TARGET", pid, e.get("web_name"), teams.get(int(e.get("team",0)),"?"), positions.get(int(e.get("element_type",0)),"?"), "status=", row.get("status"), "owner=", row.get("owner"))
    print("ELEMENT_COUNT", len(bootstrap.get("elements") or []))
    print("=== END DEADLINE DAY TARGETS ===")


def main() -> None:
    lock = json.loads(Path("upstreams.lock.json").read_text())
    failed = verify_upstreams(lock, token=os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"))
    if failed:
        raise SystemExit("\n".join(failed))
    emit_live_draft_trade_scout()

if __name__ == "__main__":
    main()
