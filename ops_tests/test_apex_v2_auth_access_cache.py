from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest


def _load_ops():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apex_v2_auth_ops.py"
    spec = importlib.util.spec_from_file_location("apex_v2_auth_ops_cache_test", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ops = _load_ops()


class FakeFernet:
    def encrypt(self, data: bytes) -> bytes:
        return b"enc:" + data

    def decrypt(self, data: bytes) -> bytes:
        if not data.startswith(b"enc:"):
            raise ValueError("bad ciphertext")
        return data[4:]


class FakeStore:
    def __init__(self):
        self.published: list[dict] = []
        self.drafts: dict[str, dict] = {}
        self.next_id = 1

    def list_releases(self):
        return [*self.drafts.values(), *self.published]

    def _create_draft_and_upload(
        self,
        tag,
        files,
        *,
        target_commitish,
        name,
        body,
    ):
        del target_commitish, name, body
        asset_name, path = next(iter(files.items()))
        raw = Path(path).read_bytes()
        release = {
            "id": self.next_id,
            "tag_name": tag,
            "draft": True,
            "asset_name": asset_name,
            "raw": raw,
        }
        self.next_id += 1
        self.drafts[tag] = release
        return release["id"], {asset_name: hashlib.sha256(raw).hexdigest()}

    def _publish_draft(self, tag, release_id, uploaded, *, require_immutable):
        del uploaded, require_immutable
        draft = self.drafts.pop(tag)
        assert int(draft["id"]) == int(release_id)
        draft["draft"] = False
        self.published.append(draft)
        return SimpleNamespace(tag=tag, immutable=True)

    def _cleanup_mutable_release(self, release_id, tag):
        del release_id
        self.drafts.pop(tag, None)


class FakeAuthModule:
    AUTH_TAG_PREFIX = "apex-v2/private-auth/"
    AUTH_ASSET = "fpl_refresh_state.enc"
    DEFAULT_OIDC_CLIENT_ID = "client"
    Fernet = FakeFernet

    def __init__(self):
        self.verify_results: list[object] = []

    @staticmethod
    def _refresh_transaction_fingerprint(token):
        return f"fp-{sum(token.encode('utf-8'))}"

    def _rotation_tag(self, fingerprint):
        return f"{self.AUTH_TAG_PREFIX}rotation/{fingerprint}"

    def _exchange_refresh_token(self, token):
        raise AssertionError(f"unexpected refresh exchange for {token}")

    def _verify_headers(self, entry_id, *, headers):
        assert entry_id == 63984
        assert headers["X-API-Authorization"].startswith("Bearer ")
        result = self.verify_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    @staticmethod
    def _bearer_header(token):
        return f"Bearer {token}"

    @staticmethod
    def _entry_id(config):
        del config
        return 63984

    @staticmethod
    def _latest_private_refresh_token(store, fernet):
        del store, fernet
        return None

    @staticmethod
    def _write_runtime_env(path, *, token="", cookie=""):
        del cookie
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(f"FPL_X_API_AUTHORIZATION={token}\n")

    @staticmethod
    def _write_github_output(path, mode):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(f"auth_mode={mode}\n")

    @staticmethod
    def download_release_asset(store, release, name, destination):
        del store
        assert name == release["asset_name"]
        Path(destination).write_bytes(release["raw"])
        return Path(destination)


ENV = {
    "FPL_REFRESH_TOKEN": "bootstrap",
    "FPL_REFRESH_WRAP_KEY": "wrap",
    "APEX_PRIVATE_GITHUB_REPOSITORY": "owner/private",
    "APEX_PRIVATE_GITHUB_TOKEN": "private-token",
}
CONFIG = Path("config/apex_v2.yaml")


def _active_store(*, refresh="parent", access: str | None = "cached-access"):
    fernet = FakeFernet()
    payload = {
        "schema_version": 1,
        "refresh_token": refresh,
        "stored_at": "2026-09-05T18:00:00+00:00",
    }
    if access is not None:
        payload["access_token"] = access
    raw = fernet.encrypt(json.dumps(payload).encode("utf-8"))
    store = FakeStore()
    store.published.append(
        {
            "id": 7,
            "tag_name": "apex-v2/private-auth/rotation/fp-parent",
            "draft": False,
            "created_at": "2026-09-05T18:00:00Z",
            "asset_name": FakeAuthModule.AUTH_ASSET,
            "raw": raw,
        }
    )
    return store, fernet


def test_staged_rotation_persists_access_token_inside_encrypted_private_state():
    module = FakeAuthModule()
    store = FakeStore()
    fernet = FakeFernet()

    tag, _, _ = ops._stage_refresh_rotation(
        module,
        store,
        fernet,
        parent_refresh_token="parent",
        next_refresh_token="child",
        access_token="verified-access",
        env=ENV,
    )

    payload = json.loads(fernet.decrypt(store.drafts[tag]["raw"]).decode("utf-8"))
    assert payload["refresh_token"] == "child"
    assert payload["access_token"] == "verified-access"


def test_matching_cached_access_is_reused_without_refresh_exchange():
    module = FakeAuthModule()
    module.verify_results = ["match"]
    store, fernet = _active_store()

    with (
        mock.patch.object(ops, "_refresh_context", return_value=(store, fernet)),
        mock.patch.object(ops, "_rotate_refresh_parent") as rotate,
        mock.patch.object(ops, "_emit_refresh_success") as emit,
    ):
        assert ops._try_private_refresh(
            module,
            config=CONFIG,
            github_output=None,
            github_env=None,
            env=ENV,
        )

    rotate.assert_not_called()
    emit.assert_called_once()
    assert emit.call_args.kwargs["access_token"] == "cached-access"
    assert emit.call_args.kwargs["recovery"] == "cached_access"


def test_explicitly_rejected_cached_access_rotates_exactly_once():
    module = FakeAuthModule()
    module.verify_results = ["rejected"]
    store, fernet = _active_store()

    with (
        mock.patch.object(ops, "_refresh_context", return_value=(store, fernet)),
        mock.patch.object(
            ops,
            "_rotate_refresh_parent",
            return_value=("fresh-access", "child"),
        ) as rotate,
        mock.patch.object(ops, "_emit_refresh_success") as emit,
    ):
        assert ops._try_private_refresh(
            module,
            config=CONFIG,
            github_output=None,
            github_env=None,
            env=ENV,
        )

    rotate.assert_called_once()
    assert rotate.call_args.kwargs["parent_refresh_token"] == "parent"
    emit.assert_called_once()
    assert emit.call_args.kwargs["access_token"] == "fresh-access"
    assert emit.call_args.kwargs["recovery"] == "none"


def test_cached_wrong_manager_fails_without_consuming_refresh_state():
    module = FakeAuthModule()
    module.verify_results = ["wrong_manager"]
    store, fernet = _active_store()

    with (
        mock.patch.object(ops, "_refresh_context", return_value=(store, fernet)),
        mock.patch.object(ops, "_rotate_refresh_parent") as rotate,
        pytest.raises(ops.AuthOpsError, match="different manager"),
    ):
        ops._try_private_refresh(
            module,
            config=CONFIG,
            github_output=None,
            github_env=None,
            env=ENV,
        )

    rotate.assert_not_called()


def test_cached_access_transport_error_fails_without_consuming_refresh_state():
    module = FakeAuthModule()
    module.verify_results = [RuntimeError("upstream timeout with secret-looking body")]
    store, fernet = _active_store()

    with (
        mock.patch.object(ops, "_refresh_context", return_value=(store, fernet)),
        mock.patch.object(ops, "_rotate_refresh_parent") as rotate,
        pytest.raises(ops.AuthOpsError, match="was not consumed") as exc_info,
    ):
        ops._try_private_refresh(
            module,
            config=CONFIG,
            github_output=None,
            github_env=None,
            env=ENV,
        )

    rotate.assert_not_called()
    assert "secret-looking" not in str(exc_info.value)


def test_legacy_active_state_without_access_token_remains_refresh_compatible():
    module = FakeAuthModule()
    store, fernet = _active_store(access=None)

    with (
        mock.patch.object(ops, "_refresh_context", return_value=(store, fernet)),
        mock.patch.object(
            ops,
            "_rotate_refresh_parent",
            return_value=("fresh-access", "child"),
        ) as rotate,
        mock.patch.object(ops, "_emit_refresh_success"),
    ):
        assert ops._try_private_refresh(
            module,
            config=CONFIG,
            github_output=None,
            github_env=None,
            env=ENV,
        )

    rotate.assert_called_once()
    assert rotate.call_args.kwargs["parent_refresh_token"] == "parent"
