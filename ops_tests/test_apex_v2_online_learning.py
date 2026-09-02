from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import apex_v2_tournament_scoring as scoring  # noqa: E402


def surface(provider: str, minute_values: dict[int, float]):
    return {
        "schema_version": 1,
        "provider_id": provider,
        "provider_version": f"{provider}-v1",
        "generated_at": "2026-09-01T12:00:00Z",
        "season": "2026-2027",
        "source_snapshot": "test",
        "scoring_rules_version": "fpl-2026-27-v1",
        "supported_horizons": [1],
        "runtime_dependencies": [],
        "rows": [
            {
                "element_id": player_id,
                "gameweek": 3,
                "horizon": 1,
                "expected_points": float((player_id % 5) + 1),
                "expected_minutes": float(minutes),
                "p_appearance": 0.9,
                "p_start": 0.8,
                "p_60": 0.7,
                "coverage_status": "FORECAST",
            }
            for player_id, minutes in sorted(minute_values.items())
        ],
    }


def live_payload(player_ids, *, with_starts=True):
    rows = []
    for player_id in sorted(player_ids):
        stats = {
            "total_points": float(player_id % 6),
            "minutes": 90 if player_id % 3 else 20,
        }
        if with_starts:
            stats["starts"] = 1 if player_id % 3 else 0
        rows.append({"id": player_id, "stats": stats})
    return {"elements": rows}


def provider_metrics(
    *,
    xp_mae: float,
    minutes_mae: float,
    defender_xp_mae: float,
    forward_xp_mae: float,
):
    return {
        "comparison_surface": {
            "mae": xp_mae,
            "rmse": xp_mae * 1.2,
            "mean_ndcg10": 0.6,
            "mean_ndcg25": 0.65,
        },
        "comparison_surface_rows": 120,
        "xp_residuals": {"catastrophic_residual_count": 6},
        "specialist": {
            "minutes": {
                "rows": 120,
                "mae": minutes_mae,
                "catastrophic_residual_count": 4,
            },
            "appearance_probability": {"rows": 120, "brier": 0.10},
            "start_probability": {"rows": 0, "brier": None},
            "p60_probability": {"rows": 120, "brier": 0.12},
        },
        "cohorts": {
            "position": {
                "DEF": {
                    "rows": 45,
                    "xp": {"mae": defender_xp_mae},
                    "minutes": {"rows": 45, "mae": minutes_mae},
                },
                "FWD": {
                    "rows": 25,
                    "xp": {"mae": forward_xp_mae},
                    "minutes": {"rows": 25, "mae": minutes_mae},
                },
            },
            "minutes_risk": {
                "ROTATION_RISK_UNDER_45": {
                    "rows": 20,
                    "xp": {"mae": xp_mae},
                    "minutes": {"rows": 20, "mae": minutes_mae},
                }
            },
        },
    }


def observation(number: int, *, dastan_minutes=12.0):
    return {
        "observation_number": number,
        "target_gameweek": number + 2,
        "providers": {
            "airsenal": provider_metrics(
                xp_mae=2.0,
                minutes_mae=18.0,
                defender_xp_mae=1.5,
                forward_xp_mae=2.5,
            ),
            "apex_proprietary": provider_metrics(
                xp_mae=2.1,
                minutes_mae=17.0,
                defender_xp_mae=1.7,
                forward_xp_mae=2.0,
            ),
            "dastan": provider_metrics(
                xp_mae=1.9,
                minutes_mae=dastan_minutes,
                defender_xp_mae=1.8,
                forward_xp_mae=1.7,
            ),
        },
    }


