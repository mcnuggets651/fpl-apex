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
    publication_authorization_artifact_id: str | None = None
    superseded_by: str | None = None
    release_id: str | None = None

    def content_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload.pop("release_id", None)
        # Preserve every pre-Slice-13 historical ReleaseRecord identity exactly. Only a V2
        # production release carries the new proof-derived authorization field.
        if payload.get("publication_authorization_artifact_id") is None:
            payload.pop("publication_authorization_artifact_id", None)
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


def _strict_optional_string(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"release record {label} must be string or null")
    return value


def _release_record_from_payload(payload: object, *, expected_release_id: str) -> ReleaseRecord:
    if not isinstance(payload, dict):
        raise ValueError("release record must be JSON object")
    declared = payload.get("release_id")
    if declared != expected_release_id:
        raise ValueError("release record declared identity mismatch")
    entry = payload.get("entry")
    gameweek = payload.get("gameweek")
    ready = payload.get("ready_to_act")
    safe = payload.get("safe_to_act")
    if isinstance(entry, bool) or not isinstance(entry, int):
        raise ValueError("release record entry must be integer")
    if gameweek is not None and (isinstance(gameweek, bool) or not isinstance(gameweek, int)):
        raise ValueError("release record gameweek must be integer or null")
    if not isinstance(ready, bool) or not isinstance(safe, bool):
        raise ValueError("release record readiness fields must be booleans")
    record = ReleaseRecord(
        season=str(payload.get("season") or ""),
        entry=entry,
        gameweek=gameweek,
        bundle_id=_strict_optional_string(payload.get("bundle_id"), label="bundle_id"),
        world_id=_strict_optional_string(payload.get("world_id"), label="world_id"),
        runtime_digest=str(payload.get("runtime_digest") or ""),
        created_at=str(payload.get("created_at") or ""),
        valid_until=_strict_optional_string(payload.get("valid_until"), label="valid_until"),
        status=ReleaseStatus(str(payload.get("status") or "")),
        ready_to_act=ready,
        safe_to_act=safe,
        artifact_manifest_id=str(payload.get("artifact_manifest_id") or ""),
        publication_authorization_artifact_id=_strict_optional_string(
            payload.get("publication_authorization_artifact_id"),
            label="publication_authorization_artifact_id",
        ),
        superseded_by=_strict_optional_string(payload.get("superseded_by"), label="superseded_by"),
        release_id=expected_release_id,
    )
    if record.with_release_id().release_id != expected_release_id:
        raise ValueError("release record content identity mismatch")
    return record


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

    def read_release(self, release_id: str) -> ReleaseRecord:
        """Replay one immutable ReleaseRecord and verify its content identity."""

        value = str(release_id).strip()
        if not value:
            raise ValueError("release_id is required")
        path = self._release_path(value)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"release record is not valid UTF-8 JSON: {value}") from exc
        return _release_record_from_payload(payload, expected_release_id=value)

    def current_release_id(self, key: ReleaseKey) -> str | None:
        path = self._pointer_path(key)
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload.get("release_id")
        return str(value) if value else None

    def current_release(self, key: ReleaseKey) -> ReleaseRecord | None:
        """Resolve current pointer to an identity-verified immutable release."""

        release_id = self.current_release_id(key)
        return None if release_id is None else self.read_release(release_id)

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
