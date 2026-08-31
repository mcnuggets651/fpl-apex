from __future__ import annotations

import unittest

from scripts.apex_v2_decision_quality_ops import build_decision_quality, legal_xi


# Valid FPL 15: 2 GK, 5 DEF, 5 MID, 3 FWD
POSITIONS = ["GK", "GK"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
PLAYERS = [
    {"element_id": idx + 1, "web_name": f"P{idx+1}", "position": pos, "team_id": 1, "price_tenths": 50}
    for idx, pos in enumerate(POSITIONS)
]
SQUAD = list(range(1, 16))
XI = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]  # 1GK,3DEF,4MID,3FWD
BENCH = [2, 6, 7, 12]


def private_attempt():
    rows = []
    for pid in SQUAD:
        rows.append({
            "element_id": pid,
            "gameweek": 3,
            "horizon": 1,
            "expected_minutes": 80.0,
            "serving_provider_id": "airsenal",
        })
    return {
        "schema_version": 2,
        "public_attempt_id": "public-id",
        "private_attempt_id": "private-id",
        "season": "2026-2027",
        "target_gameweek": 3,
        "team_state": {"free_transfers": 2},
        "system_decision": {
            "squad_ids": SQUAD,
            "xi_ids": XI,
            "bench_order": BENCH,
            "captain_id": 13,
            "vice_captain_id": 8,
            "transfers_in": [15],
            "transfers_out": [99],
            "transfer_hits": 0,
        },
        "canonical_forecast": {
            "canonical_projection_sha256": "f" * 64,
            "serving_provider_by_horizon": {"1": "airsenal"},
            "official": {"players": PLAYERS},
            "rows": rows,
        },
    }


def outcome():
    points = {str(pid): float(pid % 8) for pid in range(1, 100)}
    minutes = {str(pid): 90.0 for pid in range(1, 100)}
    # Captain misses out so vice becomes effective.
    minutes["13"] = 0.0
    points["13"] = 0.0
    # Make bench defender P6 a big hindsight alternative.
    points["6"] = 12.0
    return {
        "schema_version": 1,
        "gameweek": 3,
        "public_attempt_id": "public-id",
        "official_live_hash": "a" * 64,
        "actual_points": points,
        "actual_minutes": minutes,
    }


class DecisionQualityTests(unittest.TestCase):
    def test_sealed_xi_is_legal(self):
        players = {row["element_id"]: row for row in PLAYERS}
        self.assertTrue(legal_xi(tuple(XI), players))

    def test_scores_lineup_captain_transfer_and_minutes_without_serving_authority(self):
        dq = build_decision_quality(
            private_attempt(), outcome(), source_private_sha256="b" * 64, source_outcome_sha256="c" * 64, control_plane_sha="d" * 40
        )
        self.assertEqual(dq["production_influence"], "NONE")
        self.assertFalse(dq["serving_authorized"])
        self.assertFalse(dq["promotion_authority"])
        self.assertEqual(dq["captaincy"]["effective_captain_id"], 8)
        self.assertGreaterEqual(dq["captaincy"]["captain_bonus_realized_regret"], 0)
        self.assertGreaterEqual(dq["lineup"]["starting_xi_realized_regret_pre_autosub"], 0)
        self.assertEqual(dq["lineup"]["zero_minute_selected_starters"], [13])
        self.assertEqual(dq["minutes"]["final_squad_expected_minutes_rows"], 15)
        self.assertEqual(dq["minutes"]["final_squad_expected_minutes_coverage"], 1.0)
        self.assertIsNotNone(dq["transfers"]["same_gameweek_transferred_player_points_delta_vs_hold"])
        self.assertFalse(dq["transfers"]["hit_cost_interpreted"])

    def test_public_private_identity_mismatch_fails(self):
        out = outcome()
        out["public_attempt_id"] = "wrong"
        with self.assertRaises(RuntimeError):
            build_decision_quality(private_attempt(), out, source_private_sha256="b" * 64, source_outcome_sha256="c" * 64, control_plane_sha="d" * 40)

    def test_invalid_final_squad_partition_fails(self):
        private = private_attempt()
        private["system_decision"]["bench_order"] = BENCH[:-1]
        with self.assertRaises(RuntimeError):
            build_decision_quality(private, outcome(), source_private_sha256="b" * 64, source_outcome_sha256="c" * 64, control_plane_sha="d" * 40)

    def test_transfer_delta_is_none_when_transfer_counts_do_not_match(self):
        private = private_attempt()
        private["system_decision"]["transfers_out"] = []
        dq = build_decision_quality(private, outcome(), source_private_sha256="b" * 64, source_outcome_sha256="c" * 64, control_plane_sha="d" * 40)
        self.assertIsNone(dq["transfers"]["same_gameweek_transferred_player_points_delta_vs_hold"])


if __name__ == "__main__":
    unittest.main()
