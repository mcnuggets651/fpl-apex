from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "apex_v2_draft_auth_relay_ops.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "apex-v2-draft-auth-relay.yml"
spec = importlib.util.spec_from_file_location("draft_relay", MODULE_PATH)
assert spec and spec.loader
relay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(relay)


class FakeClient:
    def __init__(self, responses):
        self.responses = dict(responses)
        self.calls = []
        self.dispatches = []

    def get_json(self, path, headers):
        self.calls.append((path, dict(headers)))
        return self.responses[path]

    def dispatch(self, repository, github_token, payload):
        self.dispatches.append((repository, github_token, payload))
        return 204


DETAILS = {
    "league_entries": [
        {"id": 172997, "entry_id": 172178, "entry_name": "mcnuggets"},
        {"id": 999, "entry_id": 1000, "entry_name": "other"},
    ]
}
BOOTSTRAP = {
    "elements": [
        {"id": 10, "web_name": "Incoming"},
        {"id": 20, "web_name": "Outgoing"},
    ]
}
TRANSACTIONS = {
    "transactions": [
        {
            "id": 7,
            "element_in": 10,
            "element_out": 20,
            "status": "pending",
            "priority": 1,
            "private_note": "must not escape",
        }
    ]
}


class DraftAuthRelayTests(unittest.TestCase):
    def client(self, transaction_status=200, transaction_payload=TRANSACTIONS):
        return FakeClient(
            {
                "league/33160/details": (200, DETAILS),
                "bootstrap-static": (200, BOOTSTRAP),
                "draft/entry/172178/transactions": (
                    transaction_status,
                    transaction_payload if transaction_status == 200 else None,
                ),
            }
        )

    def build(self, client, **overrides):
        kwargs = dict(
            client=client,
            league_id=33160,
            entry_name="mcnuggets",
            token="owner-token",
            cookie="",
            producer_repository="mcnuggets651/fpl-apex",
            producer_run_id="12345",
            producer_sha="a" * 40,
            max_rows=100,
        )
        kwargs.update(overrides)
        return relay.build_relay(**kwargs)

    def test_builds_allowlisted_pending_transaction_snapshot(self):
        client = self.client()
        result = self.build(client)
        self.assertEqual(result["contract"], relay.CONTRACT)
        self.assertEqual(result["entry"]["team_entry_id"], 172178)
        rows = result["entry_transactions"]["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[0]["element_in_name"], "Incoming")
        self.assertEqual(rows[0]["element_out_name"], "Outgoing")
        self.assertNotIn("private_note", rows[0])
        self.assertNotIn("owner-token", repr(result))

    def test_authenticated_endpoint_uses_bearer_transport(self):
        client = self.client()
        self.build(client)
        path, headers = client.calls[-1]
        self.assertEqual(path, "draft/entry/172178/transactions")
        self.assertEqual(headers["X-API-Authorization"], "Bearer owner-token")

    def test_cookie_transport_is_supported_without_exposing_cookie(self):
        client = self.client()
        result = self.build(client, token="", cookie="session=abc")
        self.assertEqual(result["entry_transactions"]["auth_mode"], "cookie")
        self.assertNotIn("session=abc", repr(result))

    def test_rejects_missing_owner_transport(self):
        with self.assertRaises(relay.DraftRelayError):
            self.build(self.client(), token="", cookie="")

    def test_rejects_auth_failure(self):
        with self.assertRaises(relay.DraftRelayError):
            self.build(self.client(transaction_status=403))

    def test_rejects_missing_endpoint(self):
        with self.assertRaises(relay.DraftRelayError):
            self.build(self.client(transaction_status=404))

    def test_rejects_wrong_producer(self):
        with self.assertRaises(relay.DraftRelayError):
            self.build(self.client(), producer_repository="evil/example")

    def test_rejects_ambiguous_entry(self):
        details = {
            "league_entries": [
                {"entry_id": 1, "entry_name": "mcnuggets"},
                {"entry_id": 2, "entry_name": "mcnuggets"},
            ]
        }
        client = self.client()
        client.responses["league/33160/details"] = (200, details)
        with self.assertRaises(relay.DraftRelayError):
            self.build(client)

    def test_rejects_sensitive_key_if_future_code_adds_one(self):
        with self.assertRaises(relay.DraftRelayError):
            relay._reject_sensitive_keys({"access_token": "x"})

    def test_dispatch_payload_limit_is_bounded(self):
        self.assertLess(relay.MAX_DISPATCH_BYTES, 65536)
        self.assertEqual(relay.MAX_ROWS, 100)

    def test_workflow_reuses_serialized_auth_boundary_and_has_no_public_artifact(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("group: apex-v2-fpl-auth", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("permissions:\n  contents: read", text)
        self.assertIn("--mode production", text)
        self.assertIn("--github-env \"$GITHUB_ENV\"", text)
        self.assertIn("APEX_V2_PRIVATE_REPO_TOKEN", text)
        self.assertNotIn("actions/upload-artifact", text)
        self.assertNotIn("contents: write", text)

    def test_workflow_keeps_frozen_auth_worktree_and_current_controller_separate(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn('FROZEN_APEX_SHA: "99cc7b51b0cff45462b567084cb1844cfe0a456f"', text)
        self.assertIn("scripts/apex_v2_auth_ops.py", text)
        self.assertIn("scripts/apex_v2_draft_auth_relay_ops.py", text)
        self.assertIn("git show \"$CONTROL_PLANE_SHA:scripts/apex_v2_auth_ops.py\"", text)
        self.assertIn("test \"$(git rev-parse HEAD)\" = \"$FROZEN_APEX_SHA\"", text)

    def test_workflow_is_read_only_against_draft_and_dispatches_only_privately(self):
        text = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn("--league-id 33160", text)
        self.assertIn("--entry-name mcnuggets", text)
        self.assertIn("--private-repository \"$APEX_PRIVATE_GITHUB_REPOSITORY\"", text)
        self.assertNotIn("/waiver", text.casefold())
        self.assertNotIn("method: post", text.casefold())


if __name__ == "__main__":
    unittest.main()
