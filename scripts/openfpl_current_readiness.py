#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from apex.forecast.openfpl_current import (
    CURRENT_EXACT_RULE_SEASON,
    CURRENT_FEATURE_CONTRACT_VERSION,
    CURRENT_SCORING_RULES_VERSION,
    CURRENT_TRAINING_POLICY_VERSION,
    REFERENCE_ROLLING_WINDOWS,
    SCORE_DEPENDENT_REFERENCE_FEATURE_FAMILIES,
    exact_rule_history_readiness,
    training_policy_errors,
    training_policy_sha256,
)
from apex.sources.official import fetch_official_snapshot

ROOT = Path(__file__).resolve().parents[1]
GW_RE = re.compile(r"^gw(\d+)\.csv$")


def _target_gameweek(official) -> int:
    now = datetime.now(timezone.utc)
    future: list[int] = []
    for gameweek, value in official.deadlines.items():
        deadline = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        if deadline.astimezone(timezone.utc) > now:
            future.append(int(gameweek))
    if not future:
        raise RuntimeError("no future Official FPL deadline")
    return min(future)


def _github_directory(repository: str, commit: str, path: str) -> list[dict[str, Any]]:
    url = f"https://api.github.com/repos/{repository}/contents/{path}?ref={commit}"
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "fpl-apex-v2-openfpl-readiness",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.load(response)
    if not isinstance(payload, list):
        raise RuntimeError("GitHub history directory response was not a list")
    return payload


def _load_policy(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("OpenFPL training policy must be a mapping")
    errors = training_policy_errors(raw)
    if errors:
        raise ValueError("invalid OpenFPL training policy: " + "; ".join(errors))
    return raw


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit exact 2026/27 label history against governed OpenFPL policy."
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--policy",
        type=Path,
        default=ROOT / "config/openfpl_training_policy.yaml",
    )
    args = parser.parse_args()

    policy_path = args.policy if args.policy.is_absolute() else ROOT / args.policy
    policy = _load_policy(policy_path)
    policy_digest = training_policy_sha256(policy)
    governed_minimum = int(policy["minimum_exact_rule_gameweeks"])

    lock = json.loads((ROOT / "upstreams.lock.json").read_text(encoding="utf-8"))[
        "sources"
    ]["openfpl_current_history"]
    if str(lock.get("exact_scoring_season")) != CURRENT_EXACT_RULE_SEASON:
        raise SystemExit(
            "OpenFPL current-history lock does not declare the exact current scoring season"
        )

    official, _ = fetch_official_snapshot(season="2026-2027", timeout=30.0)
    target = _target_gameweek(official)
    path = f"data/{CURRENT_EXACT_RULE_SEASON}/gws"
    entries = _github_directory(str(lock["repository"]), str(lock["commit"]), path)

    gameweeks: list[int] = []
    source_rows = []
    for entry in entries:
        match = GW_RE.match(str(entry.get("name", "")))
        if not match:
            continue
        gameweek = int(match.group(1))
        gameweeks.append(gameweek)
        source_rows.append(
            {
                "gameweek": gameweek,
                "name": entry.get("name"),
                "blob_sha": entry.get("sha"),
                "size": entry.get("size"),
            }
        )
    source_rows.sort(key=lambda row: row["gameweek"])

    readiness = exact_rule_history_readiness(
        tuple(gameweeks),
        target_gameweek=target,
        minimum_exact_rule_gameweeks=governed_minimum,
    )
    source_manifest_hash = hashlib.sha256(
        json.dumps(source_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    report = {
        "schema_version": 2,
        "provider": "openfpl",
        "scoring_rules_version": CURRENT_SCORING_RULES_VERSION,
        "exact_rule_season": CURRENT_EXACT_RULE_SEASON,
        "official_source_hash": official.source_hash,
        "target_gameweek": target,
        "history_repository": lock["repository"],
        "history_commit": lock["commit"],
        "history_committed_at": lock.get("committed_at"),
        "history_path": path,
        "history_rows": source_rows,
        "history_manifest_sha256": source_manifest_hash,
        "reference_rolling_windows": list(REFERENCE_ROLLING_WINDOWS),
        "score_dependent_reference_feature_families": list(
            SCORE_DEPENDENT_REFERENCE_FEATURE_FAMILIES
        ),
        "training_policy": {
            "path": str(policy_path.relative_to(ROOT)),
            "policy_version": CURRENT_TRAINING_POLICY_VERSION,
            "sha256": policy_digest,
            "minimum_exact_rule_gameweeks": governed_minimum,
            "feature_contract_version": CURRENT_FEATURE_CONTRACT_VERSION,
            "excluded_score_dependent_feature_families": list(
                policy["excluded_score_dependent_feature_families"]
            ),
            "valid": True,
        },
        "model_construction_authorized": bool(readiness["training_ready"]),
        "legacy_reference_weights_reused": False,
        "serve_authorized": False,
        "predictive_status": "INSUFFICIENT_HISTORY",
        **readiness,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, sort_keys=True))

    if readiness["state"] == "HISTORY_LEAKAGE":
        raise SystemExit(1)
    if readiness["training_ready"]:
        # This authorizes only a current-rules SHADOW model build. It does not
        # promote, serve, or certify OpenFPL for production authority.
        print("OpenFPL exact-rule history threshold satisfied; model build remains shadow-only")


if __name__ == "__main__":
    main()
