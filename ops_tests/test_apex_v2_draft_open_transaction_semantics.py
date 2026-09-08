from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "apex-v2-draft-auth-relay.yml"


class DraftOpenTransactionSemanticProbeTests(unittest.TestCase):
    def setUp(self):
        self.text = WORKFLOW.read_text(encoding="utf-8")
        marker = "- name: Inspect Official Draft open-transaction semantics read-only"
        self.assertIn(marker, self.text)
        self.block = self.text.split(marker, 1)[1].split(
            "- name: Diagnose Official FPL owner endpoint status after auth failure", 1
        )[0]

    def test_probe_is_get_only_and_emits_schema_or_counts_not_bodies(self):
        self.assertIn("requests.get", self.block)
        self.assertNotIn("requests.post", self.block)
        self.assertNotIn("requests.put", self.block)
        self.assertNotIn("requests.patch", self.block)
        self.assertNotIn("requests.delete", self.block)
        self.assertIn('"body_values_emitted": False', self.block)
        self.assertIn("schema_only", self.block)
        self.assertIn('"sample_fields": sorted(fields)', self.block)
        self.assertNotIn("response.text", self.block)
        self.assertNotIn("response.content", self.block)

    def test_probe_covers_cycle_dynamic_and_owner_transaction_surfaces(self):
        self.assertIn('fetch("game", common)', self.block)
        self.assertIn('fetch("bootstrap-dynamic", auth)', self.block)
        self.assertIn('fetch(f"draft/entry/{team_entry_id}/transactions", auth)', self.block)
        self.assertIn('"waivers_processed"', self.block)
        self.assertIn('"processing_status"', self.block)
        self.assertIn('"current_event"', self.block)
        self.assertIn('"next_event"', self.block)
        self.assertIn('"unresolved_count": unresolved', self.block)
        self.assertIn('"resolved_count": resolved', self.block)

    def test_probe_reuses_certified_runtime_auth_without_recovery_or_secret_duplication(self):
        self.assertIn('os.environ.get("FPL_X_API_AUTHORIZATION", "")', self.block)
        self.assertIn('os.environ.get("FPL_SESSION_COOKIE", "")', self.block)
        self.assertNotIn("FPL_REFRESH_TOKEN", self.block)
        self.assertNotIn("FPL_REFRESH_WRAP_KEY", self.block)
        self.assertNotIn("APEX_PRIVATE_GITHUB_TOKEN", self.block)
        self.assertNotIn("--mode production", self.block)

    def test_probe_resolves_entry_live_and_never_hardcodes_team_entry_id(self):
        self.assertIn('fetch("league/33160/details", common)', self.block)
        self.assertIn('!= "mcnuggets"', self.block)
        self.assertNotIn("172178", self.block)


if __name__ == "__main__":
    unittest.main()
