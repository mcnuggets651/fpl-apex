#!/usr/bin/env python3
"""Bounded transient-HTTP retry helper for the pinned AIrsenal worker.

This module deliberately has no AIrsenal dependency so its retry semantics can be
unit-tested in Apex's normal environment. It retries only HTTP 429 and 5xx
responses; persistent failures and all non-transient errors remain fatal.
"""
from __future__ import annotations

import re
import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")
_STATUS_RE = re.compile(r"\bHTTP(?:\s+Error)?\s+(\d{3})\b", re.IGNORECASE)


def http_status_from_exception(exc: BaseException) -> int | None:
    """Extract an HTTP status from an exception/cause chain when available."""
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        response = getattr(current, "response", None)
        status = getattr(response, "status_code", None)
        if status is None:
            status = getattr(current, "status_code", None)
        try:
            if status is not None:
                parsed = int(status)
                if 100 <= parsed <= 599:
                    return parsed
        except (TypeError, ValueError):
            pass

        match = _STATUS_RE.search(str(current))
        if match:
            return int(match.group(1))
        current = current.__cause__ or current.__context__
    return None


def is_transient_http_status(status: int | None) -> bool:
    """Return True only for rate limiting and server-side transient failures."""
    return status == 429 or (status is not None and 500 <= status <= 599)


def retry_transient_http(
    operation: Callable[[], T],
    *,
    max_attempts: int = 4,
    base_delay_seconds: float = 1.0,
    sleeper: Callable[[float], None] = time.sleep,
    on_retry: Callable[[int, int, float, BaseException], None] | None = None,
) -> T:
    """Run ``operation`` with bounded retry for HTTP 429/5xx only.

    ``max_attempts`` counts the initial request. Delays are exponential between
    attempts. The original exception is re-raised unchanged once the budget is
    exhausted, preserving fail-closed provider freshness semantics.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")
    if base_delay_seconds < 0:
        raise ValueError("base_delay_seconds must be >= 0")

    for attempt in range(1, max_attempts + 1):
        try:
            return operation()
        except Exception as exc:
            status = http_status_from_exception(exc)
            if not is_transient_http_status(status) or attempt >= max_attempts:
                raise
            delay = base_delay_seconds * (2 ** (attempt - 1))
            if on_retry is not None:
                on_retry(attempt, int(status), delay, exc)
            sleeper(delay)

    raise AssertionError("unreachable retry state")
