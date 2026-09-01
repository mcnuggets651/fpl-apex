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

    def test_shadow_health_runs_after_shadow_ops_changes(self) -> None:
        text = _workflow("apex-v2-shadow-health.yml")
        for required in (
            FROZEN,
            "\n  push:\n",
            "      - main",
            '      - ".github/workflows/apex-v2-shadow-health.yml"',
            '      - "scripts/apex_v2_shadow_provider_ops.py"',
            "contents: read",
            "dastan-pin-health",
            "pitchside-health",
            "openfpl-readiness",
        ):
            self.assertIn(required, text)

    def test_tournament_runs_post_ops_bootstrap_without_production(self) -> None:
        text = _workflow("apex-v2-prospective-tournament.yml")
        for required in (
            FROZEN,
            "\n  push:\n",
            "      - main",
            '      - ".github/workflows/apex-v2-prospective-tournament.yml"',
            '      - "scripts/apex_v2_tournament_ops.py"',
            "EARLIEST_FUTURE_DEADLINE_THEN_LATEST_VALID_FROZEN_AT",
            "NO_ELIGIBLE_SOURCE",
            "seal-run",
            "needs: seal",
            "cancel-in-progress: false",
        ):
            self.assertIn(required, text)
        for forbidden in (
            "FPL_SESSION_COOKIE",
            "FPL_X_API_AUTHORIZATION",
            "FPL_REFRESH_TOKEN",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
        ):
            self.assertNotIn(forbidden, text)

    def test_post_ops_acceptance_never_runs_production(self) -> None:
        production = _workflow("apex-v2-daily-production.yml")
        self.assertNotIn("\n  push:\n", production)
        self.assertIn('cron: "17 4 * * *"', production)
        self.assertIn(FROZEN, production)


if __name__ == "__main__":
    unittest.main()
