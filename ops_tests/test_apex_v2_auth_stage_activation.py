from __future__ import annotations

import unittest

from ops_tests.test_apex_v2_auth_ops import (
    FakeAuthModule,
    FakeFernet,
    FakeStore,
    ops,
)


class EventuallyConsistentDraftListStore(FakeStore):
    """Model a GitHub draft that exists by ID before list_releases sees it."""

    def list_releases(self, per_page=100):
        return list(self.published)


class SameRunStageActivationTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "FPL_REFRESH_TOKEN": "bootstrap",
            "FPL_REFRESH_WRAP_KEY": "wrap",
            "APEX_PRIVATE_GITHUB_REPOSITORY": "owner/private",
            "APEX_PRIVATE_GITHUB_TOKEN": "private-token",
            "FPL_X_API_AUTHORIZATION": "",
            "FPL_SESSION_COOKIE": "",
        }

    def test_owner_match_activates_exact_created_draft_without_relisting(self):
        events: list[str] = []
        store = EventuallyConsistentDraftListStore(events)
        module = FakeAuthModule(store, events)
        module.exchange_results = [("access", "child")]
        module.verify_results = ["match"]

        access, child = ops._rotate_refresh_parent(
            module,
            entry_id=63984,
            store=store,
            fernet=FakeFernet(),
            parent_refresh_token="parent",
            env=self.env,
        )

        self.assertEqual((access, child), ("access", "child"))
        self.assertEqual(events[:4], ["exchange", "stage", "verify", "publish"])
        self.assertEqual(len(store.published), 1)
        self.assertFalse(store.drafts)

    def test_wrong_manager_purges_exact_created_draft_without_relisting(self):
        events: list[str] = []
        store = EventuallyConsistentDraftListStore(events)
        module = FakeAuthModule(store, events)
        module.exchange_results = [("access", "wrong-owner-child")]
        module.verify_results = ["wrong_manager"]

        with self.assertRaises(ops.AuthOpsError):
            ops._rotate_refresh_parent(
                module,
                entry_id=63984,
                store=store,
                fernet=FakeFernet(),
                parent_refresh_token="parent",
                env=self.env,
            )

        self.assertEqual(events, ["exchange", "stage", "verify", "cleanup"])
        self.assertFalse(store.drafts)
        self.assertFalse(store.published)


if __name__ == "__main__":
    unittest.main()
