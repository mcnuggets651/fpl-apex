from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import pytest


def _load_preflight_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "preflight_fpl_auth.py"
    spec = importlib.util.spec_from_file_location("apex_v2_preflight_fpl_auth", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


verify_owner_credential = _load_preflight_module().verify_owner_credential


@dataclass
class FakeResponse:
    status_code: int
    payload: object

    def json(self):
        return self.payload


class FakeHttp:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, *, headers, timeout):
        self.calls.append((url, dict(headers), timeout))
        return self.responses.pop(0)


def _me(entry=63984):
    return {"player": {"entry": entry}}


def test_bearer_is_proven_independently_and_preferred():
    http = FakeHttp([FakeResponse(200, _me())])
    mode = verify_owner_credential(
        63984,
        token="secret-token",
        cookie="sessionid=secret-cookie",
        http=http,
    )
    assert mode == "token"
    headers = http.calls[0][1]
    assert headers["X-API-Authorization"] == "Bearer secret-token"
    assert "Cookie" not in headers


def test_rejected_bearer_cannot_poison_valid_cookie():
    http = FakeHttp(
        [
            FakeResponse(401, {}),
            FakeResponse(200, _me()),
        ]
    )
    mode = verify_owner_credential(
        63984,
        token="stale-token",
        cookie="ACCESS_TOKEN=fresh-cookie-token",
        http=http,
    )
    assert mode == "cookie"
    token_headers = http.calls[0][1]
    cookie_headers = http.calls[1][1]
    assert "Cookie" not in token_headers
    assert "X-API-Authorization" not in cookie_headers


def test_wrong_manager_fails_closed():
    http = FakeHttp([FakeResponse(200, _me(entry=12345))])
    with pytest.raises(RuntimeError, match="different manager entry"):
        verify_owner_credential(
            63984,
            token="secret-token",
            cookie="",
            http=http,
        )


def test_all_rejected_credentials_fail_without_secret_values():
    http = FakeHttp([FakeResponse(403, {}), FakeResponse(401, {})])
    token = "top-secret-token-value"
    cookie = "sessionid=top-secret-cookie-value"
    with pytest.raises(RuntimeError) as exc_info:
        verify_owner_credential(
            63984,
            token=token,
            cookie=cookie,
            http=http,
        )
    message = str(exc_info.value)
    assert "rejected or expired" in message
    assert token not in message
    assert cookie not in message


def test_missing_credentials_fail_closed():
    with pytest.raises(RuntimeError, match="not configured"):
        verify_owner_credential(63984, token="", cookie="", http=FakeHttp([]))
