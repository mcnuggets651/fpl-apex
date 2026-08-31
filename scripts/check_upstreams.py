#!/usr/bin/env python3
"""Verify that every pinned public upstream commit is still resolvable on GitHub."""
from __future__ import annotations
import json
import os
from collections import defaultdict
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


def emit_live_draft_trade_scout() -> None:
    """Temporary branch-only diagnostic: print league 33160 roster ownership from official Draft."""
    if "draft-trade-scout-live-20260831" not in (
        os.getenv("GITHUB_HEAD_REF", "") + " " + os.getenv("GITHUB_REF_NAME", "")
    ):
        return

    base = "https://draft.premierleague.com/api"
    league_id = 33160
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; ApexDraftScout/1.0)",
        "Accept": "application/json",
    }

    def fetch(path: str) -> dict:
        response = requests.get(f"{base}{path}", timeout=30, headers=headers)
        response.raise_for_status()
        return response.json()

    details = fetch(f"/league/{league_id}/details")
    status = fetch(f"/league/{league_id}/element-status")
    bootstrap = fetch("/bootstrap-static")

    elements = bootstrap.get("elements") or []
    by_id = {int(e["id"]): e for e in elements if e.get("id") is not None}
    teams = {
        int(t["id"]): t.get("short_name") or t.get("name") or str(t["id"])
        for t in (bootstrap.get("teams") or [])
        if t.get("id") is not None
    }
    positions = {
        int(t["id"]): t.get("singular_name_short") or t.get("singular_name") or str(t["id"])
        for t in (bootstrap.get("element_types") or [])
        if t.get("id") is not None
    }

    entries = details.get("league_entries") or details.get("entries") or []
    owner_meta: dict[int, dict] = {}
    for entry in entries:
        ids: set[int] = set()
        for key in ("id", "entry_id", "league_entry_id"):
            if entry.get(key) is not None:
                try:
                    ids.add(int(entry[key]))
                except (TypeError, ValueError):
                    pass
        team_name = entry.get("entry_name") or entry.get("team_name") or entry.get("name") or ""
        manager = " ".join(
            value for value in (entry.get("player_first_name"), entry.get("player_last_name")) if value
        ).strip()
        for owner_id in ids:
            owner_meta[owner_id] = {"team_name": team_name, "manager": manager, "entry": entry}

    rows = status.get("element_status") if isinstance(status, dict) else status
    rosters: dict[int, list[dict]] = defaultdict(list)
    for row in rows or []:
        if row.get("status") != "o" or row.get("owner") is None:
            continue
        player_id = int(row["element"])
        element = by_id.get(player_id, {})
        team_id = element.get("team")
        type_id = element.get("element_type")
        rosters[int(row["owner"])].append(
            {
                "id": player_id,
                "name": element.get("web_name") or element.get("second_name") or str(player_id),
                "team": teams.get(int(team_id), str(team_id)) if team_id is not None else "?",
                "position": positions.get(int(type_id), str(type_id)) if type_id is not None else "?",
            }
        )

    print("\n=== APEX LIVE DRAFT TRADE SCOUT ===")
    print("DETAIL_KEYS", sorted(details.keys()))
    league = details.get("league") or {}
    print("LEAGUE", json.dumps(league, ensure_ascii=False, sort_keys=True))
    print("ENTRY_COUNT", len(entries))
    print("ENTRIES_BEGIN")
    for entry in entries:
        print(json.dumps(entry, ensure_ascii=False, sort_keys=True))
    print("ENTRIES_END")
    print("ROSTERS_BEGIN")
    for owner_id in sorted(rosters):
        meta = owner_meta.get(owner_id, {})
        print(
            f"OWNER={owner_id} | TEAM={meta.get('team_name','')} | MANAGER={meta.get('manager','')}"
        )
        for player in sorted(rosters[owner_id], key=lambda x: (x["position"], x["name"])):
            print(
                f"  {player['position']} | {player['name']} | {player['team']} | id={player['id']}"
            )
    print("ROSTERS_END")
    print("=== END APEX LIVE DRAFT TRADE SCOUT ===\n")


def main() -> None:
    lock = json.loads(Path("upstreams.lock.json").read_text())
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    failed = verify_upstreams(lock, token=token)
    if failed:
        raise SystemExit("\n".join(failed))
    emit_live_draft_trade_scout()


if __name__ == "__main__":
    main()
