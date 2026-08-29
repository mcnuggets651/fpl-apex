from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

import requests
import yaml

BASE = "https://fantasy.premierleague.com/api"


def _bearer_header(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    return value if value.casefold().startswith("bearer ") else f"Bearer {value}"


def _credential_candidates(
    *,
    token: str,
    cookie: str,
) -> list[tuple[str, dict[str, str]]]:
    common = {
        "Accept": "application/json",
        "Referer": "https://fantasy.premierleague.com/",
        "User-Agent": "fpl-apex-v2/1",
    }
    candidates: list[tuple[str, dict[str, str]]] = []
    bearer = _bearer_header(token)
    if bearer:
        candidates.append(("token", {**common, "X-API-Authorization": bearer}))
    if cookie.strip():
        candidates.append(("cookie", {**common, "Cookie": cookie.strip()}))
    return candidates


def verify_owner_credential(
    entry_id: int,
    *,
    token: str,
    cookie: str,
    http: Any = requests,
    timeout: float = 20.0,
) -> str:
    """Return the single proven auth transport without exposing credential material.

    Each configured credential is tested independently. This prevents a stale bearer
    token from poisoning a still-valid cookie (or vice versa), and proves manager
    identity before expensive provider generation starts.
    """
    candidates = _credential_candidates(token=token, cookie=cookie)
    if not candidates:
        raise RuntimeError("Official FPL owner credential is not configured")

    rejected = 0
    wrong_manager = 0
    for mode, headers in candidates:
        response = http.get(f"{BASE}/me/", headers=headers, timeout=timeout)
        if response.status_code in {401, 403}:
            rejected += 1
            continue
        if response.status_code != 200:
            raise RuntimeError("Official FPL owner-auth preflight returned an unexpected status")
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Official FPL owner-auth preflight returned an invalid payload")
        authenticated_entry = (payload.get("player") or {}).get("entry")
        try:
            matches = int(authenticated_entry) == int(entry_id)
        except (TypeError, ValueError):
            matches = False
        if not matches:
            wrong_manager += 1
            continue
        return mode

    if wrong_manager:
        raise RuntimeError("Official FPL credential belongs to a different manager entry")
    if rejected == len(candidates):
        raise RuntimeError("Official FPL owner credential was rejected or expired")
    raise RuntimeError("Official FPL owner credential could not be certified")


def _entry_id(config: Path) -> int:
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("entry_id") is None:
        raise RuntimeError("Apex V2 config does not define entry_id")
    return int(payload["entry_id"])


def _write_github_output(path: Path, mode: str) -> None:
    # Only booleans identifying the proven transport cross the step boundary.
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"use_token={'1' if mode == 'token' else '0'}\n")
        handle.write(f"use_cookie={'1' if mode == 'cookie' else '0'}\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("config/apex_v2.yaml"))
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()

    mode = verify_owner_credential(
        _entry_id(args.config),
        token=os.getenv("FPL_X_API_AUTHORIZATION", ""),
        cookie=os.getenv("FPL_SESSION_COOKIE", ""),
    )
    if args.github_output:
        _write_github_output(args.github_output, mode)
    print(json.dumps({"authenticated": True, "manager_identity_match": True}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
