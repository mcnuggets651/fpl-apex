from __future__ import annotations

import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "apex_v2_auth_ops.py"
    spec = importlib.util.spec_from_file_location("apex_v2_auth_ops", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ops = _load_module()


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

    def test_primary_success_never_enters_recovery(self):
        primary = self.result(0, stdout='{"authenticated": true}\n')
        with (
            mock.patch.object(ops, "_run_frozen_preflight", return_value=primary),
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
        self.assertEqual(outcome, "primary")
        bootstrap.assert_not_called()
        direct.assert_not_called()

    def test_non_refresh_failure_is_never_recovered(self):
        primary = self.result(1, stderr="wrong manager")
        with (
            mock.patch.object(ops, "_run_frozen_preflight", return_value=primary),
            mock.patch.object(ops, "_bootstrap_recover") as bootstrap,
            mock.patch.object(ops, "_direct_recover") as direct,
        ):
            with self.assertRaises(ops.AuthOpsError):
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

    def test_refresh_rejection_prefers_bootstrap_recovery(self):
        primary = self.result(1, stderr=ops.REFRESH_REJECTION)
        with (
            mock.patch.object(ops, "_run_frozen_preflight", return_value=primary),
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

    def test_production_can_use_direct_auth_only_after_both_refresh_paths_reject(self):
        primary = self.result(1, stderr=ops.REFRESH_REJECTION)
        with (
            mock.patch.object(ops, "_run_frozen_preflight", return_value=primary),
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
        primary = self.result(1, stderr=ops.REFRESH_REJECTION)
        with (
            mock.patch.object(ops, "_run_frozen_preflight", return_value=primary),
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

    def test_bootstrap_persistence_or_identity_error_is_not_masked_by_direct_auth(self):
        primary = self.result(1, stderr=ops.REFRESH_REJECTION)
        with (
            mock.patch.object(ops, "_run_frozen_preflight", return_value=primary),
            mock.patch.object(
                ops,
                "_bootstrap_recover",
                side_effect=RuntimeError("persist failed"),
            ),
            mock.patch.object(ops, "_direct_recover") as direct,
        ):
            with self.assertRaisesRegex(RuntimeError, "persist failed"):
                ops.authenticate(
                    mode="production",
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

    def test_direct_recovery_disables_refresh_inputs_for_frozen_preflight(self):
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

    def test_refresh_rejection_match_is_exactly_the_frozen_diagnostic(self):
        self.assertTrue(
            ops._is_refresh_rejection(self.result(1, stderr=ops.REFRESH_REJECTION))
        )
        self.assertFalse(
            ops._is_refresh_rejection(
                self.result(1, stderr="Official FPL owner credential belongs to a different manager entry")
            )
        )

    def test_primary_success_writes_non_recovery_marker(self):
        primary = self.result(0, stdout='{"authenticated": true}\n')
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "output"
            output.touch()
            with mock.patch.object(ops, "_run_frozen_preflight", return_value=primary):
                ops.authenticate(
                    mode="production",
                    preflight_script=self.script,
                    config=self.config,
                    github_output=output,
                    github_env=None,
                    env=self.env,
                )
            self.assertIn("auth_recovery=none", output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
