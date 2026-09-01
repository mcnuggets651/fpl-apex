from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = (ROOT / ".github/workflows/apex-v2-prospective-tournament.yml").read_text(encoding="utf-8")

    def test_source_and_frozen_contract(self):
        for needle in (
            'workflows: ["Apex V2 Daily Production"]',
            FROZEN,
            'ref: ${{ env.FROZEN_APEX_SHA }}',
            'apex_v2_tournament_common.py apex_v2_tournament_contract.py apex_v2_tournament_scoring.py apex_v2_tournament_ops.py',
            'git show "$CONTROL_PLANE_SHA:scripts/$name"',
            'git show "$FROZEN_APEX_SHA:upstreams.lock.json"',
            'git show "$FROZEN_APEX_SHA:config/openfpl_training_policy.yaml"',
        ):
            self.assertIn(needle, self.text)

    def test_tournament_commands_complete_lifecycle(self):
        for needle in ("seal-run", "retain-gw2", "canonicalize", "evaluate", "status"):
            self.assertIn(needle, self.text)

    def test_no_serving_or_manager_auth_authority(self):
        forbidden = (
            "FPL_SESSION_COOKIE",
            "FPL_X_API_AUTHORIZATION",
            "FPL_REFRESH_TOKEN",
            "FPL_REFRESH_WRAP_KEY",
            "apex-v2 solve",
            "apex-v2 publish",
            "acquire_dastan",
            "run_airsenal_worker",
            "workflow_dispatch production",
        )
        for needle in forbidden:
            self.assertNotIn(needle, self.text)
        self.assertIn("APEX_PRIVATE_GITHUB_TOKEN", self.text)
        self.assertIn("contents: write", self.text)

    def test_hourly_maintenance_and_non_cancelling(self):
        self.assertIn('cron: "23 * * * *"', self.text)
        self.assertIn("cancel-in-progress: false", self.text)


if __name__ == "__main__":
    unittest.main()
