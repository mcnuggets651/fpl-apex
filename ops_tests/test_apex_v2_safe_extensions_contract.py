from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


class SafeExtensionWorkflowContractTests(unittest.TestCase):
    def text(self, path: str) -> str:
        return (ROOT / path).read_text(encoding="utf-8")

    def test_deadline_watcher_is_lightweight_deduplicated_and_non_serving(self):
        text = self.text(".github/workflows/apex-v2-deadline-watch.yml")
        for needle in (
            'cron: "11,41 * * * *"',
            "actions: write",
            "group: apex-v2-deadline-watch",
            FROZEN,
            "apex_v2_deadline_ops.py",
            "--min-minutes 90",
            "--max-minutes 150",
        ):
            self.assertIn(needle, text)
        for forbidden in (
            "FPL_REFRESH_TOKEN",
            "FPL_X_API_AUTHORIZATION",
            "APEX_PRIVATE_GITHUB_TOKEN",
            "apex-v2 intent",
            "apex-v2 official-hash",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
            "airsenal",
            "acquire_dastan",
            "contents: write",
        ):
            self.assertNotIn(forbidden, text)

    def test_canonical_production_workflow_is_not_modified_for_deadline_logic(self):
        text = self.text(".github/workflows/apex-v2-daily-production.yml")
        self.assertIn('cron: "17 4 * * *"', text)
        self.assertIn(FROZEN, text)
        self.assertIn("group: apex-v2-fpl-auth", text)
        self.assertNotIn("apex_v2_deadline_ops.py", text)
        self.assertNotIn("deadline-window", text)
        self.assertNotIn("\n  push:\n", text)

    def test_owner_brief_is_private_read_only_and_post_production(self):
        text = self.text(".github/workflows/apex-v2-owner-brief.yml")
        for needle in (
            '"Apex V2 Daily Production"',
            "contents: read",
            FROZEN,
            "apex_v2_owner_brief_ops.py",
            "APEX_V2_PRIVATE_REPO_TOKEN",
            "apex-v2 private-store-preflight",
        ):
            self.assertIn(needle, text)
        for forbidden in (
            "schedule:",
            "cron:",
            "contents: write",
            "apex-v2 intent",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
            "airsenal",
            "acquire_dastan",
        ):
            self.assertNotIn(forbidden, text)

    def test_decision_quality_is_post_evaluation_non_serving_and_private(self):
        text = self.text(".github/workflows/apex-v2-decision-quality.yml")
        for needle in (
            '"Apex V2 Daily Evaluation"',
            "contents: read",
            FROZEN,
            "apex_v2_decision_quality_ops.py",
            "APEX_V2_PRIVATE_REPO_TOKEN",
            "apex-v2 private-store-preflight",
        ):
            self.assertIn(needle, text)
        for forbidden in (
            "schedule:",
            "cron:",
            "contents: write",
            "apex-v2 intent",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
            "airsenal",
            "acquire_dastan",
        ):
            self.assertNotIn(forbidden, text)

    def test_new_controllers_contain_explicit_non_serving_contracts(self):
        owner = self.text("scripts/apex_v2_owner_brief_ops.py")
        dq = self.text("scripts/apex_v2_decision_quality_ops.py")
        deadline = self.text("scripts/apex_v2_deadline_ops.py")
        self.assertIn('"production_influence": "NONE"', owner)
        self.assertIn('"serving_authorized": False', owner)
        self.assertIn('"production_influence": "NONE"', dq)
        self.assertIn('"serving_authorized": False', dq)
        self.assertIn('"promotion_authority": False', dq)
        self.assertIn("SKIPPED_ALREADY_RECORDED", deadline)
        self.assertIn('payload={"ref": "main"}', deadline)


if __name__ == "__main__":
    unittest.main()
