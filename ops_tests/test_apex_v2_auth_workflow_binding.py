from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRODUCTION = ROOT / ".github" / "workflows" / "apex-v2-daily-production.yml"
KEEPALIVE = ROOT / ".github" / "workflows" / "apex-v2-auth-keepalive.yml"
DRAFT = ROOT / ".github" / "workflows" / "apex-v2-draft-auth-relay.yml"
FROZEN = "99cc7b51b0cff45462b567084cb1844cfe0a456f"


class AuthWorkflowBindingTests(unittest.TestCase):
    def test_all_live_refresh_callers_use_authority_selected_core_preflight(self):
        for path in (PRODUCTION, KEEPALIVE, DRAFT):
            text = path.read_text(encoding="utf-8")
            self.assertIn(
                '--preflight-script "$APEX_CORE_PATH/scripts/preflight_fpl_auth.py"',
                text,
                path.name,
            )
            self.assertIn(
                '--config "$APEX_CORE_PATH/config/apex_v2.yaml"',
                text,
                path.name,
            )

    def test_keepalive_and_draft_resolve_machine_authority_not_frozen_auth_code(self):
        for path in (KEEPALIVE, DRAFT):
            text = path.read_text(encoding="utf-8")
            self.assertIn('authority["production_core_sha"]', text, path.name)
            self.assertIn('authority["frozen_engine_sha"]', text, path.name)
            self.assertIn(FROZEN, text, path.name)
            self.assertIn(
                'git merge-base --is-ancestor "$FROZEN_ENGINE_SHA" "$PRODUCTION_CORE_SHA"',
                text,
                path.name,
            )
            self.assertIn('git worktree add --detach "$CORE" "$PRODUCTION_CORE_SHA"', text)
            self.assertNotIn("ref: ${{ env.FROZEN_APEX_SHA }}", text)

    def test_auth_callers_share_non_cancelling_serialized_concurrency(self):
        for path in (PRODUCTION, KEEPALIVE, DRAFT):
            text = path.read_text(encoding="utf-8")
            self.assertIn("group: apex-v2-fpl-auth", text, path.name)
            self.assertIn("cancel-in-progress: false", text, path.name)

    def test_keepalive_remains_non_serving_and_read_only(self):
        text = KEEPALIVE.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("--mode keepalive", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("apex-v2 solve", text)
        self.assertNotIn("apex-v2 publish", text)


if __name__ == "__main__":
    unittest.main()
