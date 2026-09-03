from __future__ import annotations

import importlib.util
import json
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


def _stub_no_recovery(monkeypatch):
    """Most tests below are not exercising the draft-recovery path itself;
    stub it out so they exercise only the ordinary exchange+persist flow."""
    monkeypatch.setattr(
        MODULE, "_recover_pending_rotation", lambda store, fernet, current: None
    )


def test_refresh_persists_rotation_before_returning_access(monkeypatch):
    order = []
    fake_store = object()
    fake_fernet = object()
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "bootstrap-refresh")
    monkeypatch.setattr(MODULE, "_private_store", lambda: fake_store)
    monkeypatch.setattr(MODULE, "_fernet", lambda: fake_fernet)
    monkeypatch.setattr(MODULE, "_latest_private_refresh_token", lambda store, fernet: None)
    _stub_no_recovery(monkeypatch)
    monkeypatch.setattr(
        MODULE,
        "_exchange_refresh_token",
        lambda token, **kwargs: ("new-access", "new-refresh"),
    )
    monkeypatch.setattr(MODULE, "_verify_headers", lambda *args, **kwargs: "match")

    def persist(store, fernet, token, *, parent_refresh_token):
        assert store is fake_store
        assert fernet is fake_fernet
        assert token == "new-refresh"
        assert parent_refresh_token == "bootstrap-refresh"
        order.append("persist")

    monkeypatch.setattr(MODULE, "_persist_private_refresh_token", persist)
    result = MODULE._refresh_owner_credential(63984)
    order.append("return")
    assert result == ("new-access", "new-refresh")
    assert order == ["persist", "return"]


def test_refresh_persistence_failure_raises_indeterminate_not_generic_error(monkeypatch):
    """A synchronous persistence failure AFTER a successful exchange must be
    reported as FPLRefreshRotationIndeterminate, not a generic RuntimeError
    indistinguishable from an ordinary rejected/expired credential. Collapsing
    these was the original defect: a caller that retries an "ordinary
    rejection" the same way it retries everything else would silently hammer
    a parent token that may already be dead at the identity provider."""
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "bootstrap-refresh")
    monkeypatch.setattr(MODULE, "_private_store", lambda: object())
    monkeypatch.setattr(MODULE, "_fernet", lambda: object())
    monkeypatch.setattr(MODULE, "_latest_private_refresh_token", lambda store, fernet: None)
    _stub_no_recovery(monkeypatch)
    monkeypatch.setattr(
        MODULE,
        "_exchange_refresh_token",
        lambda token, **kwargs: ("new-access", "new-refresh"),
    )
    monkeypatch.setattr(MODULE, "_verify_headers", lambda *args, **kwargs: "match")

    def fail_persist(*args, **kwargs):
        raise RuntimeError("private auth persistence failed")

    monkeypatch.setattr(MODULE, "_persist_private_refresh_token", fail_persist)
    with pytest.raises(MODULE.FPLRefreshRotationIndeterminate) as exc_info:
        MODULE._refresh_owner_credential(63984)
    # Must not be catchable as an ordinary rejected/expired-credential error.
    assert "rejected or expired" not in str(exc_info.value)
    assert "Do not retry against the same parent credential" in str(exc_info.value)


def test_exchange_failure_before_any_persistence_is_ordinary_rejection(monkeypatch):
    """Contrast case for the test above: if the EXCHANGE ITSELF fails, no
    durable next-token evidence was ever created, so there is no ambiguity
    and the original rejected/expired error must still surface unchanged."""
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "bootstrap-refresh")
    monkeypatch.setattr(MODULE, "_private_store", lambda: object())
    monkeypatch.setattr(MODULE, "_fernet", lambda: object())
    monkeypatch.setattr(MODULE, "_latest_private_refresh_token", lambda store, fernet: None)
    _stub_no_recovery(monkeypatch)

    def fail_exchange(token, **kwargs):
        raise RuntimeError("Official FPL refresh credential was rejected or expired")

    monkeypatch.setattr(MODULE, "_exchange_refresh_token", fail_exchange)
    persisted = []
    monkeypatch.setattr(
        MODULE, "_persist_private_refresh_token", lambda *a, **k: persisted.append(1)
    )
    with pytest.raises(RuntimeError, match="rejected or expired"):
        MODULE._refresh_owner_credential(63984)
    assert not persisted


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
    _stub_no_recovery(monkeypatch)

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


# --- Finding 1 regression tests: crash-window draft recovery -------------
#
# These exercise the specific defect from the FPL Apex red-team review:
# the OIDC exchange consumes/invalidates the parent refresh token BEFORE
# the rotated next-token is durably persisted. If the process dies between
# those two events, the parent is dead and the only surviving copy of the
# rotated token is whatever GitHub already durably has -- which may be an
# unpublished draft release. Recovery must find and use that draft rather
# than re-exchanging the (possibly already-dead) parent.