class SpecialistScoringTests(unittest.TestCase):
    def test_common_preoutcome_minutes_risk_and_position_cohorts(self):
        ids = tuple(range(1, 13))
        a_minutes = {
            1: 90,
            2: 65,
            3: 20,
            4: 80,
            5: 60,
            6: 30,
            7: 85,
            8: 50,
            9: 25,
            10: 90,
            11: 70,
            12: 35,
        }
        b_minutes = {
            1: 80,
            2: 55,
            3: 40,
            4: 70,
            5: 50,
            6: 35,
            7: 75,
            8: 60,
            9: 30,
            10: 80,
            11: 60,
            12: 40,
        }
        result = scoring.score_horizon(
            {"a": surface("a", a_minutes), "b": surface("b", b_minutes)},
            entrants=["a", "b"],
            gameweek=3,
            horizon=1,
            live_payload=live_payload(ids),
            decision_surface=frozenset(ids),
            player_positions={
                player_id: "DEF" if player_id <= 6 else "FWD"
                for player_id in ids
            },
        )
        self.assertEqual(
            result["specialist_cohort_policy"]["minutes_risk_source"],
            "PREOUTCOME_MEDIAN_SEALED_EXPECTED_MINUTES_ACROSS_ENTRANTS",
        )
        self.assertTrue(
            result["specialist_cohort_policy"]["no_hindsight_cohort_assignment"]
        )
        for provider_id in ("a", "b"):
            cohorts = result["providers"][provider_id]["cohorts"]
            self.assertEqual(set(cohorts["position"]), {"DEF", "FWD"})
            self.assertEqual(
                set(cohorts["minutes_risk"]),
                {
                    "NAILED_75_PLUS",
                    "MANAGED_45_TO_74",
                    "ROTATION_RISK_UNDER_45",
                },
            )
        self.assertNotIn("element_id", json.dumps(result["providers"]))

    def test_explicit_official_start_label_is_scored(self):
        ids = tuple(range(1, 13))
        mins = {player_id: 75.0 for player_id in ids}
        result = scoring.score_horizon(
            {"a": surface("a", mins), "b": surface("b", mins)},
            entrants=["a", "b"],
            gameweek=3,
            horizon=1,
            live_payload=live_payload(ids, with_starts=True),
            decision_surface=frozenset(ids),
        )
        self.assertEqual(
            result["providers"]["a"]["specialist"]["start_probability"][
                "status"
            ],
            "SCORED",
        )

    def test_start_label_is_never_inferred_from_minutes(self):
        ids = tuple(range(1, 13))
        mins = {player_id: 75.0 for player_id in ids}
        result = scoring.score_horizon(
            {"a": surface("a", mins), "b": surface("b", mins)},
            entrants=["a", "b"],
            gameweek=3,
            horizon=1,
            live_payload=live_payload(ids, with_starts=False),
            decision_surface=frozenset(ids),
        )
        self.assertEqual(
            result["providers"]["a"]["specialist"]["start_probability"][
                "status"
            ],
            "NOT_SCOREABLE_NO_REALIZED_START_LABEL",
        )


class SequentialLearningTests(unittest.TestCase):
    def test_one_gameweek_is_diagnostic_not_actionable(self):
        report = scoring.build_online_learning_report(
            [observation(1)], season="2026-2027"
        )
        row = report["metric_leaders"]["availability.minutes_mae"]
        self.assertEqual(row["leader"], "dastan")
        self.assertEqual(row["stage"], "DIAGNOSTIC_SIGNAL")
        self.assertFalse(row["review_eligible"])
        self.assertFalse(report["automatic_serving_change"])

    def test_two_unanimous_large_wins_fast_track_review(self):
        report = scoring.build_online_learning_report(
            [observation(1), observation(2)], season="2026-2027"
        )
        row = report["metric_leaders"]["availability.minutes_mae"]
        self.assertEqual(row["leader"], "dastan")
        self.assertEqual(row["stage"], "FAST_TRACK_REVIEW_ELIGIBLE")
        self.assertTrue(row["review_eligible"])
        self.assertTrue(
            any(
                item["provider_id"] == "dastan"
                and item["metric_id"] == "availability.minutes_mae"
                for item in report["owner_review_queue"]
            )
        )
        self.assertEqual(report["serving_action"], "NO_AUTOMATIC_CHANGE")

    def test_three_consistent_wins_become_actionable_specialist_review(self):
        report = scoring.build_online_learning_report(
            [observation(1), observation(2), observation(3)],
            season="2026-2027",
        )
        row = report["metric_leaders"]["availability.minutes_mae"]
        self.assertEqual(row["leader"], "dastan")
        self.assertEqual(row["stage"], "ACTIONABLE_SPECIALIST_REVIEW")
        self.assertTrue(row["review_eligible"])

    def test_different_models_can_lead_different_positions(self):
        report = scoring.build_online_learning_report(
            [observation(1), observation(2), observation(3)],
            season="2026-2027",
        )
        self.assertEqual(
            report["metric_leaders"]["position.DEF.xp_mae"]["leader"],
            "airsenal",
        )
        self.assertEqual(
            report["metric_leaders"]["position.FWD.xp_mae"]["leader"],
            "dastan",
        )

    def test_provider_names_have_no_prior(self):
        first = observation(1)
        second = observation(2)
        for row in (first, second):
            row["providers"]["model_x"] = row["providers"].pop("dastan")
        report = scoring.build_online_learning_report(
            [first, second], season="2026-2027"
        )
        self.assertEqual(
            report["metric_leaders"]["availability.minutes_mae"]["leader"],
            "model_x",
        )
        self.assertTrue(
            report["learning_policy"]["provider_names_do_not_receive_priors"]
        )

    def test_twelve_gameweeks_are_not_a_gate_for_learning_or_review(self):
        report = scoring.build_online_learning_report(
            [observation(1), observation(2)], season="2026-2027"
        )
        policy = report["learning_policy"]
        self.assertFalse(policy["twelve_gameweeks_required_before_learning"])
        self.assertFalse(policy["twelve_gameweeks_required_before_review"])
        self.assertTrue(policy["final_structural_decision_can_use_longer_sample"])


if __name__ == "__main__":
    unittest.main()
