#!/usr/bin/env python3
"""Authenticated FPL Draft transaction relay for the private Apex query plane.

This is a read-only interaction capability. It uses the already-governed public
Apex owner-auth lifecycle, reads only Official FPL Draft endpoints, strips the
response to an allowlisted transaction surface and dispatches a credential-free
snapshot to the private repository.

It must never publish reusable FPL credentials, raw authenticated response bodies
or an owner transaction snapshot into this public repository.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Iterable

DRAFT_API_ROOT = "https://draft.premierleague.com/api"
GITHUB_API_ROOT = "https://api.github.com"
CONTRACT = "apex-private-draft-auth-relay-v1"
DISPATCH_EVENT = "apex-draft-auth-snapshot"
DEFAULT_LEAGUE_ID = 33160
DEFAULT_ENTRY_NAME = "mcnuggets"
DEFAULT_TIMEOUT = 25
MAX_ROWS = 100
MAX_DISPATCH_BYTES = 60_000
INTERESTING_SCHEMA_FRAGMENTS = (
    "transaction",
    "waiver",
    "request",
    "pending",
    "trade",
)
SAFE_TRANSACTION_FIELDS = {
    "id",
    "event",
    "entry",
    "entry_id",
    "league_entry",
    "owner",
    "element",
    "element_in",
    "element_out",
    "player_in",
    "player_out",
    "kind",
    "type",
    "transaction_type",
    "status",
    "result",
    "priority",
    "rank",
    "created",
    "created_at",
    "submitted",
    "submitted_at",
    "timestamp",
    "waiver",
    "trade",
    "accepted",
    "approved",
    "vetoed",
    "deadline",
    "stage",
    "added",
    "index",
}
FORBIDDEN_KEY_FRAGMENTS = ("token", "cookie", "authorization", "secret", "credential")


class DraftRelayError(RuntimeError):
    """Fail-closed relay failure with deliberately credential-free text."""


class HttpClient:
    def __init__(self, *, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.timeout = timeout

    def get_json(self, path: str, headers: dict[str, str]) -> tuple[int, Any | None]:
        clean = path.strip().lstrip("/")
        if not clean or "://" in clean or ".." in clean.split("/"):
            raise DraftRelayError("refusing unsafe Official Draft path")
        request = urllib.request.Request(
            f"{DRAFT_API_ROOT}/{clean}", headers=headers, method="GET"
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                status = int(getattr(response, "status", 200))
                raw = response.read()
        except urllib.error.HTTPError as exc:
            return int(exc.code), None
        except urllib.error.URLError as exc:
            raise DraftRelayError("Official Draft network request failed") from exc
        if status != 200:
            return status, None
        try:
            return status, json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise DraftRelayError("Official Draft returned invalid JSON") from exc

    def dispatch(self, repository: str, github_token: str, payload: dict[str, Any]) -> int:
        if "/" not in repository or repository.count("/") != 1:
            raise DraftRelayError("private repository identity is invalid")
        raw = json.dumps(
            {"event_type": DISPATCH_EVENT, "client_payload": payload},
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(raw) > MAX_DISPATCH_BYTES:
            raise DraftRelayError("Draft relay dispatch exceeds safe payload limit")
        request = urllib.request.Request(
            f"{GITHUB_API_ROOT}/repos/{repository}/dispatches",
            data=raw,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {github_token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "fpl-apex-draft-auth-relay/1",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return int(getattr(response, "status", 204))
        except urllib.error.HTTPError as exc:
            # Never include response bodies because they can contain repository detail.
            return int(exc.code)
        except urllib.error.URLError as exc:
            raise DraftRelayError("private repository dispatch failed") from exc


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bearer(raw: str) -> str:
    value = raw.strip()
    if not value:
        return ""
    return value if value.casefold().startswith("bearer ") else f"Bearer {value}"


def _common_headers() -> dict[str, str]:
    return {
        "Accept": "application/json",
        "Referer": "https://draft.premierleague.com/",
        "User-Agent": "fpl-apex-draft-auth-relay/1",
    }


def _auth_headers(token: str, cookie: str) -> tuple[str, dict[str, str]]:
    common = _common_headers()
    bearer = _bearer(token)
    if bearer:
        return "token", {**common, "X-API-Authorization": bearer}
    if cookie.strip():
        return "cookie", {**common, "Cookie": cookie.strip()}
    raise DraftRelayError("authenticated Draft relay has no owner credential transport")


def _require_public(client: HttpClient, path: str, label: str) -> Any:
    status, payload = client.get_json(path, _common_headers())
    if status != 200:
        raise DraftRelayError(f"Official Draft {label} unavailable: HTTP {status}")
    return payload


def _league_entries(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("league_entries"), list):
        raise DraftRelayError("Draft league details omitted league_entries")
    return [dict(row) for row in payload["league_entries"] if isinstance(row, dict)]


def _resolve_team_entry_id(details: Any, entry_name: str) -> int:
    wanted = entry_name.strip().casefold()
    matches: list[int] = []
    for row in _league_entries(details):
        if str(row.get("entry_name") or "").strip().casefold() != wanted:
            continue
        raw = row.get("entry_id")
        if raw is None:
            raw = row.get("id")
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value > 0:
            matches.append(value)
    if len(matches) != 1:
        raise DraftRelayError("configured Draft entry did not resolve uniquely")
    return matches[0]


def _list_rows(payload: Any, keys: Iterable[str]) -> list[dict[str, Any]]:
    rows: Any = payload
    if isinstance(payload, dict):
        rows = None
        for key in keys:
            candidate = payload.get(key)
            if isinstance(candidate, list):
                rows = candidate
                break
        if rows is None:
            return []
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _bootstrap_players(payload: Any) -> dict[int, str]:
    if not isinstance(payload, dict):
        raise DraftRelayError("Draft bootstrap payload is invalid")
    result: dict[int, str] = {}
    for row in payload.get("elements") or []:
        if not isinstance(row, dict) or row.get("id") is None:
            continue
        try:
            element_id = int(row["id"])
        except (TypeError, ValueError):
            continue
        result[element_id] = str(row.get("web_name") or row.get("second_name") or "")
    if not result:
        raise DraftRelayError("Draft bootstrap contains no player identities")
    return result


def _safe_scalar(value: Any) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _safe_rows(payload: Any, players: dict[int, str], *, limit: int) -> list[dict[str, Any]]:
    rows = _list_rows(payload, ("transactions", "waivers", "results", "data"))
    if not rows and isinstance(payload, list):
        rows = [dict(row) for row in payload if isinstance(row, dict)]
    safe_rows: list[dict[str, Any]] = []
    for row in rows[:limit]:
        safe: dict[str, Any] = {}
        for key in SAFE_TRANSACTION_FIELDS:
            if key in row and _safe_scalar(row[key]):
                safe[key] = row[key]
        for source_key, target_key in (
            ("element", "element_name"),
            ("element_in", "element_in_name"),
            ("element_out", "element_out_name"),
            ("player_in", "player_in_name"),
            ("player_out", "player_out_name"),
        ):
            try:
                element_id = int(row.get(source_key))
            except (TypeError, ValueError):
                continue
            name = players.get(element_id)
            if name:
                safe[target_key] = name
        if safe:
            safe_rows.append(safe)
    return safe_rows


def _transaction_resolution_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Classify only by whether Official Draft has supplied a result code.

    A missing result is deliberately called ``unresolved`` rather than ``pending``
    until runtime evidence proves that the upstream field has that exact semantic.
    """

    resolved = 0
    unresolved = 0
    for row in rows:
        result = row.get("result")
        if result is None or not str(result).strip():
            unresolved += 1
        else:
            resolved += 1
    return {"resolved": resolved, "unresolved": unresolved}


