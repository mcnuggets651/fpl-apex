"""Immutable content-addressed runtime artifact storage contracts.

Slice 0 deliberately keeps the production interface independent from any one backend.
The filesystem adapter is useful for tests, local recovery and staging a sealed packet.
A durable remote backend can implement the same protocol without changing domain code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import os
from pathlib import Path
import tempfile
from typing import Protocol


@dataclass(frozen=True)
class ArtifactRef:
    """Reference to one immutable content-addressed object."""

    digest: str
    size: int
    media_type: str = "application/octet-stream"
    schema_name: str | None = None
    schema_version: str | None = None

    @property
    def artifact_id(self) -> str:
        return f"sha256:{self.digest}"

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["artifact_id"] = self.artifact_id
        return payload


class ArtifactIntegrityError(RuntimeError):
    """Raised when bytes do not match their declared content identity."""


class ArtifactStore(Protocol):
    """Stable port for immutable runtime artifact storage."""

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        schema_name: str | None = None,
        schema_version: str | None = None,
    ) -> ArtifactRef: ...

    def read_bytes(self, artifact_id: str) -> bytes: ...

    def verify(self, artifact_id: str) -> bool: ...


class FileSystemArtifactStore:
    """Content-addressed store with immutable objects and atomic writes."""

    def __init__(self, root: str | Path):
        self.root = Path(root)

    @staticmethod
    def _digest_from_id(artifact_id: str) -> str:
        algorithm, separator, digest = str(artifact_id).partition(":")
        if algorithm != "sha256" or not separator or len(digest) != 64:
            raise ValueError(f"invalid artifact id: {artifact_id!r}")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError(f"invalid sha256 digest: {digest!r}") from exc
        return digest

    def _object_path(self, digest: str) -> Path:
        return self.root / "objects" / "sha256" / digest[:2] / digest

    def put_bytes(
        self,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        schema_name: str | None = None,
        schema_version: str | None = None,
    ) -> ArtifactRef:
        if not isinstance(content, bytes):
            raise TypeError("artifact content must be bytes")
        digest = sha256(content).hexdigest()
        destination = self._object_path(digest)
        destination.parent.mkdir(parents=True, exist_ok=True)

        if destination.exists():
            existing = destination.read_bytes()
            if existing != content:
                raise ArtifactIntegrityError(
                    f"content collision or corruption at sha256:{digest}"
                )
        else:
            fd, tmp_name = tempfile.mkstemp(prefix=".artifact-", dir=destination.parent)
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(content)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_path, destination)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()

        return ArtifactRef(
            digest=digest,
            size=len(content),
            media_type=media_type,
            schema_name=schema_name,
            schema_version=schema_version,
        )

    def put_file(
        self,
        path: str | Path,
        *,
        media_type: str = "application/octet-stream",
        schema_name: str | None = None,
        schema_version: str | None = None,
    ) -> ArtifactRef:
        return self.put_bytes(
            Path(path).read_bytes(),
            media_type=media_type,
            schema_name=schema_name,
            schema_version=schema_version,
        )

    def read_bytes(self, artifact_id: str) -> bytes:
        digest = self._digest_from_id(artifact_id)
        path = self._object_path(digest)
        content = path.read_bytes()
        if sha256(content).hexdigest() != digest:
            raise ArtifactIntegrityError(f"artifact failed integrity check: {artifact_id}")
        return content

    def verify(self, artifact_id: str) -> bool:
        try:
            self.read_bytes(artifact_id)
        except (FileNotFoundError, ArtifactIntegrityError, ValueError):
            return False
        return True
