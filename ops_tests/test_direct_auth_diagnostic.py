from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "apex-v2-direct-auth-diagnostic.yml"
FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


class DirectAuthDiagnosticTests(unittest.TestCase):
    def test_is_incident_only_frozen_manual_and_non_serving(self) -> None:
        text = WORKFLOW.read_text(encoding="utf-8")
        for required in (
            FROZEN,
            "workflow_dispatch:",
            "if: github.ref == 'refs/heads/main'",
            "permissions:\n  contents: read",
            "FPL_X_API_AUTHORIZATION",
            "FPL_SESSION_COOKIE",
            'FPL_REFRESH_TOKEN: ""',
            'FPL_REFRESH_WRAP_KEY: ""',
            "python scripts/preflight_fpl_auth.py --config config/apex_v2.yaml",
        ):
            self.assertIn(required, text)

        for forbidden in (
            "\n  push:\n",
            "\n  schedule:\n",
            "\n  workflow_run:\n",
            "cron:",
            "contents: write",
            "APEX_PRIVATE_GITHUB",
            "apex-v2 intent",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
            "apex-v2 official-hash",
            "airsenal",
            "acquire_dastan",
        ):
            self.assertNotIn(forbidden, text)

    def test_daily_production_remains_without_push_trigger(self) -> None:
        text = (ROOT / ".github" / "workflows" / "apex-v2-daily-production.yml").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("\n  push:\n", text)
        self.assertIn(FROZEN, text)


if __name__ == "__main__":
    unittest.main()