def _interesting_schema(payload: Any) -> dict[str, Any]:
    """Return schema-only diagnostics with no scalar owner values.

    The purpose is to discover authenticated Draft surfaces without ever logging
    raw manager state. Only key names, container types, list counts and sample
    field names are retained.
    """

    result: dict[str, Any] = {
        "type": "object" if isinstance(payload, dict) else type(payload).__name__,
        "top_level_keys": sorted(str(key) for key in payload) if isinstance(payload, dict) else [],
        "interesting_paths": [],
    }

    def walk(value: Any, path: str, depth: int) -> None:
        if depth > 5:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = str(key)
                child_path = f"{path}.{key_text}" if path else key_text
                lowered = key_text.casefold()
                if any(fragment in lowered for fragment in INTERESTING_SCHEMA_FRAGMENTS):
                    item: dict[str, Any] = {"path": child_path}
                    if isinstance(child, dict):
                        item.update(
                            {
                                "type": "object",
                                "keys": sorted(str(child_key) for child_key in child),
                            }
                        )
                    elif isinstance(child, list):
                        fields: set[str] = set()
                        for sample in child[:3]:
                            if isinstance(sample, dict):
                                fields.update(str(sample_key) for sample_key in sample)
                        item.update(
                            {
                                "type": "list",
                                "count": len(child),
                                "sample_fields": sorted(fields),
                            }
                        )
                    else:
                        item["type"] = type(child).__name__
                    result["interesting_paths"].append(item)
                walk(child, child_path, depth + 1)
        elif isinstance(value, list):
            for index, child in enumerate(value[:3]):
                walk(child, f"{path}[]" if path else "[]", depth + 1)

    walk(payload, "", 0)
    return result


