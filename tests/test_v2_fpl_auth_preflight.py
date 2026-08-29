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


MODULE = _load_preflight_module()
verify_owner_credential = MODULE.verify_owner_credential


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
        self.calls.append(("get", url, dict(headers), timeout))
        return self.responses.pop(0)

    def post(self, url, *, data, timeout):
        self.calls.append(("post", url, dict(data), timeout))
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
    headers = http.calls[0][2]
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
    token_headers = http.calls[0][2]
    cookie_headers = http.calls[1][2]
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


def test_refresh_exchange_uses_refresh_grant_and_returns_rotated_token(monkeypatch):
    monkeypatch.delenv("FPL_TOKEN_URL", raising=False)
    monkeypatch.delenv("FPL_OIDC_CLIENT_ID", raising=False)
    http = FakeHttp(
        [
            FakeResponse(
                200,
                {
                    "access_token": "fresh-access",
                    "refresh_token": "rotated-refresh",
                },
            )
        ]
    )
    access, refresh = MODULE._exchange_refresh_token("current-refresh", http=http)
    assert access == "fresh-access"
    assert refresh == "rotated-refresh"
    _, url, data, _ = http.calls[0]
    assert url == MODULE.DEFAULT_TOKEN_URL
    assert data == {
        "grant_type": "refresh_token",
        "refresh_token": "current-refresh",
        "client_id": MODULE.DEFAULT_OIDC_CLIENT_ID,
    }


def test_rejected_refresh_does_not_echo_secret():
    secret = "private-refresh-token-value"
    http = FakeHttp([FakeResponse(400, {"error": "invalid_grant"})])
    with pytest.raises(RuntimeError) as exc_info:
        MODULE._exchange_refresh_token(secret, http=http)
    assert "rejected or expired" in str(exc_info.value)
    assert secret not in str(exc_info.value)


def test_refresh_persists_rotation_before_returning_access(monkeypatch):
    order = []
    fake_store = object()
    fake_fernet = object()
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "bootstrap-refresh")
    monkeypatch.setattr(MODULE, "_private_store", lambda: fake_store)
    monkeypatch.setattr(MODULE, "_fernet", lambda: fake_fernet)
    monkeypatch.setattr(MODULE, "_latest_private_refresh_token", lambda store, fernet: None)
    monkeypatch.setattr(
        MODULE,
        "_exchange_refresh_token",
        lambda token, **kwargs: ("new-access", "new-refresh"),
    )
    monkeypatch.setattr(MODULE, "_verify_headers", lambda *args, **kwargs: "match")

    def persist(store, fernet, token):
        assert store is fake_store
        assert fernet is fake_fernet
        assert token == "new-refresh"
        order.append("persist")

    monkeypatch.setattr(MODULE, "_persist_private_refresh_token", persist)
    result = MODULE._refresh_owner_credential(63984)
    order.append("return")
    assert result == ("new-access", "new-refresh")
    assert order == ["persist", "return"]


def test_refresh_persistence_failure_fails_closed(monkeypatch):
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "bootstrap-refresh")
    monkeypatch.setattr(MODULE, "_private_store", lambda: object())
    monkeypatch.setattr(MODULE, "_fernet", lambda: object())
    monkeypatch.setattr(MODULE, "_latest_private_refresh_token", lambda store, fernet: None)
    monkeypatch.setattr(
        MODULE,
        "_exchange_refresh_token",
        lambda token, **kwargs: ("new-access", "new-refresh"),
    )
    monkeypatch.setattr(MODULE, "_verify_headers", lambda *args, **kwargs: "match")

    def fail_persist(*args, **kwargs):
        raise RuntimeError("private auth persistence failed")

    monkeypatch.setattr(MODULE, "_persist_private_refresh_token", fail_persist)
    with pytest.raises(RuntimeError, match="persistence failed"):
        MODULE._refresh_owner_credential(63984)


def test_private_rotated_state_precedes_bootstrap_secret(monkeypatch):
    used = []
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "stale-bootstrap")
    monkeypatch.setattr(MODULE, "_private_store", lambda: object())
    monkeypatch.setattr(MODULE, "_fernet", lambda: object())
    monkeypatch.setattr(
        MODULE,
        "_latest_private_refresh_token",
        lambda store, fernet: "latest-private-refresh",
    )

    def exchange(token, **kwargs):
        used.append(token)
        return "access", "next-refresh"

    monkeypatch.setattr(MODULE, "_exchange_refresh_token", exchange)
    monkeypatch.setattr(MODULE, "_verify_headers", lambda *args, **kwargs: "match")
    monkeypatch.setattr(MODULE, "_persist_private_refresh_token", lambda *args, **kwargs: None)
    assert MODULE._refresh_owner_credential(63984) == ("access", "next-refresh")
    assert used == ["latest-private-refresh"]


def test_refresh_requires_encrypted_private_store(monkeypatch):
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "bootstrap-refresh")
    monkeypatch.setattr(MODULE, "_private_store", lambda: None)
    monkeypatch.setattr(MODULE, "_fernet", lambda: None)
    with pytest.raises(RuntimeError, match="requires private storage"):
        MODULE._refresh_owner_credential(63984)
