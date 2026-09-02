from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


_MANIFEST_NAME = "manifest.json"
_MANIFEST_FIELDS = frozenset({"schema_version", "files", "metadata", "snapshot_id"})


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _validate_snapshot_name(name: str) -> str:
    text = str(name)
    path = PurePosixPath(text)
    if (
        not text
        or path.is_absolute()
        or text != path.as_posix()
        or "\\" in text
        or any(part in {"", ".", ".."} for part in path.parts)
        or text == _MANIFEST_NAME
    ):
        raise ValueError(
            "snapshot file name must be a canonical relative POSIX path "
            "inside the snapshot and cannot be manifest.json"
        )
    return text


def _snapshot_core(manifest: dict) -> dict:
    if not isinstance(manifest, dict):
        raise RuntimeError("frozen snapshot manifest must be a JSON object")
    if frozenset(manifest) != _MANIFEST_FIELDS:
        raise RuntimeError("frozen snapshot manifest schema/integrity violation")
    if manifest.get("schema_version") != 1:
        raise RuntimeError("unsupported frozen snapshot manifest schema")
    files = manifest.get("files")
    metadata = manifest.get("metadata")
    if not isinstance(files, dict) or not files:
        raise RuntimeError("frozen snapshot manifest contains no files")
    if not isinstance(metadata, dict):
        raise RuntimeError("frozen snapshot metadata must be a JSON object")
    for raw_name, row in files.items():
        name = _validate_snapshot_name(raw_name)
        if name != raw_name:
            raise RuntimeError("frozen snapshot contains non-canonical file name")
        if not isinstance(row, dict):
            raise RuntimeError(f"frozen snapshot manifest entry invalid: {name}")
        digest = str(row.get("sha256") or "").lower()
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise RuntimeError(f"frozen snapshot file hash invalid: {name}")
        try:
            size = int(row["bytes"])
        except (KeyError, TypeError, ValueError) as exc:
            raise RuntimeError(f"frozen snapshot file size invalid: {name}") from exc
        if size < 0:
            raise RuntimeError(f"frozen snapshot file size invalid: {name}")
    return {
        "schema_version": 1,
        "files": files,
        "metadata": metadata,
    }


def _snapshot_id(core: dict) -> str:
    return sha256_bytes(
        json.dumps(
            core,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    )


@dataclass(frozen=True)
class FrozenSnapshot:
    snapshot_id: str
    root: Path
    manifest: dict

    def read_bytes(self, name: str) -> bytes:
        name = _validate_snapshot_name(name)
        files = self.manifest.get("files") or {}
        if name not in files:
            raise FileNotFoundError(name)
        path = self.root / name
        data = path.read_bytes()
        entry = files[name]
        expected = str(entry["sha256"]).lower()
        if sha256_bytes(data) != expected:
            raise RuntimeError(f"frozen snapshot integrity violation: {name}")
        if len(data) != int(entry["bytes"]):
            raise RuntimeError(f"frozen snapshot size integrity violation: {name}")
        return data

    def read_json(self, name: str):
        return json.loads(self.read_bytes(name))


class SnapshotBuilder:
    def __init__(self):
        self._files: dict[str, bytes] = {}
        self._frozen = False

    def add_bytes(self, name: str, data: bytes):
        if self._frozen:
            raise RuntimeError("snapshot already frozen; acquisition is closed")
        name = _validate_snapshot_name(name)
        if name in self._files:
            raise ValueError(f"duplicate snapshot file {name}")
        self._files[name] = bytes(data)

    def add_json(self, name: str, payload):
        self.add_bytes(
            name,
            (
                json.dumps(
                    payload,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                    allow_nan=False,
                )
                + "\n"
            ).encode(),
        )

    def freeze(
        self,
        base: Path,
        *,
        metadata: dict | None = None,
    ) -> FrozenSnapshot:
        if self._frozen:
            raise RuntimeError("snapshot already frozen")
        if not self._files:
            raise RuntimeError("cannot freeze empty snapshot")
        files = {
            name: {"sha256": sha256_bytes(data), "bytes": len(data)}
            for name, data in sorted(self._files.items())
        }
        core = {"schema_version": 1, "files": files, "metadata": metadata or {}}
        snapshot_id = _snapshot_id(core)
        manifest = {**core, "snapshot_id": snapshot_id}
        base = Path(base)
        base.mkdir(parents=True, exist_ok=True)
        target = base / snapshot_id
        if target.exists():
            existing = json.loads((target / _MANIFEST_NAME).read_text())
            if existing != manifest:
                raise RuntimeError("snapshot id collision/integrity violation")
            self._frozen = True
            return open_frozen_snapshot(target)
        stage = Path(tempfile.mkdtemp(prefix=".snapshot-", dir=base))
        try:
            for name, data in self._files.items():
                path = stage / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (stage / _MANIFEST_NAME).write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n"
            )
            os.replace(stage, target)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
        self._frozen = True
        return open_frozen_snapshot(target)


def open_frozen_snapshot(path: Path) -> FrozenSnapshot:
    path = Path(path)
    manifest = json.loads((path / _MANIFEST_NAME).read_text())
    core = _snapshot_core(manifest)
    computed_snapshot_id = _snapshot_id(core)
    recorded_snapshot_id = str(manifest.get("snapshot_id") or "").lower()
    if recorded_snapshot_id != computed_snapshot_id:
        raise RuntimeError(
            "frozen snapshot manifest integrity violation: snapshot identity mismatch"
        )
    snapshot = FrozenSnapshot(computed_snapshot_id, path, manifest)
    for name in core["files"]:
        snapshot.read_bytes(name)
    return snapshot
