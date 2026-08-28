from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import hashlib, json, os, tempfile

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

@dataclass(frozen=True)
class FrozenSnapshot:
    snapshot_id: str
    root: Path
    manifest: dict

    def read_bytes(self, name: str) -> bytes:
        path = self.root / name
        data = path.read_bytes()
        expected = self.manifest['files'][name]['sha256']
        if sha256_bytes(data) != expected:
            raise RuntimeError(f'frozen snapshot integrity violation: {name}')
        return data

    def read_json(self, name: str):
        return json.loads(self.read_bytes(name))

class SnapshotBuilder:

    def __init__(self):
        self._files: dict[str, bytes] = {}
        self._frozen = False

    def add_bytes(self, name: str, data: bytes):
        if self._frozen:
            raise RuntimeError('snapshot already frozen; acquisition is closed')
        if name in self._files:
            raise ValueError(f'duplicate snapshot file {name}')
        self._files[name] = bytes(data)

    def add_json(self, name: str, payload):
        self.add_bytes(name, (json.dumps(payload, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False) + '\n').encode())

    def freeze(self, base: Path, *, metadata: dict | None=None) -> FrozenSnapshot:
        if self._frozen:
            raise RuntimeError('snapshot already frozen')
        if not self._files:
            raise RuntimeError('cannot freeze empty snapshot')
        files = {n: {'sha256': sha256_bytes(b), 'bytes': len(b)} for n, b in sorted(self._files.items())}
        core = {'schema_version': 1, 'files': files, 'metadata': metadata or {}}
        snapshot_id = sha256_bytes(json.dumps(core, sort_keys=True, separators=(',', ':')).encode())
        manifest = {**core, 'snapshot_id': snapshot_id}
        base = Path(base)
        base.mkdir(parents=True, exist_ok=True)
        target = base / snapshot_id
        if target.exists():
            existing = json.loads((target / 'manifest.json').read_text())
            if existing != manifest:
                raise RuntimeError('snapshot id collision/integrity violation')
            self._frozen = True
            return FrozenSnapshot(snapshot_id, target, manifest)
        stage = Path(tempfile.mkdtemp(prefix='.snapshot-', dir=base))
        try:
            for n, b in self._files.items():
                p = stage / n
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b)
            (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2, sort_keys=True) + '\n')
            os.replace(stage, target)
        finally:
            if stage.exists():
                import shutil
                shutil.rmtree(stage)
        self._frozen = True
        return FrozenSnapshot(snapshot_id, target, manifest)

def open_frozen_snapshot(path: Path) -> FrozenSnapshot:
    path = Path(path)
    manifest = json.loads((path / 'manifest.json').read_text())
    snap = FrozenSnapshot(manifest['snapshot_id'], path, manifest)
    for name in manifest['files']:
        snap.read_bytes(name)
    return snap