def test_recovery_finds_and_publishes_pending_draft_before_any_fresh_exchange(monkeypatch):
    """If a prior attempt's draft for this exact parent exists, it must be
    published and its token used as `current` for a FRESH rotation -- the
    original parent must never be re-exchanged."""
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "dead-parent")
    monkeypatch.setattr(MODULE, "_private_store", lambda: object())
    monkeypatch.setattr(MODULE, "_fernet", lambda: object())
    monkeypatch.setattr(MODULE, "_latest_private_refresh_token", lambda store, fernet: None)

    monkeypatch.setattr(
        MODULE,
        "_recover_pending_rotation",
        lambda store, fernet, current: (
            ("recovered-token", "apex-v2/private-auth/rotation/deadbeef")
            if current == "dead-parent"
            else None
        ),
    )
    published = []
    monkeypatch.setattr(
        MODULE, "_publish_pending_rotation", lambda store, tag: published.append(tag)
    )

    exchanged_with = []

    def exchange(token, **kwargs):
        exchanged_with.append(token)
        return "fresh-access", "brand-new-refresh"

    monkeypatch.setattr(MODULE, "_exchange_refresh_token", exchange)
    monkeypatch.setattr(MODULE, "_verify_headers", lambda *a, **k: "match")

    persisted = []

    def persist(store, fernet, token, *, parent_refresh_token):
        persisted.append((token, parent_refresh_token))

    monkeypatch.setattr(MODULE, "_persist_private_refresh_token", persist)

    result = MODULE._refresh_owner_credential(63984)

    assert published == ["apex-v2/private-auth/rotation/deadbeef"]
    # The dead parent is NEVER exchanged; only the recovered token is.
    assert exchanged_with == ["recovered-token"]
    assert result == ("fresh-access", "brand-new-refresh")
    # The recovered token gets its OWN correctly-persisted rotation.
    assert persisted == [("brand-new-refresh", "recovered-token")]


def test_no_recoverable_draft_proceeds_with_ordinary_exchange(monkeypatch):
    """When there is nothing to recover, behaviour must be identical to the
    pre-existing ordinary path (no draft lookup side effects change it)."""
    monkeypatch.setenv("FPL_REFRESH_TOKEN", "normal-parent")
    monkeypatch.setattr(MODULE, "_private_store", lambda: object())
    monkeypatch.setattr(MODULE, "_fernet", lambda: object())
    monkeypatch.setattr(MODULE, "_latest_private_refresh_token", lambda store, fernet: None)
    monkeypatch.setattr(
        MODULE, "_recover_pending_rotation", lambda store, fernet, current: None
    )
    published = []
    monkeypatch.setattr(
        MODULE, "_publish_pending_rotation", lambda store, tag: published.append(tag)
    )

    exchanged_with = []

    def exchange(token, **kwargs):
        exchanged_with.append(token)
        return "access", "next-refresh"

    monkeypatch.setattr(MODULE, "_exchange_refresh_token", exchange)
    monkeypatch.setattr(MODULE, "_verify_headers", lambda *a, **k: "match")
    monkeypatch.setattr(MODULE, "_persist_private_refresh_token", lambda *a, **k: None)

    result = MODULE._refresh_owner_credential(63984)
    assert not published
    assert exchanged_with == ["normal-parent"]
    assert result == ("access", "next-refresh")


def test_recover_pending_rotation_rejects_mismatched_parent_fingerprint(monkeypatch):
    """A decrypted draft whose stored parent_fingerprint does not match the
    fingerprint of the CURRENT parent token must fail closed rather than be
    treated as recoverable for the wrong rotation."""

    class _StubStore:
        def get_draft_by_tag(self, tag):
            return {"id": 1, "tag_name": tag}

    def fake_download(store, release, name, destination):
        destination.write_bytes(b"encrypted-placeholder")
        return destination

    monkeypatch.setattr(MODULE, "download_release_asset", fake_download)

    class _StubFernet:
        def decrypt(self, data):
            return json.dumps(
                {
                    "schema_version": 1,
                    "refresh_token": "irrelevant",
                    "parent_fingerprint": "wrong-fingerprint",
                }
            ).encode("utf-8")

    with pytest.raises(RuntimeError, match="does not match the current parent"):
        MODULE._recover_pending_rotation(_StubStore(), _StubFernet(), "actual-parent-token")


def test_recover_pending_rotation_returns_none_when_no_draft_exists(monkeypatch):
    class _StubStore:
        def get_draft_by_tag(self, tag):
            return None

    assert MODULE._recover_pending_rotation(_StubStore(), object(), "some-parent") is None


def test_refresh_transaction_fingerprint_is_deterministic_and_not_reversible():
    token = "a-very-secret-refresh-token-value"
    fp1 = MODULE._refresh_transaction_fingerprint(token)
    fp2 = MODULE._refresh_transaction_fingerprint(token)
    assert fp1 == fp2
    assert token not in fp1
    assert MODULE._refresh_transaction_fingerprint("different-token") != fp1


def test_different_parents_never_collide_on_rotation_tag():
    tag_a = MODULE._rotation_tag(MODULE._refresh_transaction_fingerprint("parent-a"))
    tag_b = MODULE._rotation_tag(MODULE._refresh_transaction_fingerprint("parent-b"))
    assert tag_a != tag_b
