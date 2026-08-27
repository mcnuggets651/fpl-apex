"""Immutable production-authority roots plus a dedicated season-level CAS pointer."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Iterator

from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.production_authority_root import ProductionAuthorityRoot


class AuthorityRootCompareAndSwapConflict(RuntimeError):
    """Raised when a stale writer attempts to move the current authority-root pointer."""


class ImmutableAuthorityRootConflict(RuntimeError):
    """Raised if an existing root ID is presented with different bytes."""


def _strict_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _optional_text(value: object, *, label: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string or null")
    return value.strip()


def authority_root_bytes(root: ProductionAuthorityRoot) -> bytes:
    return canonical_json_bytes(root.semantic_payload())


def parse_authority_root_bytes(
    content: bytes,
    *,
    expected_root_id: str,
) -> ProductionAuthorityRoot:
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("authority root registry row is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_name") != "apex-production-authority-root":
        raise ValueError("authority root registry row has wrong schema")
    if _strict_int(raw.get("schema_version"), label="authority root schema_version") != 1:
        raise ValueError("unsupported authority root schema")
    root = ProductionAuthorityRoot(
        season=str(raw.get("season") or ""),
        generation=_strict_int(raw.get("generation"), label="authority root generation"),
        parent_root_artifact_id=_optional_text(
            raw.get("parent_root_artifact_id"),
            label="authority root parent_root_artifact_id",
        ),
        champion_generation_artifact_id=str(raw.get("champion_generation_artifact_id") or ""),
        ruleset_artifact_id=str(raw.get("ruleset_artifact_id") or ""),
        ruleset_id=str(raw.get("ruleset_id") or ""),
        learning_policy_registry_artifact_id=str(
            raw.get("learning_policy_registry_artifact_id") or ""
        ),
        learning_policy_id=str(raw.get("learning_policy_id") or ""),
        outcome_truth_registry_artifact_id=str(
            raw.get("outcome_truth_registry_artifact_id") or ""
        ),
        outcome_truth_registry_id=str(raw.get("outcome_truth_registry_id") or ""),
        build_manifest_artifact_id=str(raw.get("build_manifest_artifact_id") or ""),
        build_manifest_id=str(raw.get("build_manifest_id") or ""),
        change_control_artifact_id=str(raw.get("change_control_artifact_id") or ""),
        authorized_by=str(raw.get("authorized_by") or ""),
        authorized_at=str(raw.get("authorized_at") or ""),
        valid_from=str(raw.get("valid_from") or ""),
        valid_until=str(raw.get("valid_until") or ""),
        reason=str(raw.get("reason") or ""),
        schema_version=1,
    )
    if root.root_id != str(expected_root_id) or authority_root_bytes(root) != content:
        raise ValueError("authority root registry identity mismatch")
    return root


class FileSystemAuthorityRootRegistry:
    """Reference filesystem authority-root history and atomic current pointer.

    This adapter is deliberately non-production. Production runtime accepts only the
    dedicated PostgreSQL adapter and separately qualified operational evidence.
    """

    backend_id = "apex.reference.filesystem-authority-root-registry.v1"

    def __init__(self, root: str | Path, *, lock_timeout_seconds: float = 5.0):
        self.root = Path(root)
        self.lock_timeout_seconds = lock_timeout_seconds

    def reopen(self) -> "FileSystemAuthorityRootRegistry":
        return FileSystemAuthorityRootRegistry(
            self.root,
            lock_timeout_seconds=self.lock_timeout_seconds,
        )

    def _root_path(self, root_id: str) -> Path:
        digest = str(root_id).removeprefix("sha256:")
        if len(digest) != 64:
            raise ValueError("authority root ID must be sha256 identity")
        return self.root / "authority-roots" / f"{digest}.json"

    def _pointer_path(self, season: str) -> Path:
        season = str(season).strip()
        if not season or "/" in season or "\\" in season:
            raise ValueError("authority root season is invalid")
        return self.root / "current-authority-root" / f"{season}.json"

    @contextmanager
    def _lock(self, season: str) -> Iterator[None]:
        lock_path = self._pointer_path(season).with_suffix(".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self.lock_timeout_seconds
        fd: int | None = None
        while fd is None:
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"authority root registry lock busy: {lock_path}")
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

    def append(self, root: ProductionAuthorityRoot) -> ProductionAuthorityRoot:
        body = authority_root_bytes(root)
        destination = self._root_path(root.root_id)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            if destination.read_bytes() != body:
                raise ImmutableAuthorityRootConflict(root.root_id)
            return root
        fd: int | None = None
        try:
            fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, body)
            os.fsync(fd)
        finally:
            if fd is not None:
                os.close(fd)
        return root

    def read_root(self, root_id: str) -> ProductionAuthorityRoot:
        return parse_authority_root_bytes(
            self._root_path(root_id).read_bytes(),
            expected_root_id=str(root_id),
        )

    def current_root_id(self, season: str) -> str | None:
        path = self._pointer_path(season)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("authority root pointer is not valid JSON") from exc
        if not isinstance(payload, dict) or payload.get("schema_name") != "apex-authority-root-pointer":
            raise ValueError("authority root pointer has wrong schema")
        if payload.get("season") != str(season):
            raise ValueError("authority root pointer season mismatch")
        value = payload.get("root_id")
        return None if value is None else str(value)

    def current_root(self, season: str) -> ProductionAuthorityRoot | None:
        root_id = self.current_root_id(season)
        return None if root_id is None else self.read_root(root_id)

    def compare_and_swap_current(
        self,
        season: str,
        *,
        expected_root_id: str | None,
        new_root_id: str,
    ) -> None:
        new_root = self.read_root(new_root_id)
        if new_root.season != str(season):
            raise ValueError("authority root cannot be selected for a different season")
        if new_root.parent_root_artifact_id != expected_root_id:
            raise ValueError("authority root parent must equal CAS expected current root")
        with self._lock(season):
            current = self.current_root_id(season)
            if current != expected_root_id:
                raise AuthorityRootCompareAndSwapConflict(
                    f"stale authority-root writer for {season}: expected {expected_root_id!r}, "
                    f"found {current!r}"
                )
            pointer = {
                "schema_name": "apex-authority-root-pointer",
                "schema_version": 1,
                "season": str(season),
                "root_id": str(new_root_id),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            path = self._pointer_path(season)
            path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".authority-root-", dir=path.parent)
            tmp_path = Path(tmp_name)
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(canonical_json_bytes(pointer))
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp_path, path)
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
