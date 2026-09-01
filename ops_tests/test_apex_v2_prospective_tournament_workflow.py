from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.text = (
            ROOT / ".github/workflows/apex-v2-prospective-tournament.yml"
        ).read_text(encoding="utf-8")

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
        for needle in (
            "seal-run",
            "retain-gw2",
            "canonicalize",
            "evaluate",
            "status",
        ):
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

    def test_hourly_maintenance_is_ordered_and_non_cancelling(self):
        self.assertIn('cron: "23 * * * *"', self.text)
        self.assertIn("cancel-in-progress: false", self.text)
        self.assertIn("  maintenance:\n    needs: seal\n    if: >-\n      always()", self.text)

    def test_relevant_main_ops_push_bootstraps_without_running_production(self):
        for needle in (
            "\n  push:\n",
            "      - main",
            '      - ".github/workflows/apex-v2-prospective-tournament.yml"',
            '      - "scripts/apex_v2_tournament_ops.py"',
            '      - "scripts/apex_v2_shadow_provider_ops.py"',
            "github.event_name == 'push'",
            "EARLIEST_FUTURE_DEADLINE_THEN_LATEST_VALID_FROZEN_AT",
            '"status": "NO_ELIGIBLE_SOURCE"',
            'echo "has_source=false"',
            "steps.source.outputs.has_source == 'true'",
        ):
            self.assertIn(needle, self.text)

    def test_legacy_final_without_modern_asset_is_rejected_not_fatal(self):
        for needle in (
            'MISSING_PUBLIC_ATTEMPT_ASSET = "MISSING_PUBLIC_ATTEMPT_ASSET"',
            'if "public_attempt.json" not in asset_names:',
            "except FileNotFoundError:",
            "Legacy releases and a release-list/asset-read race are ineligible",
            'reject(rejections, tag, MISSING_PUBLIC_ATTEMPT_ASSET)',
            '"rejection_counts": rejection_counts',
            '"rejections": rejections',
            '"examined_final_release_count": examined',
        ):
            self.assertIn(needle, self.text)

    def test_modern_authority_corruption_still_fails_closed(self):
        for needle in (
            "final release run identity mismatch",
            "final release season mismatch",
            "invalid final authority fields",
            "frozen_at >= deadline or now >= deadline",
            'get("personalized_actionable") is not True',
            '!= "airsenal" for h in range(1, 9)',
            "serving authority drift in immutable final",
        ):
            self.assertIn(needle, self.text)

    def test_source_resolution_is_persisted_before_sealing(self):
        for needle in (
            "Upload source-resolution proof",
            "apex-v2-tournament-source-${{ github.run_id }}",
            "steps.source.conclusion == 'success'",
            "EXACT_PRODUCTION_WORKFLOW_RUN",
            "EXACT_MANUAL_RUN_ID",
            "RESOLVED_IMMUTABLE_FINAL",
            "source_resolution.json",
            "retention-days: 90",
        ):
            self.assertIn(needle, self.text)


if __name__ == "__main__":
    unittest.main()