def _reject_sensitive_keys(value: Any, *, path: str = "payload") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lower = str(key).casefold()
            if any(fragment in lower for fragment in FORBIDDEN_KEY_FRAGMENTS):
                raise DraftRelayError(f"sensitive key forbidden at {path}.{key}")
            _reject_sensitive_keys(child, path=f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_sensitive_keys(child, path=f"{path}[{index}]")


def build_relay(
    *,
    client: HttpClient,
    league_id: int,
    entry_name: str,
    token: str,
    cookie: str,
    producer_repository: str,
    producer_run_id: str,
    producer_sha: str,
    max_rows: int = MAX_ROWS,
) -> dict[str, Any]:
    if league_id <= 0:
        raise DraftRelayError("league_id must be positive")
    if not entry_name.strip():
        raise DraftRelayError("entry_name must be non-empty")
    if max_rows < 1 or max_rows > MAX_ROWS:
        raise DraftRelayError(f"max_rows must be between 1 and {MAX_ROWS}")
    if producer_repository != "mcnuggets651/fpl-apex":
        raise DraftRelayError("producer repository identity mismatch")
    if not str(producer_run_id).isdigit():
        raise DraftRelayError("producer run ID is invalid")
    sha = producer_sha.strip().casefold()
    if len(sha) != 40 or any(char not in "0123456789abcdef" for char in sha):
        raise DraftRelayError("producer SHA is invalid")

    details = _require_public(client, f"league/{league_id}/details", "league details")
    bootstrap = _require_public(client, "bootstrap-static", "bootstrap")
    team_entry_id = _resolve_team_entry_id(details, entry_name)
    players = _bootstrap_players(bootstrap)

    auth_mode, headers = _auth_headers(token, cookie)
    status, transactions = client.get_json(
        f"draft/entry/{team_entry_id}/transactions", headers
    )
    if status in {401, 403}:
        raise DraftRelayError("Official Draft rejected authenticated entry transactions")
    if status == 404:
        raise DraftRelayError("Official Draft entry transaction endpoint was not found")
    if status != 200:
        raise DraftRelayError(f"Official Draft entry transactions unavailable: HTTP {status}")

    rows = _safe_rows(transactions, players, limit=max_rows)
    resolution = _transaction_resolution_counts(rows)

    my_team_status, my_team = client.get_json(f"entry/{team_entry_id}/my-team", headers)
    if my_team_status == 200:
        my_team_diagnostic = {
            "status": "ok",
            "schema": _interesting_schema(my_team),
        }
    else:
        my_team_diagnostic = {
            "status": f"http_{my_team_status}",
            "schema": {"type": "unavailable", "top_level_keys": [], "interesting_paths": []},
        }

    relay = {
        "schema_version": 1,
        "contract": CONTRACT,
        "generated_at": _utc_now(),
        "source": "official_fpl_draft",
        "league": {"id": league_id},
        "entry": {"entry_name": entry_name.strip(), "team_entry_id": team_entry_id},
        "entry_transactions": {
            "status": "ok",
            "auth_mode": auth_mode,
            "rows": rows,
            "resolution": resolution,
        },
        # Schema-only metadata. The private relay validator is free to discard it;
        # it exists so endpoint drift can be diagnosed without logging owner values.
        "source_diagnostics": {"entry_my_team": my_team_diagnostic},
        "producer": {
            "repository": producer_repository,
            "run_id": str(producer_run_id),
            "sha": sha,
        },
    }
    _reject_sensitive_keys(relay)
    return relay


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--league-id", type=int, default=DEFAULT_LEAGUE_ID)
    parser.add_argument("--entry-name", default=DEFAULT_ENTRY_NAME)
    parser.add_argument("--private-repository", required=True)
    parser.add_argument("--producer-repository", required=True)
    parser.add_argument("--producer-run-id", required=True)
    parser.add_argument("--producer-sha", required=True)
    parser.add_argument("--max-rows", type=int, default=MAX_ROWS)
    args = parser.parse_args()

    try:
        github_token = os.environ.get("APEX_PRIVATE_GITHUB_TOKEN", "").strip()
        if not github_token:
            raise DraftRelayError("private repository dispatch credential is not configured")
        client = HttpClient()
        relay = build_relay(
            client=client,
            league_id=args.league_id,
            entry_name=args.entry_name,
            token=os.environ.get("FPL_X_API_AUTHORIZATION", ""),
            cookie=os.environ.get("FPL_SESSION_COOKIE", ""),
            producer_repository=args.producer_repository,
            producer_run_id=args.producer_run_id,
            producer_sha=args.producer_sha,
            max_rows=args.max_rows,
        )
        status = client.dispatch(args.private_repository, github_token, relay)
        if status != 204:
            raise DraftRelayError(f"private repository dispatch rejected: HTTP {status}")
        print(
            json.dumps(
                {
                    "contract": relay["contract"],
                    "league_id": relay["league"]["id"],
                    "entry_name": relay["entry"]["entry_name"],
                    "team_entry_id": relay["entry"]["team_entry_id"],
                    "transaction_rows": len(relay["entry_transactions"]["rows"]),
                    "resolved_transaction_rows": relay["entry_transactions"]["resolution"]["resolved"],
                    "unresolved_transaction_rows": relay["entry_transactions"]["resolution"]["unresolved"],
                    "auth_mode": relay["entry_transactions"]["auth_mode"],
                    "entry_my_team_schema": relay["source_diagnostics"]["entry_my_team"],
                    "dispatch_status": status,
                },
                sort_keys=True,
            )
        )
        return 0
    except DraftRelayError as exc:
        print(f"ERROR: {exc}", file=__import__("sys").stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
