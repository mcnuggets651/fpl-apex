#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable


SELECTION_POLICY = "EARLIEST_FUTURE_DEADLINE_THEN_LATEST_VALID_FROZEN_AT"
MISSING_PUBLIC_ATTEMPT_ASSET = "MISSING_PUBLIC_ATTEMPT_ASSET"


class SourceResolutionError(RuntimeError):
    """Raised when an apparently modern immutable final violates authority invariants."""


def parse_utc(value: Any) -> datetime:
    text = str(value or "").strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _asset_names(release: dict[str, Any]) -> set[str]:
    return {
        str(asset.get("name") or "")
        for asset in release.get("assets") or []
        if isinstance(asset, dict)
    }


def _rejection(rejections: list[dict[str, str]], tag: str, reason: str) -> None:
    rejections.append({"tag": tag, "reason": reason})


def select_latest_eligible_source(
    releases: Iterable[dict[str, Any]],
    *,
    season: str,
    now: datetime,
    load_public_attempt: Callable[[dict[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    """Select the newest valid immutable production final for the nearest future deadline.

    Legacy final tags that predate the V2 public-attempt asset contract are explicit
    ineligible evidence, not fatal repository corruption. Once a release advertises
    the modern asset, identity/authority violations fail closed.
    """

    now = now.astimezone(timezone.utc)
    prefix = f"apex-v2/final/{season}/"
    candidates: list[dict[str, Any]] = []
    rejections: list[dict[str, str]] = []
    examined = 0

    for release in releases:
        tag = str(release.get("tag_name") or "")
        if not tag.startswith(prefix):
            continue
        examined += 1
        if release.get("draft"):
            _rejection(rejections, tag, "DRAFT_RELEASE")
            continue
        if release.get("immutable") is not True:
            _rejection(rejections, tag, "RELEASE_NOT_IMMUTABLE")
            continue
        if "public_attempt.json" not in _asset_names(release):
            _rejection(rejections, tag, MISSING_PUBLIC_ATTEMPT_ASSET)
            continue

        try:
            payload = load_public_attempt(release)
        except FileNotFoundError:
            # Protect against release-list/asset-read races and legacy malformed tags.
            _rejection(rejections, tag, MISSING_PUBLIC_ATTEMPT_ASSET)
            continue
        if not isinstance(payload, dict):
            raise SourceResolutionError(f"public attempt is not an object: {tag}")

        run_key = tag[len(prefix) :]
        if str(payload.get("run_id") or "") != run_key:
            raise SourceResolutionError(f"final release run identity mismatch: {tag}")
        if str(payload.get("season") or "") != season:
            raise SourceResolutionError(f"final release season mismatch: {tag}")

        try:
            target_gameweek = int(payload.get("target_gameweek") or 0)
            frozen_at = parse_utc(payload.get("frozen_at"))
            deadline = parse_utc((payload.get("certification") or {}).get("valid_until"))
        except Exception as exc:
            raise SourceResolutionError(
                f"invalid final authority fields for {tag}: {exc}"
            ) from exc

        if target_gameweek < 3:
            _rejection(rejections, tag, "PRE_GW3_FINAL")
            continue
        if frozen_at >= deadline:
            _rejection(rejections, tag, "SOURCE_NOT_PREDEADLINE")
            continue
        if now >= deadline:
            _rejection(rejections, tag, "DEADLINE_PASSED")
            continue
        if (payload.get("certification") or {}).get("actionable") is not True:
            _rejection(rejections, tag, "PRODUCTION_NOT_ACTIONABLE")
            continue
        if (
            (payload.get("manager_actionability") or {}).get(
                "personalized_actionable"
            )
            is not True
        ):
            _rejection(rejections, tag, "MANAGER_NOT_ACTIONABLE")
            continue

        serving = payload.get("serving_provider_by_horizon") or {}
        if any(
            str(serving.get(str(h), serving.get(h, ""))) != "airsenal"
            for h in range(1, 9)
        ):
            raise SourceResolutionError(
                f"serving authority drift in immutable final: {tag}"
            )

        candidates.append(
            {
                "run_id": run_key,
                "target_gameweek": target_gameweek,
                "frozen_at": frozen_at,
                "deadline": deadline,
                "source_release_tag": tag,
            }
        )

    counts = dict(sorted(Counter(row["reason"] for row in rejections).items()))
    audit = {
        "examined_final_release_count": examined,
        "eligible_candidate_count": len(candidates),
        "rejection_counts": counts,
        "rejections": rejections,
        "selection_policy": SELECTION_POLICY,
    }

    if not candidates:
        return {
            "schema_version": 1,
            "status": "NO_ELIGIBLE_SOURCE",
            "run_id": None,
            **audit,
        }

    current_deadline = min(row["deadline"] for row in candidates)
    current = [row for row in candidates if row["deadline"] == current_deadline]
    selected = max(current, key=lambda row: row["frozen_at"])
    return {
        "schema_version": 1,
        "status": "FOUND",
        "run_id": selected["run_id"],
        "target_gameweek": selected["target_gameweek"],
        "frozen_at": selected["frozen_at"].isoformat(),
        "deadline": selected["deadline"].isoformat(),
        "source_release_tag": selected["source_release_tag"],
        **audit,
    }


def resolve_github_source(
    *, repo: str, season: str, token: str, now: datetime
) -> dict[str, Any]:
    from apex.runtime.releases import GitHubReleaseStore, download_release_asset

    store = GitHubReleaseStore(repo, token)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def load_public_attempt(release: dict[str, Any]) -> dict[str, Any]:
            path = download_release_asset(
                store,
                release,
                "public_attempt.json",
                root / f"{release['id']}-public_attempt.json",
            )
            return json.loads(path.read_text(encoding="utf-8"))

        return select_latest_eligible_source(
            store.list_releases(),
            season=season,
            now=now,
            load_public_attempt=load_public_attempt,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Resolve an immutable predeadline Apex V2 tournament source final."
    )
    parser.add_argument("--repo", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--now",
        default=None,
        help="Optional UTC timestamp for deterministic diagnostics/tests; defaults to now.",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN is required")
    now = parse_utc(args.now) if args.now else datetime.now(timezone.utc)
    result = resolve_github_source(
        repo=args.repo,
        season=args.season,
        token=token,
        now=now,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
