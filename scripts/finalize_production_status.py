#!/usr/bin/env python3
"""Fail closed when a production run stops before canonical assembly."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def _diagnostic_matches(path: Path, bundle_id: str) -> bool:
    payload = _load(path)
    return bool(bundle_id and payload.get("decision_bundle_id") == bundle_id)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="data/generated")
    parser.add_argument("--bundle-dir", default="data/generated/decision_bundle")
    parser.add_argument("--archive-dir", default="data/history/production_runs")
    parser.add_argument("--run-id", default="local")
    parser.add_argument("--reason", default="production workflow stopped before canonical assembly")
    parser.add_argument("--canonical-step-succeeded", action="store_true")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    manifest_path = Path(args.bundle_dir) / "manifest.json"
    manifest = _load(manifest_path)
    bundle_id = str(manifest.get("bundle_id") or "")
    created_at = str(manifest.get("created_at") or datetime.now(timezone.utc).isoformat())
    canonical_path = output_dir / "apex_recommendation_latest.json"
    canonical = _load(canonical_path)

    # A current, fully assembled contract needs no fallback. Everything else must
    # replace any previously committed actionable recommendation.
    if (
        args.canonical_step_succeeded
        and bundle_id
        and canonical.get("decision_bundle_id") == bundle_id
    ):
        print(f"Current canonical contract already matches bundle {bundle_id}")
        return

    blockers = [str(args.reason)]
    pinnacle_path = output_dir / "pinnacle_latest.json"
    if _diagnostic_matches(pinnacle_path, bundle_id):
        pinnacle = _load(pinnacle_path)
        blockers.extend(
            str(row)
            for row in ((pinnacle.get("pinnacle_gate") or {}).get("blockers") or [])
        )
    latest = _load(Path("reports/latest.json"))
    for row in (latest.get("data_quality") or {}).get("failures") or []:
        blockers.append(str(row))
    blockers = list(dict.fromkeys(blockers))

    identity = manifest.get("identity") if isinstance(manifest.get("identity"), dict) else {}
    official = identity.get("official") if isinstance(identity.get("official"), dict) else {}
    official_snapshot = {
        "snapshot_id": (latest.get("official_snapshot") or {}).get("snapshot_id"),
        "bootstrap_sha256": official.get("bootstrap_sha256"),
        "fixtures_sha256": official.get("fixtures_sha256"),
    }
    payload = {
        "contract": "apex-strategy-recommendation-v2",
        "generated_at": created_at,
        "canonical": True,
        "user_facing_source_of_truth": True,
        "ready_to_act": False,
        "blockers": blockers,
        "official_snapshot": official_snapshot,
        "decision_bundle_id": bundle_id or None,
        "decision_bundle": {
            "contract": manifest.get("contract"),
            "bundle_id": bundle_id or None,
            "material_inputs": identity.get("material_inputs", {}),
        },
        "gameweeks": [],
        "recommendation": None,
        "failure_stage": "pre_canonical_assembly",
    }
    answer = {
        "contract": "apex-answer-context-v1",
        "generated_at": created_at,
        "safe_to_act": False,
        "ready_to_act": False,
        "blockers": blockers,
        "decision_bundle_id": bundle_id or None,
        "recommendation": None,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    canonical_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    (output_dir / "apex_answer_context.json").write_text(
        json.dumps(answer, indent=2) + "\n", encoding="utf-8"
    )
    (output_dir / "apex_recommendation_latest.md").write_text(
        "# Apex Unified Recommendation — NOT READY\n\n"
        f"Generated: {created_at}\n\n"
        "The production run stopped before canonical assembly:\n\n"
        + "\n".join(f"- {row}" for row in blockers)
        + "\n",
        encoding="utf-8",
    )

    # Stale diagnostics are never allowed to travel beside a current bundle.
    rejected: dict[str, str | None] = {}
    for name in ("pinnacle_latest.json", "solver_parity.json", "elite_latest.json"):
        path = output_dir / name
        if path.exists() and not _diagnostic_matches(path, bundle_id):
            rejected[name] = _sha256(path)
            path.unlink()
            markdown = path.with_suffix(".md")
            if markdown.exists():
                markdown.unlink()

    archive_dir = Path(args.archive_dir)
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_key = bundle_id or f"run-{args.run_id}"
    record = {
        "contract": "apex-production-run-v1",
        "run_id": str(args.run_id),
        "generated_at": created_at,
        "status": "not_ready",
        "decision_bundle_id": bundle_id or None,
        "official_snapshot": official_snapshot,
        "blockers": blockers,
        "rejected_stale_diagnostics": rejected,
        "manifest_sha256": _sha256(manifest_path),
    }
    (archive_dir / f"{archive_key}.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Published teamless NOT READY for bundle {bundle_id or 'unavailable'}")


if __name__ == "__main__":
    main()
