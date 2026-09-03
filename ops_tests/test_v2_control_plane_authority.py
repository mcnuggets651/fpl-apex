from __future__ import annotations

import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class V2ControlPlaneAuthorityTests(unittest.TestCase):
    def test_required_ci_has_no_legacy_runtime_authority(self):
        text = (ROOT / ".github/workflows/apex.yml").read_text(encoding="utf-8")
        for forbidden in (
            "apex_fpl",
            "apex-fpl",
            "scripts/run_apex.py",
            "run_pinnacle.py",
            "apex_recommendation_latest",
            "pinnacle_latest",
            "elite_latest",
        ):
            self.assertNotIn(forbidden, text)
        for required in (
            "docs/APEX_V2_AUTHORITY.json",
            "git worktree add --detach",
            "ops_tests",
            "check_v2_architecture.py",
            "tests/test_apex_v2_*.py",
            "tests/test_v2_*.py",
        ):
            self.assertIn(required, text)

    def test_manual_readiness_is_read_only_v2_candidate_rehearsal(self):
        text = (ROOT / ".github/workflows/production-readiness.yml").read_text(encoding="utf-8")
        for forbidden in (
            "run_apex.py",
            "run_pinnacle.py",
            "apex_recommendation_latest",
            "pinnacle_latest",
            "elite_latest",
            "ODDS_API_KEY",
            "ODDS_API_URL",
            "APEX_NEWS_FEEDS",
            "contents: write",
            "secrets.",
        ):
            self.assertNotIn(forbidden, text)
        for required in (
            "workflow_dispatch:",
            "candidate_sha:",
            "docs/APEX_V2_AUTHORITY.json",
            "git worktree add --detach",
            "check_v2_architecture.py",
            "check_v2_critical_coverage.py",
            "run_v2_mutation_sentinels.py",
            "mode=non-serving-candidate",
            "contents: read",
        ):
            self.assertIn(required, text)
        self.assertNotIn("schedule:", text)
        self.assertNotIn("push:\n", text)

    def test_authority_keeps_legacy_nonserving_and_one_v2_publisher(self):
        authority = json.loads(
            (ROOT / "docs/APEX_V2_AUTHORITY.json").read_text(encoding="utf-8")
        )
        self.assertEqual(authority["legacy"]["status"], "HISTORICAL_NON_SERVING")
        self.assertEqual(
            authority["production"]["serving_workflow"],
            ".github/workflows/apex-v2-daily-production.yml",
        )
        self.assertEqual(authority["production"]["serving_provider"], "airsenal")
        self.assertFalse(authority["model_authority"]["automatic_promotion"])


if __name__ == "__main__":
    unittest.main()
