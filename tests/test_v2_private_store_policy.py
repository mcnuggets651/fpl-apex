from __future__ import annotations

import pytest

from apex.runtime.releases import GitHubReleaseStore


class FakeResponse:
    def __init__(self, status_code: int, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.urls = []

    def get(self, url, **kwargs):
        del kwargs
        self.urls.append(url)
        if not self.responses:
            raise AssertionError(f"unexpected GET {url}")
        return self.responses.pop(0)


def test_private_store_policy_accepts_private_initialized_immutable_repository():
    session = FakeSession(
        [
            FakeResponse(200, {"private": True, "default_branch": "main"}),
            FakeResponse(200, {"name": "main"}),
            FakeResponse(200, {"enabled": True, "enforced_by_owner": False}),
        ]
    )
    store = GitHubReleaseStore("owner/apex-private", "token", session=session)
    policy = store.assert_repository_policy(
        require_private=True,
        require_immutable=True,
        require_initialized=True,
    )
    assert policy["private"] is True
    assert policy["initialized"] is True
    assert policy["default_branch"] == "main"
    assert policy["immutable_releases"] is True
    assert session.urls[1].endswith("/repos/owner/apex-private/branches/main")
    assert session.urls[-1].endswith("/repos/owner/apex-private/immutable-releases")


def test_private_store_policy_rejects_public_repository_before_other_checks():
    session = FakeSession(
        [FakeResponse(200, {"private": False, "default_branch": "main"})]
    )
    store = GitHubReleaseStore("owner/not-private", "token", session=session)
    with pytest.raises(RuntimeError, match="not private"):
        store.assert_repository_policy(
            require_private=True,
            require_immutable=True,
            require_initialized=True,
        )
    assert len(session.urls) == 1


def test_private_store_policy_rejects_uninitialized_repository():
    session = FakeSession(
        [
            FakeResponse(200, {"private": True, "default_branch": "main"}),
            FakeResponse(404, {}),
        ]
    )
    store = GitHubReleaseStore("owner/apex-private", "token", session=session)
    with pytest.raises(RuntimeError, match="no initialized default-branch commit"):
        store.assert_repository_policy(
            require_private=True,
            require_immutable=True,
            require_initialized=True,
        )
    assert len(session.urls) == 2


def test_private_store_policy_rejects_disabled_immutable_releases():
    session = FakeSession(
        [
            FakeResponse(200, {"private": True, "default_branch": "main"}),
            FakeResponse(200, {"name": "main"}),
            FakeResponse(404, {}),
        ]
    )
    store = GitHubReleaseStore("owner/apex-private", "token", session=session)
    with pytest.raises(RuntimeError, match="immutability is not enabled"):
        store.assert_repository_policy(
            require_private=True,
            require_immutable=True,
            require_initialized=True,
        )


def test_private_store_policy_rejects_nonaffirmative_enabled_payload():
    session = FakeSession(
        [
            FakeResponse(200, {"private": True, "default_branch": "main"}),
            FakeResponse(200, {"name": "main"}),
            FakeResponse(200, {"enabled": False}),
        ]
    )
    store = GitHubReleaseStore("owner/apex-private", "token", session=session)
    with pytest.raises(RuntimeError, match="enabled=true"):
        store.assert_repository_policy(
            require_private=True,
            require_immutable=True,
            require_initialized=True,
        )
