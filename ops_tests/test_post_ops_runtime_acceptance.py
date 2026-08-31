from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


def _workflow(name: str) -> str:
    return (ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


class PostOpsRuntimeAcceptanceTests(unittest.TestCase):
    def test_auth_keepalive_runs_after_auth_ops_changes(self) -> None:
        text = _workflow("apex-v2-auth-keepalive.yml")
        for required in (
            FROZEN,
            "\n  push:\n",
            "      - main",
            '      - ".github/workflows/apex-v2-auth-keepalive.yml"',
            '      - ".github/workflows/apex-v2-daily-production.yml"',
            '      - "scripts/apex_v2_auth_ops.py"',
            'cron: "22 */6 * * *"',
            "group: apex-v2-fpl-auth",
            "cancel-in-progress: false",
            "--mode keepalive",
        ):
            self.assertIn(required, text)

        for forbidden in (
            "FPL_X_API_AUTHORIZATION",
            "FPL_SESSION_COOKIE",
            "apex-v2 intent",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
        ):
            self.assertNotIn(forbidden, text)

    def test_evaluation_runs_after_evaluation_ops_changes(self) -> None:
        text = _workflow("apex-v2-daily-evaluation.yml")
        for required in (
            FROZEN,
            "\n  push:\n",
            "      - main",
            '      - ".github/workflows/apex-v2-daily-evaluation.yml"',
            '      - "scripts/apex_v2_attempt_audit_ops.py"',
            'cron: "41 6 * * *"',
            "group: apex-v2-evaluation",
            "cancel-in-progress: false",
            "apex_v2_attempt_audit_ops.py",
            "apex-v2 private-store-preflight",
            "apex-v2 evaluate-completed",
            "apex-v2 tournament-standings",
        ):
            self.assertIn(required, text)

    def test_post_ops_acceptance_never_runs_production(self) -> None:
        production = _workflow("apex-v2-daily-production.yml")
        self.assertNotIn("\n  push:\n", production)
        self.assertIn('cron: "17 4 * * *"', production)
        self.assertIn(FROZEN, production)


if __name__ == "__main__":
    unittest.main()
