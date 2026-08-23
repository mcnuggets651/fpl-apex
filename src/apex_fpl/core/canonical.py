"""Canonical serialization for semantic identity.

Apex V2 intentionally narrows durable semantic JSON to values whose representation is
unambiguous across supported runtimes: null, booleans, integers, strings, arrays and
string-keyed objects. Probabilistic/numeric artifacts must quantise or encode governed
non-integer values before entering semantic identity.

For this restricted value domain, sorted UTF-8 JSON with minimal separators is the
project's documented RFC 8785-compatible profile. Floats (including NaN/Infinity) are
rejected instead of relying on implementation-specific formatting.
"""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Any


class NonCanonicalValueError(ValueError):
    """Raised when a value cannot enter Apex semantic identity."""


def _validate(value: Any, *, path: str = "$") -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        raise NonCanonicalValueError(
            f"{path}: floats are forbidden; quantise and encode under NumericPolicy"
        )
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise NonCanonicalValueError(f"{path}: object key {key!r} is not a string")
            _validate(item, path=f"{path}.{key}")
        return
    raise NonCanonicalValueError(f"{path}: unsupported canonical type {type(value).__name__}")


def canonical_json_bytes(value: Any) -> bytes:
    """Return deterministic UTF-8 bytes for allowed semantic content."""

    _validate(value)
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Return a namespaced SHA-256 semantic identifier."""

    return f"sha256:{sha256(canonical_json_bytes(value)).hexdigest()}"
