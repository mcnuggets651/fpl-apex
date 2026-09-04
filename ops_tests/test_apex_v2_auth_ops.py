from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apex_v2_auth_ops.py"
    spec = importlib.util.spec_from_file_location("apex_v2_auth_ops", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ops = _load_module()

ROOT = Path(__file__).resolve().parents[1]
PRODUCTION_WORKFLOW = ROOT / ".github" / "workflows" / "apex-v2-daily-production.yml"
KEEPALIVE_WORKFLOW = ROOT / ".github" / "workflows" / "apex-v2-auth-keepalive.yml"
DRAFT_WORKFLOW = ROOT / ".github" / "workflows" / "apex-v2-draft-auth-relay.yml"
FROZEN_SHA = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


class FakeFernet:
    def encrypt(self, data: bytes) -> bytes:
        return b"enc:" + data

    def decrypt(self, data: bytes) -> bytes:
        if not data.startswith(b"enc:"):
            raise ValueError("bad ciphertext")
        return data[4:]


class FakeStore:
    def __init__(self, events=None):
        self.events = events if events is not None else []
        self.drafts = {}
        self.published = []
        self.next_id = 1
        self.fail_cleanup = False

    def get_draft_by_tag(self, tag):
        return self.drafts.get(tag)

    def list_releases(self, per_page=100):
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
        self.events.append("stage")
        if tag in self.drafts:
            raise RuntimeError("duplicate draft")
        asset_name, path = next(iter(files.items()))
        release = {
            "id": self.next_id,
            "tag_name": tag,
            "draft": True,
            "name": name,
            "body": body,
            "asset_name": asset_name,
            "raw": Path(path).read_bytes(),
        }
        self.next_id += 1
        self.drafts[tag] = release
        return release["id"], {asset_name: hashlib.sha256(release["raw"]).hexdigest()}

    def _publish_draft(self, tag, release_id, uploaded, *, require_immutable):
        self.events.append("publish")
        draft = self.drafts.get(tag)
        if draft is None or int(draft["id"]) != int(release_id):
            raise RuntimeError("missing draft")
        expected = hashlib.sha256(draft["raw"]).hexdigest()
        if uploaded != {draft["asset_name"]: expected}:
            raise RuntimeError("digest mismatch")
        draft = self.drafts.pop(tag)
        draft["draft"] = False
        draft["immutable"] = bool(require_immutable)
        self.published.append(draft)
        return SimpleNamespace(tag=tag, immutable=bool(require_immutable))

    def _cleanup_mutable_release(self, release_id, tag):
        self.events.append("cleanup")
        if self.fail_cleanup:
            raise RuntimeError("cleanup failed with secret-looking detail")
        draft = self.drafts.get(tag)
        if draft is not None and int(draft["id"]) != int(release_id):
            raise RuntimeError("wrong release id")
        self.drafts.pop(tag, None)


class FakeAuthModule:
    DEFAULT_OIDC_CLIENT_ID = "client"
    AUTH_ASSET = "fpl_refresh_state.enc"
    Fernet = FakeFernet

    def __init__(self, store=None, events=None):
        self.events = events if events is not None else []
        self.store = store or FakeStore(self.events)
        self.exchange_results = []
        self.verify_results = []
        self.private_parent = None
        self.exchanged = []

    @staticmethod
    def _refresh_transaction_fingerprint(token):
        # Deterministic and value-free enough for unit tests.
        return f"fp-{sum(token.encode('utf-8'))}"

    def _rotation_tag(self, fingerprint):
        return f"apex-v2/private-auth/rotation/{fingerprint}"

    def _recover_pending_rotation(self, store, fernet, parent):
        tag = self._rotation_tag(self._refresh_transaction_fingerprint(parent))
        draft = store.get_draft_by_tag(tag)
        if draft is None:
            return None
        payload = json.loads(fernet.decrypt(draft["raw"]).decode("utf-8"))
        if payload["parent_fingerprint"] != self._refresh_transaction_fingerprint(parent):
            raise RuntimeError("wrong parent fingerprint")
        return payload["refresh_token"], tag

    def _publish_pending_rotation(self, store, tag):
        self.events.append("publish")
        draft = store.drafts.pop(tag)
        draft["draft"] = False
        store.published.append(draft)

    @staticmethod
    def download_release_asset(store, draft, name, destination):
        if name != draft["asset_name"]:
            raise RuntimeError("unknown asset")
        Path(destination).write_bytes(draft["raw"])
        return Path(destination)

    def _exchange_refresh_token(self, token):
        self.events.append("exchange")
        self.exchanged.append(token)
        result = self.exchange_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    def _verify_headers(self, entry_id, *, headers):
        self.events.append("verify")
        result = self.verify_results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    @staticmethod
    def _bearer_header(token):
        return f"Bearer {token}"

    @staticmethod
    def _entry_id(config):
        return 63984

    def _latest_private_refresh_token(self, store, fernet):
        return self.private_parent

    @staticmethod
    def _write_runtime_env(path, *, token="", cookie=""):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(f"FPL_X_API_AUTHORIZATION={token}\n")
            handle.write(f"FPL_SESSION_COOKIE={cookie}\n")

    @staticmethod
    def _write_github_output(path, mode):
        with Path(path).open("a", encoding="utf-8") as handle:
            handle.write(f"auth_mode={mode}\n")


class AuthOperationsTests(unittest.TestCase):
    def setUp(self):
        self.script = Path("scripts/preflight_fpl_auth.py")
        self.config = Path("config/apex_v2.yaml")
        self.env = {
            "FPL_REFRESH_TOKEN": "bootstrap",
            "FPL_REFRESH_WRAP_KEY": "wrap",
            "APEX_PRIVATE_GITHUB_REPOSITORY": "owner/private",
            "APEX_PRIVATE_GITHUB_TOKEN": "private-token",
            "FPL_X_API_AUTHORIZATION": "direct-token",
            "FPL_SESSION_COOKIE": "",
        }

    @staticmethod
    def result(returncode: int, *, stdout: str = "", stderr: str = ""):
        return subprocess.CompletedProcess(
            args=["preflight"], returncode=returncode, stdout=stdout, stderr=stderr
        )

    def test_rotation_stages_before_owner_verification_and_publishes_only_after_match(self):
        events = []
        store = FakeStore(events)
        module = FakeAuthModule(store, events)
        module.exchange_results = [("access", "child")]
        module.verify_results = ["match"]

        access, child = ops._rotate_refresh_parent(
            module,
            entry_id=63984,
            store=store,
            fernet=FakeFernet(),
            parent_refresh_token="parent",
            env=self.env,
        )

        self.assertEqual((access, child), ("access", "child"))
        self.assertEqual(events[:4], ["exchange", "stage", "verify", "publish"])
        self.assertEqual(len(store.published), 1)
        self.assertFalse(store.drafts)

    def test_unexpected_owner_verification_keeps_child_staged_and_inactive(self):
        events = []
        store = FakeStore(events)
        module = FakeAuthModule(store, events)
        module.exchange_results = [("access", "recoverable-child")]
        module.verify_results = [RuntimeError("upstream 503 with secret-looking body")]

        with self.assertRaises(ops.RefreshRotationIndeterminate) as exc_info:
            ops._rotate_refresh_parent(
                module,
                entry_id=63984,
                store=store,
                fernet=FakeFernet(),
                parent_refresh_token="parent",
                env=self.env,
            )

        self.assertEqual(events, ["exchange", "stage", "verify"])
        self.assertEqual(len(store.drafts), 1)
        self.assertFalse(store.published)
        self.assertNotIn("secret-looking", str(exc_info.exception))

    def test_rejected_refreshed_access_is_indeterminate_not_bootstrap_fallback(self):
        store = FakeStore()
        module = FakeAuthModule(store)
        module.exchange_results = [("access", "recoverable-child")]
        module.verify_results = ["rejected"]

        with self.assertRaises(ops.RefreshRotationIndeterminate):
            ops._rotate_refresh_parent(
                module,
                entry_id=63984,
                store=store,
                fernet=FakeFernet(),
                parent_refresh_token="parent",
                env=self.env,
            )
        self.assertEqual(len(store.drafts), 1)
        self.assertFalse(store.published)

    def test_wrong_manager_discards_staged_chain_and_never_activates_it(self):
        events = []
        store = FakeStore(events)
        module = FakeAuthModule(store, events)
        module.exchange_results = [("access", "wrong-manager-child")]
        module.verify_results = ["wrong_manager"]

        with self.assertRaisesRegex(ops.AuthOpsError, "different manager"):
            ops._rotate_refresh_parent(
                module,
                entry_id=63984,
                store=store,
                fernet=FakeFernet(),
                parent_refresh_token="parent",
                env=self.env,
            )
        self.assertEqual(events, ["exchange", "stage", "verify", "cleanup"])
        self.assertFalse(store.drafts)
        self.assertFalse(store.published)

    def test_wrong_manager_cleanup_failure_requires_manual_cleanup_and_stays_secret_free(self):
        store = FakeStore()
        store.fail_cleanup = True
        module = FakeAuthModule(store)
        module.exchange_results = [("access", "wrong-manager-child")]
        module.verify_results = ["wrong_manager"]

        with self.assertRaisesRegex(
            ops.AuthOpsError, "manual private-store cleanup is required"
        ) as exc_info:
            ops._rotate_refresh_parent(
                module,
                entry_id=63984,
                store=store,
                fernet=FakeFernet(),
                parent_refresh_token="parent",
                env=self.env,
            )
        self.assertEqual(len(store.drafts), 1)
        self.assertFalse(store.published)
        self.assertNotIn("secret-looking", str(exc_info.exception))

    def test_stage_failure_after_exchange_is_indeterminate_and_not_generic_rejection(self):
        store = FakeStore()
        module = FakeAuthModule(store)
        module.exchange_results = [("access", "child")]
        module.verify_results = ["match"]
        with mock.patch.object(
            ops,
            "_stage_refresh_rotation",
            side_effect=RuntimeError("private store unavailable secret-value"),
        ):
            with self.assertRaises(ops.RefreshRotationIndeterminate) as exc_info:
                ops._rotate_refresh_parent(
                    module,
                    entry_id=63984,
                    store=store,
                    fernet=FakeFernet(),
                    parent_refresh_token="parent",
                    env=self.env,
                )
        self.assertNotIn("secret-value", str(exc_info.exception))

    def test_pending_child_is_used_before_consumed_parent_is_reexchanged(self):
        events = []
        store = FakeStore(events)
        module = FakeAuthModule(store, events)
        fernet = FakeFernet()
        # Simulate a previous run: exchange parent -> child was staged, then
        # owner verification failed before activation.
        ops._stage_refresh_rotation(
            module,
            store,
            fernet,
            parent_refresh_token="dead-parent",
            next_refresh_token="staged-child",
            env=self.env,
        )
        events.clear()
        module.exchange_results = [("fresh-access", "new-active-child")]
        module.verify_results = ["match"]

        result = ops._rotate_refresh_parent(
            module,
            entry_id=63984,
            store=store,
            fernet=fernet,
            parent_refresh_token="dead-parent",
            env=self.env,
        )

        self.assertEqual(result, ("fresh-access", "new-active-child"))
        self.assertEqual(module.exchanged, ["staged-child"])
        self.assertNotIn("dead-parent", module.exchanged)
        self.assertEqual(len(store.published), 1)
        # The consumed intermediate staged draft is removed after final child activation.
        self.assertFalse(store.drafts)

    def test_exchange_rejection_before_staging_is_safe_for_bootstrap_recovery(self):
        module = FakeAuthModule(FakeStore())
        module.exchange_results = [RuntimeError(ops.REFRESH_REJECTION)]
        with self.assertRaises(ops.RefreshRejected):
            ops._rotate_refresh_parent(
                module,
                entry_id=63984,
                store=module.store,
                fernet=FakeFernet(),
                parent_refresh_token="rejected-parent",
                env=self.env,
            )
        self.assertFalse(module.store.drafts)

    def test_indeterminate_private_rotation_never_falls_through_to_bootstrap_or_direct(self):
        fake_module = SimpleNamespace()
        with (
            mock.patch.object(ops, "_load_frozen_auth", return_value=fake_module),
            mock.patch.object(
                ops,
                "_try_private_refresh",
                side_effect=ops.RefreshRotationIndeterminate("staged child retained"),
            ),
            mock.patch.object(ops, "_bootstrap_recover") as bootstrap,
            mock.patch.object(ops, "_direct_recover") as direct,
        ):
            with self.assertRaises(ops.RefreshRotationIndeterminate):
                ops.authenticate(
                    mode="production",
                    preflight_script=self.script,
                    config=self.config,
                    github_output=None,
                    github_env=None,
                    env=self.env,
                )
        bootstrap.assert_not_called()
        direct.assert_not_called()

    def test_private_exchange_rejection_prefers_bootstrap_recovery(self):
        fake_module = SimpleNamespace()
        with (
            mock.patch.object(ops, "_load_frozen_auth", return_value=fake_module),
            mock.patch.object(
                ops,
                "_try_private_refresh",
                side_effect=ops.RefreshRejected(ops.REFRESH_REJECTION),
            ),
            mock.patch.object(ops, "_bootstrap_recover") as bootstrap,
            mock.patch.object(ops, "_direct_recover") as direct,
        ):
            outcome = ops.authenticate(
                mode="production",
                preflight_script=self.script,
                config=self.config,
                github_output=None,
                github_env=None,
                env=self.env,
            )
        self.assertEqual(outcome, "bootstrap")
        bootstrap.assert_called_once()
        direct.assert_not_called()

    def test_production_direct_auth_only_after_refresh_and_bootstrap_exchange_reject(self):
        fake_module = SimpleNamespace()
        with (
            mock.patch.object(ops, "_load_frozen_auth", return_value=fake_module),
            mock.patch.object(
                ops,
                "_try_private_refresh",
                side_effect=ops.RefreshRejected(ops.REFRESH_REJECTION),
            ),
            mock.patch.object(
                ops,
                "_bootstrap_recover",
                side_effect=ops.RefreshRejected(ops.REFRESH_REJECTION),
            ) as bootstrap,
            mock.patch.object(ops, "_direct_recover") as direct,
        ):
            outcome = ops.authenticate(
                mode="production",
                preflight_script=self.script,
                config=self.config,
                github_output=None,
                github_env=None,
                env=self.env,
            )
        self.assertEqual(outcome, "direct")
        bootstrap.assert_called_once()
        direct.assert_called_once()

    def test_keepalive_never_substitutes_direct_auth_for_dead_refresh_chain(self):
        fake_module = SimpleNamespace()
        with (
            mock.patch.object(ops, "_load_frozen_auth", return_value=fake_module),
            mock.patch.object(
                ops,
                "_try_private_refresh",
                side_effect=ops.RefreshRejected(ops.REFRESH_REJECTION),
            ),
            mock.patch.object(
                ops,
                "_bootstrap_recover",
                side_effect=ops.RefreshRejected(ops.REFRESH_REJECTION),
            ),
            mock.patch.object(ops, "_direct_recover") as direct,
        ):
            with self.assertRaises(ops.AuthOpsError):
                ops.authenticate(
                    mode="keepalive",
                    preflight_script=self.script,
                    config=self.config,
                    github_output=None,
                    github_env=None,
                    env=self.env,
                )
        direct.assert_not_called()

    def test_direct_recovery_requires_a_direct_credential(self):
        env = dict(self.env)
        env["FPL_X_API_AUTHORIZATION"] = ""
        env["FPL_SESSION_COOKIE"] = ""
        with self.assertRaises(ops.AuthOpsError):
            ops._direct_recover(
                self.script,
                config=self.config,
                github_output=None,
                github_env=None,
                env=env,
            )

    def test_direct_recovery_disables_refresh_inputs_for_selected_preflight(self):
        seen_env = {}

        def fake_run(*args, **kwargs):
            seen_env.update(kwargs["env"])
            return self.result(0, stdout='{"authenticated": true}\n')

        with mock.patch.object(ops, "_run_frozen_preflight", side_effect=fake_run):
            ops._direct_recover(
                self.script,
                config=self.config,
                github_output=None,
                github_env=None,
                env=self.env,
            )
        self.assertEqual(seen_env["FPL_REFRESH_TOKEN"], "")
        self.assertEqual(seen_env["FPL_REFRESH_WRAP_KEY"], "")
        self.assertEqual(seen_env["FPL_X_API_AUTHORIZATION"], "direct-token")

    def test_refresh_success_writes_auth_mode_and_non_recovery_marker(self):
        module = FakeAuthModule()
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            env_file = Path(tmp) / "env"
            output.touch()
            env_file.touch()
            ops._emit_refresh_success(
                module,
                access_token="masked-access",
                github_output=output,
                github_env=env_file,
                recovery="none",
            )
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("auth_mode=refresh", rendered)
            self.assertIn("auth_recovery=none", rendered)
            self.assertIn(
                "FPL_X_API_AUTHORIZATION=masked-access",
                env_file.read_text(encoding="utf-8"),
            )

    def test_wrapper_suppresses_arbitrary_exception_detail(self):
        rendered = ops._format_wrapper_error(
            RuntimeError("super-secret-token-material")
        )
        self.assertIn("RuntimeError", rendered)
        self.assertNotIn("super-secret-token-material", rendered)
        safe = ops._format_wrapper_error(ops.AuthOpsError("static safe failure"))
        self.assertIn("static safe failure", safe)


class AuthWorkflowBindingTests(unittest.TestCase):
    def test_all_live_refresh_callers_use_authority_selected_core_preflight(self):
        for path in (PRODUCTION_WORKFLOW, KEEPALIVE_WORKFLOW, DRAFT_WORKFLOW):
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                '--preflight-script "$APEX_CORE_PATH/scripts/preflight_fpl_auth.py"',
                text,
                path.name,
            )
            self.assertIn(
                '--config "$APEX_CORE_PATH/config/apex_v2.yaml"',
                text,
                path.name,
            )

    def test_keepalive_and_draft_resolve_machine_authority_not_frozen_auth_code(self):
        for path in (KEEPALIVE_WORKFLOW, DRAFT_WORKFLOW):
            text = path.read_text(encoding="utf-8")
            self.assertIn('authority["production_core_sha"]', text, path.name)
            self.assertIn('authority["frozen_engine_sha"]', text, path.name)
            self.assertIn(FROZEN_SHA, text, path.name)
            self.assertIn(
                'git merge-base --is-ancestor "$FROZEN_ENGINE_SHA" "$PRODUCTION_CORE_SHA"',
                text,
                path.name,
            )
            self.assertIn(
                'git worktree add --detach "$CORE" "$PRODUCTION_CORE_SHA"',
                text,
                path.name,
            )
            self.assertNotIn("ref: ${{ env.FROZEN_APEX_SHA }}", text)

    def test_auth_callers_share_non_cancelling_serialized_concurrency(self):
        for path in (PRODUCTION_WORKFLOW, KEEPALIVE_WORKFLOW, DRAFT_WORKFLOW):
            text = path.read_text(encoding="utf-8")
            self.assertIn("group: apex-v2-fpl-auth", text, path.name)
            self.assertIn("cancel-in-progress: false", text, path.name)

    def test_keepalive_remains_non_serving_and_read_only(self):
        text = KEEPALIVE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("--mode keepalive", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("apex-v2 solve", text)
        self.assertNotIn("apex-v2 publish", text)


if __name__ == "__main__":
    unittest.main()
