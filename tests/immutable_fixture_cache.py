from __future__ import annotations

import atexit
from pathlib import Path
import shutil
import tempfile
from threading import RLock
from typing import Hashable


_LOCK = RLock()
_CACHE: dict[tuple[str, Hashable], tuple[Path, object]] = {}


def _store_root(store: object) -> Path | None:
    root = getattr(store, "root", None)
    if root is None:
        delegate = getattr(store, "delegate", None)
        root = getattr(delegate, "root", None)
    return None if root is None else Path(root)


def restore_cached_fixture(
    namespace: str,
    key: Hashable,
    *,
    store: object,
) -> object | None:
    """Clone pristine immutable fixture bytes into one isolated filesystem-backed store.

    Only synthetic evidence *generation* is cached. Production/control replay remains live in
    every test and still re-reads, hashes, reconstructs and verifies the cloned artifacts.
    Non-filesystem stores deliberately bypass this optimization.
    """

    root = _store_root(store)
    if root is None:
        return None
    with _LOCK:
        cached = _CACHE.get((namespace, key))
        if cached is None:
            return None
        snapshot_root, value = cached
        source_objects = snapshot_root / "objects"
        if source_objects.exists():
            shutil.copytree(source_objects, root / "objects", dirs_exist_ok=True)
        return value


def retain_cached_fixture(
    namespace: str,
    key: Hashable,
    value: object,
    *,
    store: object,
) -> object:
    """Retain a corruption-isolated pristine copy of deterministic test fixture bytes."""

    root = _store_root(store)
    if root is None:
        return value
    with _LOCK:
        cache_key = (namespace, key)
        if cache_key in _CACHE:
            return value
        snapshot_root = Path(tempfile.mkdtemp(prefix="apex-immutable-fixture-"))
        source_objects = root / "objects"
        if source_objects.exists():
            shutil.copytree(source_objects, snapshot_root / "objects")
        _CACHE[cache_key] = (snapshot_root, value)
    return value


def _cleanup() -> None:
    with _LOCK:
        snapshots = {snapshot for snapshot, _ in _CACHE.values()}
        _CACHE.clear()
    for snapshot in snapshots:
        shutil.rmtree(snapshot, ignore_errors=True)


atexit.register(_cleanup)
