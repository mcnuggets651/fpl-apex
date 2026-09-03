from pathlib import Path
import unittest

FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"
ROOT = Path(__file__).parents[1]


class ShadowProviderWorkflowTests(unittest.TestCase):
    def test_production_keeps_immutable_base_serving_core_and_resilient_dastan(self):
        text = (ROOT / ".github/workflows/apex-v2-daily-production.yml").read_text(encoding="utf-8")
        for needle in (
            f'FROZEN_APEX_BASE_SHA: "{FROZEN}"',
            'authority["production_core_sha"]',
            'authority["frozen_engine_sha"]',
            'git merge-base --is-ancestor "$FROZEN_ENGINE_SHA" "$PRODUCTION_CORE_SHA"',
            'git worktree add --detach "$CORE" "$PRODUCTION_CORE_SHA"',
            'echo "APEX_CODE_SHA=$PRODUCTION_CORE_SHA" >> "$GITHUB_ENV"',
            'cp "$APEX_CORE_PATH/upstreams.lock.json" "$RUNNER_TEMP/apex-v2-upstreams.lock.json"',
            '--source "$APEX_CORE_PATH/config/apex_v2.yaml"',
            '--output "$RUNNER_TEMP/apex_v2_runtime.yaml"',
            '--config "$RUNNER_TEMP/apex_v2_runtime.yaml"',
            'Acquire Dastan H1 shadow with bounded transient retry',
            'dastan-run',
            '--runner "$APEX_CORE_PATH/scripts/acquire_dastan_shadow.py"',
            '--max-attempts 2',
            '--wall-clock-seconds 900',
            'Generate fresh AIrsenal candidate',
            '"$APEX_CORE_PATH/scripts/run_airsenal_worker.py"',
            '"$APEX_CORE_PATH/scripts/check_v2_architecture.py"',
            'apex-v2 solve',
            'apex-v2 publish',
        ):
            self.assertIn(needle, text)
        self.assertNotIn(f'APEX_CODE_SHA: "{FROZEN}"', text)
        self.assertNotIn('ref: ${{ env.APEX_CODE_SHA }}', text)

    def test_external_health_workflow_has_no_serving_or_manager_authority(self):
        text = (ROOT / ".github/workflows/apex-v2-shadow-health.yml").read_text(encoding="utf-8")
        for forbidden in (
            "FPL_SESSION_COOKIE",
            "FPL_X_API_AUTHORIZATION",
            "FPL_REFRESH_TOKEN",
            "apex-v2 solve",
            "apex-v2 publish",
            "APEX_PRIVATE_GITHUB_TOKEN",
            "contents: write",
        ):
            self.assertNotIn(forbidden, text)
        for needle in (
            "contents: read",
            f'FROZEN_APEX_SHA: "{FROZEN}"',
            'git show "$FROZEN_APEX_SHA:upstreams.lock.json"',
            'git show "$FROZEN_APEX_SHA:config/openfpl_training_policy.yaml"',
            "dastan-pin-health",
            "pitchside-health",
            "openfpl-readiness",
            '--history-ref master',
        ):
            self.assertIn(needle, text)

    def test_external_health_runs_after_relevant_main_ops_merges(self):
        text = (ROOT / ".github/workflows/apex-v2-shadow-health.yml").read_text(encoding="utf-8")
        for needle in (
            "\n  push:\n",
            "      - main",
            '      - ".github/workflows/apex-v2-shadow-health.yml"',
            '      - "scripts/apex_v2_shadow_provider_ops.py"',
        ):
            self.assertIn(needle, text)
        self.assertNotIn(".github/workflows/apex-v2-daily-production.yml", text)


if __name__ == "__main__":
    unittest.main()
