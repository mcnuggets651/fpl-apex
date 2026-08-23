from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore
from apex_fpl.control.release_registry import (
    CompareAndSwapConflict,
    FileSystemReleaseRegistry,
    ReleaseKey,
    ReleaseRecord,
    ReleaseStatus,
)


ROOT = Path(__file__).resolve().parents[1]


def _record(*, bundle: str, artifact: str, gameweek: int = 1) -> ReleaseRecord:
    return ReleaseRecord(
        season="2026-2027",
        entry=63984,
        gameweek=gameweek,
        bundle_id=bundle,
        world_id=None,
        runtime_digest="git:test",
        created_at=datetime(2026, 8, 23, tzinfo=timezone.utc).isoformat(),
        valid_until=None,
        status=ReleaseStatus.WITHHELD,
        ready_to_act=False,
        safe_to_act=False,
        artifact_manifest_id=artifact,
    )


def test_artifact_store_is_content_addressed_immutable_and_verified(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first = store.put_bytes(b"same bytes", media_type="text/plain")
    second = store.put_bytes(b"same bytes", media_type="application/octet-stream")

    assert first.artifact_id == second.artifact_id
    assert store.read_bytes(first.artifact_id) == b"same bytes"
    assert store.verify(first.artifact_id) is True

    object_path = (
        tmp_path
        / "artifacts"
        / "objects"
        / "sha256"
        / first.digest[:2]
        / first.digest
    )
    object_path.write_bytes(b"corrupted")
    assert store.verify(first.artifact_id) is False
    with pytest.raises(ArtifactIntegrityError):
        store.read_bytes(first.artifact_id)


def test_release_registry_rejects_stale_writer(tmp_path: Path):
    registry = FileSystemReleaseRegistry(tmp_path / "registry")
    key = ReleaseKey("2026-2027", 63984, 1)
    release_a = registry.append(_record(bundle="a", artifact="sha256:" + "a" * 64))
    release_b = registry.append(_record(bundle="b", artifact="sha256:" + "b" * 64))

    registry.compare_and_swap_current(
        key,
        expected_release_id=None,
        new_release_id=str(release_a.release_id),
    )
    assert registry.current_release_id(key) == release_a.release_id

    with pytest.raises(CompareAndSwapConflict):
        registry.compare_and_swap_current(
            key,
            expected_release_id=None,
            new_release_id=str(release_b.release_id),
        )

    registry.compare_and_swap_current(
        key,
        expected_release_id=str(release_a.release_id),
        new_release_id=str(release_b.release_id),
    )
    assert registry.current_release_id(key) == release_b.release_id


def test_production_workflow_cannot_write_runtime_state_to_main():
    text = (ROOT / ".github/workflows/pinnacle.yml").read_text(encoding="utf-8")
    assert "contents: read" in text
    assert "contents: write" not in text
    assert "git push origin HEAD:main" not in text
    assert "git add -f" not in text
    assert "data: publish canonical Apex recommendation" not in text
    assert "scripts/stage_runtime_release.py" in text
    assert "actions/upload-artifact@" in text


def test_live_recommendation_files_are_not_source_authoritative():
    forbidden = (
        "data/generated/apex_answer_context.json",
        "data/generated/apex_recommendation_latest.json",
        "data/generated/apex_recommendation_latest.md",
        "data/generated/pinnacle_latest.json",
        "data/generated/pinnacle_latest.md",
        "data/generated/elite_latest.json",
        "data/generated/elite_latest.md",
        "data/generated/solver_parity.json",
        "data/generated/calibration_report.json",
        "data/generated/apex_latest.json",
        "data/generated/apex_latest.md",
        "data/generated/airsenal.csv",
    )
    assert all(not (ROOT / path).exists() for path in forbidden)
