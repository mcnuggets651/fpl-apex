from __future__ import annotations

import json

import pytest

from apex.runtime.snapshot import SnapshotBuilder, open_frozen_snapshot, sha256_bytes


def test_open_snapshot_recomputes_content_addressed_snapshot_identity(tmp_path):
    builder = SnapshotBuilder()
    builder.add_json("payload.json", {"value": "original"})
    frozen = builder.freeze(tmp_path)

    tampered = b'{"value":"tampered"}\n'
    payload_path = frozen.root / "payload.json"
    payload_path.write_bytes(tampered)

    manifest_path = frozen.root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    original_snapshot_id = manifest["snapshot_id"]
    manifest["files"]["payload.json"] = {
        "sha256": sha256_bytes(tampered),
        "bytes": len(tampered),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    assert manifest["snapshot_id"] == original_snapshot_id
    with pytest.raises(RuntimeError, match="snapshot.*identity|manifest.*integrity"):
        open_frozen_snapshot(frozen.root)


def test_snapshot_builder_rejects_parent_path_escape(tmp_path):
    builder = SnapshotBuilder()

    with pytest.raises(ValueError, match="snapshot file name"):
        builder.add_bytes("../escape.json", b"should-not-be-written")

    assert not (tmp_path / "escape.json").exists()


def test_snapshot_builder_rejects_absolute_path(tmp_path):
    builder = SnapshotBuilder()
    absolute = str((tmp_path / "absolute-escape.json").resolve())

    with pytest.raises(ValueError, match="snapshot file name"):
        builder.add_bytes(absolute, b"should-not-be-written")

    assert not (tmp_path / "absolute-escape.json").exists()
