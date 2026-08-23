#!/usr/bin/env python3
"""Stage one V1-compatible run into immutable runtime artifacts.

This is the Slice 0 migration bridge. It stops treating Git as runtime state while
preserving the current fail-closed recommendation semantics. The generated registry
inside the workflow packet is intentionally transitional until a durable shared
ArtifactStore/ReleaseRegistry backend is selected and qualified.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import mimetypes
from pathlib import Path
from typing import Any

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.release_registry import (
    FileSystemReleaseRegistry,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _detect_gameweek(canonical: dict[str, Any], answer: dict[str, Any]) -> int | None:
    candidates: list[Any] = [
        canonical.get("gameweek"),
        canonical.get("gw"),
        canonical.get("next_actionable_gameweek"),
        answer.get("gameweek"),
        answer.get("gw"),
    ]
    recommendation = canonical.get("recommendation")
    if isinstance(recommendation, dict):
        candidates.extend(
            [
                recommendation.get("gameweek"),
                recommendation.get("gw"),
                recommendation.get("next_actionable_gameweek"),
            ]
        )
    gameweeks = canonical.get("gameweeks")
    if isinstance(gameweeks, list) and gameweeks:
        first = gameweeks[0]
        if isinstance(first, dict):
            candidates.extend([first.get("gameweek"), first.get("gw"), first.get("event")])
        else:
            candidates.append(first)

    for value in candidates:
        try:
            gameweek = int(value)
        except (TypeError, ValueError):
            continue
        if gameweek > 0:
            return gameweek
    return None


def _media_type(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--packet-root", required=True)
    parser.add_argument("--artifact-root", required=True)
    parser.add_argument("--registry-root", required=True)
    parser.add_argument("--season", required=True)
    parser.add_argument("--entry", required=True, type=int)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--runtime-digest", required=True)
    parser.add_argument("--gameweek", type=int)
    args = parser.parse_args()

    packet_root = Path(args.packet_root)
    artifact_store = FileSystemArtifactStore(args.artifact_root)
    registry = FileSystemReleaseRegistry(args.registry_root)

    canonical = _load_json(packet_root / "data/generated/apex_recommendation_latest.json")
    answer = _load_json(packet_root / "data/generated/apex_answer_context.json")
    if not canonical and not answer:
        raise SystemExit("runtime packet has no canonical or answer-context status")

    artifact_rows: list[dict[str, Any]] = []
    for path in sorted(item for item in packet_root.rglob("*") if item.is_file()):
        relative = path.relative_to(packet_root).as_posix()
        if relative.startswith("runtime/"):
            continue
        ref = artifact_store.put_file(path, media_type=_media_type(path))
        artifact_rows.append({"path": relative, **ref.as_dict()})

    manifest = {
        "schema_name": "apex-runtime-artifact-manifest",
        "schema_version": "1",
        "run_id": str(args.run_id),
        "runtime_digest": args.runtime_digest,
        "artifacts": artifact_rows,
    }
    manifest_bytes = (
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    manifest_ref = artifact_store.put_bytes(
        manifest_bytes,
        media_type="application/json",
        schema_name="apex-runtime-artifact-manifest",
        schema_version="1",
    )
    manifest["artifact_manifest_id"] = manifest_ref.artifact_id

    generated_at = str(
        answer.get("generated_at")
        or canonical.get("generated_at")
        or datetime.now(timezone.utc).isoformat()
    )
    ready = answer.get("ready_to_act") is True and canonical.get("ready_to_act") is True
    safe = answer.get("safe_to_act") is True and ready
    status = ReleaseStatus.V1_ACTIONABLE if safe else ReleaseStatus.WITHHELD
    gameweek = args.gameweek or _detect_gameweek(canonical, answer)
    record = ReleaseRecord(
        season=args.season,
        entry=args.entry,
        gameweek=gameweek,
        bundle_id=str(
            answer.get("decision_bundle_id") or canonical.get("decision_bundle_id") or ""
        )
        or None,
        world_id=None,
        runtime_digest=args.runtime_digest,
        created_at=generated_at,
        valid_until=None,
        status=status,
        ready_to_act=ready,
        safe_to_act=safe,
        artifact_manifest_id=manifest_ref.artifact_id,
    )
    record = registry.append(record)

    current_pointer_updated = False
    if gameweek is not None:
        key = ReleaseKey(args.season, args.entry, gameweek)
        expected = registry.current_release_id(key)
        registry.compare_and_swap_current(
            key,
            expected_release_id=expected,
            new_release_id=str(record.release_id),
        )
        current_pointer_updated = True

    runtime_dir = packet_root / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    (runtime_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    release_payload = {
        **record.content_payload(),
        "release_id": record.release_id,
        "current_pointer_updated": current_pointer_updated,
        "source_control_authoritative": False,
        "backend_class": "transitional_ci_artifact",
    }
    (runtime_dir / "release_record.json").write_text(
        json.dumps(release_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"staged runtime release {record.release_id} "
        f"(status={record.status.value}, gw={gameweek}, source_control=false)"
    )


if __name__ == "__main__":
    main()
