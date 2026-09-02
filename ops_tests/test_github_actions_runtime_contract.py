from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
DEPENDABOT = ROOT / ".github" / "dependabot.yml"
DIRECT_AUTH = WORKFLOW_DIR / "apex-v2-direct-auth-diagnostic.yml"

ACTION_PINS = {
    "actions/checkout": ("3d3c42e5aac5ba805825da76410c181273ba90b1", "v7.0.1"),
    "actions/setup-python": ("5fda3b95a4ea91299a34e894583c3862153e4b97", "v7.0.0"),
    "actions/cache": ("55cc8345863c7cc4c66a329aec7e433d2d1c52a9", "v6.1.0"),
    "actions/upload-artifact": ("043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", "v7.0.1"),
}
USE_RE = re.compile(
    r"^\s*-?\s*uses:\s*(actions/[A-Za-z0-9_.-]+)@([0-9a-f]{40})\s+#\s+(v[^\s]+)\s*$"
)


class GitHubActionsRuntimeContractTests(unittest.TestCase):
    def _active_workflows(self) -> list[Path]:
        return sorted([*WORKFLOW_DIR.glob("*.yml"), *WORKFLOW_DIR.glob("*.yaml")])

    def test_all_github_owned_actions_are_exact_node24_release_pins(self) -> None:
        seen: set[str] = set()
        for path in self._active_workflows():
            for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if "uses: actions/" not in line:
                    continue
                match = USE_RE.match(line)
                self.assertIsNotNone(
                    match,
                    f"{path.relative_to(ROOT)}:{lineno} must pin a GitHub-owned action to a full commit SHA with version comment",
                )
                action, sha, version = match.groups()
                self.assertIn(
                    action,
                    ACTION_PINS,
                    f"{path.relative_to(ROOT)}:{lineno} introduces an ungoverned GitHub-owned action: {action}",
                )
                expected_sha, expected_version = ACTION_PINS[action]
                self.assertEqual(sha, expected_sha, f"{action} is not on the certified Node-24 pin")
                self.assertEqual(version, expected_version, f"{action} version comment drifted from its certified pin")
                seen.add(action)

        self.assertEqual(seen, set(ACTION_PINS), "expected active GitHub Actions are missing from the executable workflow set")

    def test_deprecated_mutable_major_refs_are_absent_from_active_workflows(self) -> None:
        active = "\n".join(path.read_text(encoding="utf-8") for path in self._active_workflows())
        for forbidden in (
            "actions/checkout@v4",
            "actions/setup-python@v5",
            "actions/cache@v4",
            "actions/upload-artifact@v4",
        ):
            self.assertNotIn(forbidden, active)

    def test_dependabot_keeps_github_actions_updates_on_the_pr_path(self) -> None:
        payload = yaml.safe_load(DEPENDABOT.read_text(encoding="utf-8"))
        self.assertEqual(payload.get("version"), 2)
        updates = payload.get("updates") or []
        action_updates = [row for row in updates if row.get("package-ecosystem") == "github-actions"]
        self.assertEqual(len(action_updates), 1)
        config = action_updates[0]
        self.assertEqual(config.get("directory"), "/")
        self.assertEqual((config.get("schedule") or {}).get("interval"), "weekly")
        self.assertEqual((config.get("schedule") or {}).get("timezone"), "Europe/London")
        self.assertGreaterEqual(int(config.get("open-pull-requests-limit", 0)), 1)

    def test_direct_auth_diagnostic_is_manual_only_and_non_serving(self) -> None:
        body = DIRECT_AUTH.read_text(encoding="utf-8")
        payload = yaml.load(body, Loader=yaml.BaseLoader)
        triggers = payload.get("on")
        self.assertIsInstance(triggers, dict)
        self.assertEqual(set(triggers), {"workflow_dispatch"})

        job = (payload.get("jobs") or {}).get("verify-direct-owner-auth") or {}
        self.assertEqual(job.get("if"), "github.ref == 'refs/heads/main'")
        self.assertIn("FPL_X_API_AUTHORIZATION: ${{ secrets.FPL_X_API_AUTHORIZATION }}", body)
        self.assertIn('FPL_REFRESH_TOKEN: ""', body)
        self.assertIn('FPL_REFRESH_WRAP_KEY: ""', body)
        for forbidden in (
            "\n  push:",
            "\n  schedule:",
            "\n  workflow_run:",
            "contents: write",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
        ):
            self.assertNotIn(forbidden, body)


if __name__ == "__main__":
    unittest.main()
