from __future__ import annotations

import copy
import unittest

from scripts.apex_v2_owner_brief_ops import build_owner_brief, render_markdown


PLAYERS = [
    {"element_id": 1, "web_name": "Keeper", "position": "GK", "team_id": 1, "price_tenths": 50},
    {"element_id": 2, "web_name": "Captain", "position": "FWD", "team_id": 2, "price_tenths": 140},
    {"element_id": 3, "web_name": "Vice", "position": "MID", "team_id": 3, "price_tenths": 90},
    {"element_id": 4, "web_name": "Bench", "position": "DEF", "team_id": 4, "price_tenths": 45},
]


def private_attempt():
    return {
        "schema_version": 2,
        "private_attempt_id": "private-id",
        "public_attempt_id": "public-id",
        "season": "2026-2027",
        "target_gameweek": 3,
        "team_state": {
            "entry_id": 63984,
            "bank_tenths": 5,
            "free_transfers": 2,
            "active_chip": None,
        },
        "system_decision": {
            "decision_mode": "TRANSFER_HORIZON",
            "xi_ids": [1, 2, 3],
            "captain_id": 2,
            "vice_captain_id": 3,
            "bench_order": [4],
            "transfers_in": [3],
            "transfers_out": [4],
            "transfer_hits": 0,
            "objective": 57.1,
            "horizon": 8,
        },
        "transfer_plan": [
            {"horizon": 1, "gameweek": 3, "transfers_in": [3], "transfers_out": [4], "bank_tenths": 5, "free_transfers": 2, "hits": 0, "submitted_ev": 57.1},
            {"horizon": 2, "gameweek": 4, "transfers_in": [], "transfers_out": [], "bank_tenths": 5, "free_transfers": 2, "hits": 0, "submitted_ev": 54.0},
            {"horizon": 3, "gameweek": 5, "transfers_in": [4], "transfers_out": [3], "bank_tenths": 5, "free_transfers": 2, "hits": 0, "submitted_ev": 56.0},
            {"horizon": 4, "gameweek": 6, "transfers_in": [], "transfers_out": [], "bank_tenths": 5, "free_transfers": 3, "hits": 0, "submitted_ev": 58.0},
        ],
        "canonical_forecast_sha256": "a" * 64,
        "canonical_forecast": {
            "official": {"players": PLAYERS, "deadlines": {"3": "2026-09-04T17:30:00Z"}},
            "serving_provider_by_horizon": {"1": "airsenal", "2": "airsenal"},
        },
    }


def public_attempt():
    return {
        "public_attempt_id": "public-id",
        "target_gameweek": 3,
        "code_sha": "9" * 40,
        "frozen_at": "2026-09-04T15:30:00Z",
        "certification": {"state": "CERTIFIED", "actionable": True, "warnings": [], "reasons": []},
        "manager_actionability": {
            "manager_state_scope": "FULL_MANAGER",
            "personalized_actionable": True,
            "exact_transfer_state_verified": True,
            "current_editable_team_verified": True,
        },
    }


class OwnerBriefTests(unittest.TestCase):
    def test_builds_read_only_owner_surface(self):
        brief = build_owner_brief(private_attempt(), public_attempt(), {}, source_private_sha256="b" * 64, control_plane_sha="c" * 40)
        self.assertEqual(brief["status"], "ACTIONABLE")
        self.assertEqual(brief["decision"]["captain"]["name"], "Captain")
        self.assertEqual(brief["decision"]["transfers_in"][0]["name"], "Vice")
        self.assertEqual([row["horizon"] for row in brief["h2_h3_plan"]], [2, 3])
        self.assertEqual(brief["h2_h3_plan"][1]["transfers_in"][0]["name"], "Bench")
        self.assertEqual(brief["production_influence"], "NONE")
        self.assertFalse(brief["serving_authorized"])
        self.assertTrue(all(value is False for key, value in brief["guardrails"].items() if key != "private_only"))
        self.assertTrue(brief["guardrails"]["private_only"])

    def test_missing_actionability_fails_closed_in_display(self):
        pub = public_attempt()
        pub["manager_actionability"]["personalized_actionable"] = False
        brief = build_owner_brief(private_attempt(), pub, {}, source_private_sha256="b" * 64, control_plane_sha="c" * 40)
        self.assertEqual(brief["status"], "NOT_ACTIONABLE")

    def test_missing_system_decision_is_not_actionable(self):
        private = private_attempt()
        private["system_decision"] = None
        brief = build_owner_brief(private, public_attempt(), {}, source_private_sha256="b" * 64, control_plane_sha="c" * 40)
        self.assertEqual(brief["status"], "NOT_ACTIONABLE")
        self.assertEqual(brief["decision"]["xi"], [])

    def test_missing_official_identity_is_fatal(self):
        private = private_attempt()
        private["canonical_forecast"]["official"]["players"] = [
            row for row in PLAYERS if row["element_id"] != 2
        ]
        with self.assertRaises(RuntimeError):
            build_owner_brief(
                private,
                public_attempt(),
                {},
                source_private_sha256="b" * 64,
                control_plane_sha="c" * 40,
            )

    def test_h2_h3_plan_excludes_current_h1_and_later_scenarios(self):
        brief = build_owner_brief(
            private_attempt(),
            public_attempt(),
            {},
            source_private_sha256="b" * 64,
            control_plane_sha="c" * 40,
        )
        self.assertEqual([row["gameweek"] for row in brief["h2_h3_plan"]], [4, 5])
        text = render_markdown(brief)
        self.assertIn("H2 / GW4", text)
        self.assertIn("H3 / GW5", text)
        self.assertNotIn("H1 / GW3", text)

    def test_identity_mismatch_is_fatal(self):
        private = private_attempt()
        private["public_attempt_id"] = "wrong"
        with self.assertRaises(RuntimeError):
            build_owner_brief(private, public_attempt(), {}, source_private_sha256="b" * 64, control_plane_sha="c" * 40)

    def test_markdown_contains_decision_but_no_recomputation_claim(self):
        brief = build_owner_brief(private_attempt(), public_attempt(), {}, source_private_sha256="b" * 64, control_plane_sha="c" * 40)
        text = render_markdown(brief)
        self.assertIn("OUT: Bench → IN: Vice", text)
        self.assertIn("does not recompute xP", text)

    def test_source_payload_is_not_mutated(self):
        private = private_attempt()
        original = copy.deepcopy(private)
        build_owner_brief(private, public_attempt(), {}, source_private_sha256="b" * 64, control_plane_sha="c" * 40)
        self.assertEqual(private, original)


if __name__ == "__main__":
    unittest.main()
