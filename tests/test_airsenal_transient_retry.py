from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "apex_airsenal_transient_retry",
    ROOT / "scripts/airsenal_transient_retry.py",
)
assert SPEC is not None and SPEC.loader is not None
RETRY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RETRY)


class _Response:
    def __init__(self, status_code: int):
        self.status_code = status_code


class _HTTPError(RuntimeError):
    def __init__(self, status_code: int, message: str | None = None):
        super().__init__(message or f"HTTP Error {status_code}: transient")
        self.response = _Response(status_code)


def test_transient_retry_recovers_after_503() -> None:
    calls = 0
    delays: list[float] = []
    retries: list[tuple[int, int, float]] = []

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise _HTTPError(503)
        return "fresh"

    result = RETRY.retry_transient_http(
        operation,
        max_attempts=4,
        base_delay_seconds=1.0,
        sleeper=delays.append,
        on_retry=lambda attempt, status, delay, _exc: retries.append(
            (attempt, status, delay)
        ),
    )

    assert result == "fresh"
    assert calls == 3
    assert delays == [1.0, 2.0]
    assert retries == [(1, 503, 1.0), (2, 503, 2.0)]


def test_rate_limit_is_transient_but_404_is_not() -> None:
    assert RETRY.is_transient_http_status(429) is True
    assert RETRY.is_transient_http_status(500) is True
    assert RETRY.is_transient_http_status(599) is True
    assert RETRY.is_transient_http_status(404) is False
    assert RETRY.is_transient_http_status(None) is False


def test_non_transient_http_error_is_not_retried() -> None:
    calls = 0

    def operation() -> None:
        nonlocal calls
        calls += 1
        raise _HTTPError(404)

    with pytest.raises(_HTTPError):
        RETRY.retry_transient_http(
            operation,
            sleeper=lambda _delay: pytest.fail("404 must not sleep/retry"),
        )
    assert calls == 1


def test_persistent_503_re_raises_original_final_failure() -> None:
    calls = 0
    failures: list[_HTTPError] = []

    def operation() -> None:
        nonlocal calls
        calls += 1
        exc = _HTTPError(503)
        failures.append(exc)
        raise exc

    with pytest.raises(_HTTPError) as caught:
        RETRY.retry_transient_http(
            operation,
            max_attempts=4,
            base_delay_seconds=0.0,
            sleeper=lambda _delay: None,
        )

    assert calls == 4
    assert caught.value is failures[-1]


def test_status_extraction_traverses_wrapped_cause() -> None:
    inner = _HTTPError(503)
    outer = RuntimeError("player detail request failed")
    outer.__cause__ = inner
    assert RETRY.http_status_from_exception(outer) == 503


def test_status_extraction_falls_back_to_error_text() -> None:
    assert RETRY.http_status_from_exception(RuntimeError("HTTP Error 502: gateway")) == 502


def test_retry_configuration_fails_closed() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        RETRY.retry_transient_http(lambda: None, max_attempts=0)
    with pytest.raises(ValueError, match="base_delay_seconds"):
        RETRY.retry_transient_http(lambda: None, base_delay_seconds=-1)
