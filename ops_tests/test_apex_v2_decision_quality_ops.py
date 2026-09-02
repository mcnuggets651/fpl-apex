from __future__ import annotations

import unittest

from scripts import apex_v2_decision_quality_ops as dq


POSITIONS = ["GK", "GK"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
PLAYERS = [
    {
        "element_id": idx + 1,
        "web_name": f"P{idx + 1}",
        "position": pos,
        "team_id": 1,
        "price_tenths": 50,
    }
    for idx, pos in enumerate(POSITIONS)
]
POSITION_MAP = {row["element_id"]: row["position"] for row in PLAYERS}
SQUAD = list(range(1, 16))
XI = [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15]
BENCH = [2, 6, 7, 12]


def private_attempt():
    rows = []
    for pid in SQUAD:
        rows.append(
            {
                "element_id": pid,
                "gameweek": 3,
                "horizon": 1,
                "expected_minutes": 80.0,
                "serving_provider_id": "airsenal",
            }
        )
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
    minutes["13"] = 0.0
    points["13"] = 0.0
    points["6"] = 12.0
    return {
        "schema_version": 1,
        "gameweek": 3,
        "public_attempt_id": "public-id",
        "official_live_hash": "a" * 64,
        "actual_points": points,
        "actual_minutes": minutes,
    }


def decision(*, bench_order=None, hits=0):
    return {
        "squad_ids": SQUAD,
        "xi_ids": XI,
        "bench_order": bench_order or BENCH,
        "captain_id": 13,
        "vice_captain_id": 8,
        "transfers_in": [],
        "transfers_out": [],
        "transfer_hits": hits,
    }


def edge(observation_number: int, edge_points: float, *, provider="dastan"):
    return {
        "source": {
            "prospective_observation_number": observation_number,
            "target_gameweek": observation_number + 2,
        },
        "baseline_variant_id": "production_baseline",
        "variants": {
            "production_baseline": {
                "provider_id": "airsenal",
                "variant_kind": "PRODUCTION_BASELINE",
                "edge_vs_production_points": 0.0,
                "decision_changed_vs_production": False,
            },
            f"h1_plus_airsenal_future::{provider}": {
                "provider_id": provider,
                "variant_kind": "CHALLENGER_H1_AIRSENAL_H2_PLUS",
                "edge_vs_production_points": edge_points,
                "decision_changed_vs_production": True,
            },
        },
    }


class DecisionQualityCompatibilityTests(unittest.TestCase):
    def test_sealed_xi_is_legal(self):
        players = {row["element_id"]: row for row in PLAYERS}
        self.assertTrue(dq.legal_xi(tuple(XI), players))

    def test_existing_v1_diagnostics_remain_non_serving(self):
        result = dq.build_decision_quality(
            private_attempt(),
            outcome(),
            source_private_sha256="b" * 64,
            source_outcome_sha256="c" * 64,
            control_plane_sha="d" * 40,
        )
        self.assertEqual(result["production_influence"], "NONE")
        self.assertFalse(result["serving_authorized"])
        self.assertFalse(result["promotion_authority"])
        self.assertEqual(result["captaincy"]["effective_captain_id"], 8)
        self.assertEqual(result["lineup"]["zero_minute_selected_starters"], [13])
        self.assertEqual(result["minutes"]["final_squad_expected_minutes_rows"], 15)
        self.assertEqual(result["minutes"]["final_squad_expected_minutes_coverage"], 1.0)

    def test_public_private_identity_mismatch_fails(self):
        out = outcome()
        out["public_attempt_id"] = "wrong"
        with self.assertRaises(RuntimeError):
            dq.build_decision_quality(
                private_attempt(),
                out,
                source_private_sha256="b" * 64,
                source_outcome_sha256="c" * 64,
                control_plane_sha="d" * 40,
            )

    def test_invalid_final_squad_partition_fails(self):
        private = private_attempt()
        private["system_decision"]["bench_order"] = BENCH[:-1]
        with self.assertRaises(RuntimeError):
            dq.build_decision_quality(
                private,
                outcome(),
                source_private_sha256="b" * 64,
                source_outcome_sha256="c" * 64,
                control_plane_sha="d" * 40,
            )

    def test_transfer_delta_is_none_when_transfer_counts_do_not_match(self):
        private = private_attempt()
        private["system_decision"]["transfers_out"] = []
        result = dq.build_decision_quality(
            private,
            outcome(),
            source_private_sha256="b" * 64,
            source_outcome_sha256="c" * 64,
            control_plane_sha="d" * 40,
        )
        self.assertIsNone(
            result["transfers"]["same_gameweek_transferred_player_points_delta_vs_hold"]
        )


class RealizedDecisionEdgeTests(unittest.TestCase):
    def score(self, *, payload=None, points=None, minutes=None, chip=None, hit_cost=4):
        return dq._realized_decision_score(
            payload or decision(),
            actual_points=points or {pid: 1.0 for pid in SQUAD},
            actual_minutes=minutes or {pid: 90.0 for pid in SQUAD},
            positions=POSITION_MAP,
            active_chip=chip,
            transfer_hit_cost=hit_cost,
        )

    def test_formation_aware_autosub_skips_illegal_first_bench(self):
        # Submitted 3-4-3. DEF P3 misses. Put MID P12 ahead of DEF P6:
        # P12 cannot replace P3 because that would leave only two defenders.
        payload = decision(bench_order=[2, 12, 6, 7])
        minutes = {pid: 90.0 for pid in SQUAD}
        minutes[3] = 0.0
        result = self.score(payload=payload, minutes=minutes)
        self.assertEqual(result["autosubbed_in_ids"], [6])
        self.assertEqual(result["scoring_player_count_before_captain"], 11)

    def test_goalkeeper_autosub_is_separate_and_exact(self):
        minutes = {pid: 90.0 for pid in SQUAD}
        minutes[1] = 0.0
        result = self.score(minutes=minutes)
        self.assertEqual(result["goalkeeper_autosub_id"], 2)
        self.assertIn(2, result["autosubbed_in_ids"])

    def test_captain_no_show_falls_back_to_vice(self):
        minutes = {pid: 90.0 for pid in SQUAD}
        minutes[13] = 0.0
        points = {pid: 1.0 for pid in SQUAD}
        points[8] = 7.0
        result = self.score(points=points, minutes=minutes)
        self.assertEqual(result["effective_captain_id"], 8)
        self.assertEqual(result["captain_bonus_points"], 7.0)

    def test_transfer_hits_are_deducted(self):
        payload = decision(hits=2)
        result = self.score(payload=payload, hit_cost=4)
        self.assertEqual(result["transfer_hit_cost_points"], 8.0)

    def test_triple_captain_adds_two_extra_copies(self):
        points = {pid: 1.0 for pid in SQUAD}
        points[13] = 6.0
        result = self.score(points=points, chip="3xc")
        self.assertEqual(result["captain_bonus_points"], 12.0)

    def test_bench_boost_scores_exact_full_fifteen(self):
        minutes = {pid: 90.0 for pid in SQUAD}
        minutes[2] = 0.0
        points = {pid: 1.0 for pid in SQUAD}
        points[2] = 0.0
        result = self.score(points=points, minutes=minutes, chip="bboost")
        self.assertEqual(result["scoring_player_count_before_captain"], 15)
        self.assertEqual(result["autosubbed_in_ids"], [])

    def test_unknown_future_chip_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.score(chip="mystery-chip")


class CounterfactualConstructionTests(unittest.TestCase):
    def test_availability_overlay_never_changes_airsenal_xp(self):
        challenger = {
            "provider_version": "challenger-v1",
            "rows": [
                {
                    "element_id": pid,
                    "horizon": 1,
                    "coverage_status": "FORECAST",
                    "expected_points": 100.0 + pid,
                    "expected_minutes": 40.0 + pid,
                    "p_appearance": 0.5,
                    "p_start": 0.4,
                    "p_60": 0.3,
                }
                for pid in (1, 2)
            ],
        }
        airsenal = {
            "provider_version": "airsenal-v1",
            "season": "2026-2027",
            "source_snapshot": "official",
            "scoring_rules_version": "fpl-2026-27-v1",
            "rows": [
                {
                    "element_id": pid,
                    "horizon": 1,
                    "expected_points": float(pid * 2),
                    "expected_minutes": 80.0,
                    "p_appearance": 0.9,
                    "p_start": 0.8,
                    "p_60": 0.7,
                    "metadata": {},
                }
                for pid in (1, 2)
            ],
        }
        overlay, fields = dq._availability_overlay(
            provider_id="challenger",
            challenger=challenger,
            airsenal=airsenal,
            required_ids=frozenset({1, 2}),
            max_horizon=1,
        )
        self.assertEqual(
            [row["expected_points"] for row in overlay["rows"]],
            [2.0, 4.0],
        )
        self.assertEqual(
            fields,
            ["expected_minutes", "p_appearance", "p_start", "p_60"],
        )

    def test_incomplete_availability_field_is_not_silently_overlaid(self):
        challenger = {
            "provider_version": "challenger-v1",
            "rows": [
                {
                    "element_id": 1,
                    "horizon": 1,
                    "coverage_status": "FORECAST",
                    "expected_points": 4.0,
                    "p_appearance": 0.8,
                },
                {
                    "element_id": 2,
                    "horizon": 1,
                    "coverage_status": "FORECAST",
                    "expected_points": 4.0,
                    "p_appearance": None,
                },
            ],
        }
        airsenal = {
            "provider_version": "airsenal-v1",
            "season": "2026-2027",
            "source_snapshot": "official",
            "scoring_rules_version": "fpl-2026-27-v1",
            "rows": [],
        }
        with self.assertRaises(RuntimeError):
            dq._availability_overlay(
                provider_id="challenger",
                challenger=challenger,
                airsenal=airsenal,
                required_ids=frozenset({1, 2}),
                max_horizon=1,
            )


class SequentialDecisionEdgeLearningTests(unittest.TestCase):
    def test_one_observation_is_diagnostic_only(self):
        report = dq.build_decision_edge_learning(
            [edge(1, 8.0)], season="2026-2027"
        )
        row = report["variant_evidence"]["h1_plus_airsenal_future::dastan"]
        self.assertEqual(row["stage"], "DIAGNOSTIC_SIGNAL")
        self.assertFalse(row["review_eligible"])
        self.assertFalse(report["automatic_serving_change"])

    def test_two_large_unanimous_wins_fast_track_review(self):
        report = dq.build_decision_edge_learning(
            [edge(1, 5.0), edge(2, 5.0)], season="2026-2027"
        )
        row = report["variant_evidence"]["h1_plus_airsenal_future::dastan"]
        self.assertEqual(row["stage"], "FAST_TRACK_REVIEW_ELIGIBLE")
        self.assertTrue(row["review_eligible"])
        self.assertEqual(report["serving_action"], "NO_AUTOMATIC_CHANGE")

    def test_provider_names_have_no_prior(self):
        report = dq.build_decision_edge_learning(
            [edge(1, 5.0, provider="model_x"), edge(2, 5.0, provider="model_x")],
            season="2026-2027",
        )
        row = report["variant_evidence"]["h1_plus_airsenal_future::model_x"]
        self.assertEqual(row["provider_id"], "model_x")
        self.assertEqual(row["stage"], "FAST_TRACK_REVIEW_ELIGIBLE")

    def test_twelve_gameweeks_are_not_a_learning_or_review_gate(self):
        report = dq.build_decision_edge_learning(
            [edge(1, 5.0), edge(2, 5.0)], season="2026-2027"
        )
        self.assertFalse(report["twelve_gameweeks_required_before_learning"])
        self.assertFalse(report["twelve_gameweeks_required_before_review"])


if __name__ == "__main__":
    unittest.main()
