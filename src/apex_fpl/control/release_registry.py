"""Immutable release records plus compare-and-swap current pointers."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterator


class ReleaseStatus(StrEnum):
    WITHHELD = "WITHHELD"
    V1_ACTIONABLE = "V1_ACTIONABLE"
    CERTIFIED = "CERTIFIED"
    PUBLISHED = "PUBLISHED"
    SUPERSEDED = "SUPERSEDED"


@dataclass(frozen=True)
class ReleaseKey:
    season: str
    entry: int
    gameweek: int

    def __post_init__(self) -> None:
        if not self.season.strip():
            raise ValueError("season is required")
        if self.entry <= 0:
            raise ValueError("entry must be positive")
        if self.gameweek <= 0:
            raise ValueError("gameweek must be positive")


@dataclass(frozen=True)
class ReleaseRecord:
    season: str
    entry: int
    gameweek: int | None
    bundle_id: str | None
    world_id: str | None
    runtime_digest: str
    created_at: str
    valid_until: str | None
    status: ReleaseStatus
    ready_to_act: bool
    safe_to_act: bool
    artifact_manifest_id: str
    superseded_by: str | None = None
    release_id: str | None = None

    def content_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload.pop("release_id", None)
        return payload

    def with_release_id(self) -> "ReleaseRecord":
        payload = _canonical_json_bytes(self.content_payload())
        release_id = sha256(payload).hexdigest()
        return replace(self, release_id=release_id)


class CompareAndSwapConflict(RuntimeError):
    """Raised when a stale writer attempts to move a current-release pointer."""


class ImmutableReleaseConflict(RuntimeError):
    """Raised if an existing release ID is presented with different bytes."""


def _canonical_json_bytes(payload: dict[str, object]) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


class FileSystemReleaseRegistry:
    """Filesystem adapter implementing immutable records and atomic CAS pointers.

    This adapter is intentionally backend-neutral domain infrastructure. It is suitable
    for tests, local recovery and a single shared POSIX volume. V2 production cutover
    must bind the same contract to a durable shared backend selected from operational
    evidence.
    """

    def __init__(self, root: str | Path, *, lock_timeout_seconds: float = 5.0):
        self.root = Path(root)
        self.lock_timeout_seconds = lock_timeout_seconds

    def _release_path(self, release_id: str) -> Path:
        return self.root / "releases" / f"{release_id}.json"

    def _pointer_path(self, key: ReleaseKey) -> Path:
        return (
            self.root
            / "current"
            / key.season
            / str(key.entry)
            / f"gw-{key.gameweek}.json"
        )

    @contextmanager
    def _lock(self, key: ReleaseKey) -> Iterator[None]:
        lock_path = self._pointer_path(key).with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.lock_timeout_seconds
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"release registry lock busy: {lock_path}")
                time.sleep(0.01)
        try:
            os.write(fd, f"{os.getpid()}\n".encode("ascii"))
            os.close(fd)
            fd = None
            yield
        finally:
            if fd is not None:
                os.close(fd)
            try:
                lock_path.unlink()
            except FileNotFoundError:
                pass

    def append(self, record: ReleaseRecord) -> ReleaseRecord:
        normalized = record if record.release_id else record.with_release_id()
        assert normalized.release_id is not None
        body = _canonical_json_bytes(
            {**normalized.content_payload(), "release_id": normalized.release_id}
        )
        destination = self._release_path(normalized.release_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != body:
                raise ImmutableReleaseConflict(normalized.release_id)
            return normalized

        fd: int | None = None
        try:
            fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, body)
            os.fsync(fd)
        finally:
            if fd is not None:
                os.close(fd)
        return normalized

    def current_release_id(self, key: ReleaseKey) -> str | None:
        path = self._pointer_path(key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("release_id")
        return str(value) if value else None

    def compare_and_swap_current(
        self,
        key: ReleaseKey,
        *,
        expected_release_id: str | None,
        new_release_id: str,
    ) -> None:
        if not self._release_path(new_release_id).exists():
            raise FileNotFoundError(f"unknown release: {new_release_id}")

        with self._lock(key):
            current = self.current_release_id(key)
            if current != expected_release_id:
                raise CompareAndSwapConflict(
                    f"stale writer for {key}: expected {expected_release_id!r}, "
                    f"found {current!r}"
                )
            pointer = {
                "schema_name": "apex-release-pointer",
                "schema_version": "1",
                "season": key.season,
                "entry": key.entry,
                "gameweek": key.gameweek,
                "release_id": new_release_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            path = self._pointer_path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".pointer-", dir=path.parent)
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(_canonical_json_bytes(pointer))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_path, path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
