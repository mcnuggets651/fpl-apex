from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

OFFICIAL_BOOTSTRAP = "https://fantasy.premierleague.com/api/bootstrap-static/"
API_ROOT = "https://api.github.com"
WORKFLOW_FILE = "apex-v2-daily-production.yml"
# Operational closure switch. This forces exactly the push-triggered watcher run
# created by merging this change to dispatch canonical production immediately.
# Scheduled watcher runs remain deadline-gated because they are not push events.
# Revert this to False immediately after the canonical production run starts.
FORCE_PUSH_DISPATCH_ONCE = True


def parse_utc(value: str) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("empty UTC timestamp")
    dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return dt.astimezone(timezone.utc)


@dataclass(frozen=True)
class DeadlineDecision:
    gameweek: int
    deadline_time: str
    seconds_until_deadline: int
    eligible: bool
    reason: str


def next_official_deadline(bootstrap: dict[str, Any], now: datetime) -> tuple[int, datetime]:
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    candidates: list[tuple[datetime, int]] = []
    events = bootstrap.get("events")
    if not isinstance(events, list):
        raise RuntimeError("Official FPL bootstrap omitted events")
    for event in events:
        if not isinstance(event, dict):
            continue
        try:
            gameweek = int(event["id"])
        except (KeyError, TypeError, ValueError):
            continue
        if gameweek <= 0 or bool(event.get("finished", False)):
            continue
        try:
            deadline = parse_utc(str(event["deadline_time"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"Official FPL unfinished GW{gameweek} lacks a valid deadline"
            ) from exc
        if deadline > now.astimezone(timezone.utc):
            candidates.append((deadline, gameweek))
    if not candidates:
        raise RuntimeError("Official FPL has no future Gameweek deadline")
    deadline, gameweek = min(candidates)
    return gameweek, deadline


def decide_deadline_window(
    bootstrap: dict[str, Any],
    *,
    now: datetime,
    min_minutes: int = 90,
    max_minutes: int = 150,
) -> DeadlineDecision:
    if min_minutes < 0 or max_minutes <= min_minutes:
        raise ValueError("deadline window must satisfy 0 <= min < max")
    gameweek, deadline = next_official_deadline(bootstrap, now)
    seconds = int((deadline - now.astimezone(timezone.utc)).total_seconds())
    lower = min_minutes * 60
    upper = max_minutes * 60
    if seconds < lower:
        reason = "TOO_CLOSE"
        eligible = False
    elif seconds > upper:
        reason = "TOO_EARLY"
        eligible = False
    else:
        reason = "IN_WINDOW"
        eligible = True
    return DeadlineDecision(
        gameweek=gameweek,
        deadline_time=deadline.isoformat().replace("+00:00", "Z"),
        seconds_until_deadline=seconds,
        eligible=eligible,
        reason=reason,
    )


def has_existing_deadline_run(
    runs_payload: dict[str, Any],
    *,
    deadline: datetime,
    min_minutes: int,
    max_minutes: int,
) -> bool:
    runs = runs_payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise RuntimeError("GitHub workflow-runs payload omitted workflow_runs")
    start = deadline - timedelta(minutes=max_minutes)
    end = deadline - timedelta(minutes=min_minutes)
    for run in runs:
        if not isinstance(run, dict) or str(run.get("event") or "") != "workflow_dispatch":
            continue
        try:
            created = parse_utc(str(run.get("created_at") or ""))
        except ValueError:
            continue
        if start <= created <= end:
            return True
    return False


def _json_request(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> tuple[int, Any]:
    headers = {
        "Accept": "application/vnd.github+json" if "api.github.com" in url else "application/json",
        "User-Agent": "apex-v2-deadline-watch/1",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2026-03-10"
    data = None
    if payload is not None:
        data = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, method=method, headers=headers, data=data)
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            if not raw:
                return int(response.status), None
            return int(response.status), json.loads(raw.decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code} from required deadline operation: {body}") from exc


def run_watch(
    *,
    repository: str,
    token: str,
    ref: str,
    now: datetime,
    min_minutes: int,
    max_minutes: int,
) -> dict[str, Any]:
    if not repository or "/" not in repository:
        raise RuntimeError("GITHUB_REPOSITORY is not configured")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is not configured")
    if ref != "main":
        raise RuntimeError("deadline watcher may dispatch only the main control plane")

    status, bootstrap = _json_request(OFFICIAL_BOOTSTRAP)
    if status != 200 or not isinstance(bootstrap, dict):
        raise RuntimeError("Official FPL bootstrap request failed")
    decision = decide_deadline_window(
        bootstrap,
        now=now,
        min_minutes=min_minutes,
        max_minutes=max_minutes,
    )
    forced_push = FORCE_PUSH_DISPATCH_ONCE and os.getenv("GITHUB_EVENT_NAME", "") == "push"
    result: dict[str, Any] = {
        "schema_version": 1,
        "gameweek": decision.gameweek,
        "deadline_time": decision.deadline_time,
        "seconds_until_deadline": decision.seconds_until_deadline,
        "eligible": decision.eligible or forced_push,
        "reason": "FORCED_PUSH_OPERATIONAL_CLOSURE" if forced_push else decision.reason,
        "dispatch": "NOT_ATTEMPTED",
    }
    if not decision.eligible and not forced_push:
        return result

    runs_url = (
        f"{API_ROOT}/repos/{repository}/actions/workflows/{WORKFLOW_FILE}/runs"
        "?event=workflow_dispatch&per_page=100"
    )
    status, runs = _json_request(runs_url, token=token)
    if status != 200 or not isinstance(runs, dict):
        raise RuntimeError("GitHub workflow run history could not be verified")
    deadline_dt = parse_utc(decision.deadline_time)
    if not forced_push and has_existing_deadline_run(
        runs, deadline=deadline_dt, min_minutes=min_minutes, max_minutes=max_minutes
    ):
        result["dispatch"] = "SKIPPED_ALREADY_RECORDED"
        return result

    dispatch_url = f"{API_ROOT}/repos/{repository}/actions/workflows/{WORKFLOW_FILE}/dispatches"
    status, _ = _json_request(
        dispatch_url,
        method="POST",
        token=token,
        payload={"ref": "main"},
    )
    # GitHub has returned 204 historically and currently may return 202 for
    # accepted asynchronous workflow dispatches. Treat all documented/observed
    # successful acceptance statuses as success.
    if status not in {201, 202, 204}:
        raise RuntimeError("GitHub did not accept deadline production dispatch")
    result["dispatch"] = "DISPATCHED"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--token", default=os.getenv("GITHUB_TOKEN", ""))
    parser.add_argument("--ref", default="main")
    parser.add_argument("--min-minutes", type=int, default=90)
    parser.add_argument("--max-minutes", type=int, default=150)
    parser.add_argument("--now", default="")
    args = parser.parse_args()
    now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)
    result = run_watch(
        repository=args.repository,
        token=args.token,
        ref=args.ref,
        now=now,
        min_minutes=args.min_minutes,
        max_minutes=args.max_minutes,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
