from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import apex_v2_tournament_common as common  # noqa: E402
import apex_v2_tournament_contract as contract  # noqa: E402
import apex_v2_tournament_scoring as scoring  # noqa: E402


def surface(
    provider: str,
    horizons=(1,),
    *,
    generated="2026-09-01T12:00:00Z",
    season="2026-2027",
    player_ids=(1, 2, 3),
    with_minutes=False,
    values=None,
):
    rows = []
    values = values or {}
    for horizon in horizons:
        for element_id in player_ids:
            row = {
                "element_id": element_id,
                "gameweek": 3 + horizon - 1,
                "horizon": horizon,
                "expected_points": float(
                    values.get((horizon, element_id), element_id + horizon)
                ),
                "coverage_status": "FORECAST",
            }
            if with_minutes:
                row.update(
                    {
                        "expected_minutes": 75.0,
                        "p_appearance": 0.9,
                        "p_start": 0.8,
                        "p_60": 0.7,
                    }
                )
            rows.append(row)
    return {
        "schema_version": 1,
        "provider_id": provider,
        "provider_version": f"{provider}-v1",
        "generated_at": generated,
        "season": season,
        "source_snapshot": "test",
        "scoring_rules_version": "fpl-2026-27-v1",
        "supported_horizons": list(horizons),
        "runtime_dependencies": [],
        "rows": rows,
    }


def qrow(
    provider: str,
    horizons=(1,),
    *,
    reasons=(),
    health="HEALTHY",
    role="SHADOW",
    serving=False,
):
    return {
        "provider_id": provider,
        "role": role,
        "health": health,
        "qualification_by_horizon": {
            str(horizon): (
                "QUALIFIED" if horizon in horizons else "UNQUALIFIED"
            )
            for horizon in range(1, 9)
        },
        "reasons": list(reasons),
        "serve_authorized": serving,
    }


def base_inputs(gameweek=3, season="2026-2027"):
    public = {
        "public_attempt_id": "a" * 64,
        "run_id": "123-1",
        "snapshot_id": "b" * 64,
        "season": season,
        "target_gameweek": gameweek,
        "official_snapshot_sha256": "c" * 64,
        "frozen_at": "2026-09-01T13:00:00Z",
        "certification": {
            "actionable": True,
            "valid_until": "2026-09-04T17:30:00Z",
        },
        "manager_actionability": {"personalized_actionable": True},
        "serving_provider_by_horizon": {
            str(horizon): "airsenal" for horizon in range(1, 9)
        },
    }
    governance = {
        "season": season,
        "target_gameweek": gameweek,
        "qualification_matrix": [
            qrow(
                "airsenal",
                range(1, 9),
                role="CHAMPION",
                serving=True,
            ),
            qrow("apex_proprietary", range(1, 9)),
            qrow("dastan", (1,)),
        ],
    }
    internal = {
        "airsenal": surface("airsenal", range(1, 9), season=season),
        "apex_proprietary": surface(
            "apex_proprietary", range(1, 9), season=season
        ),
        "dastan": surface("dastan", (1,), season=season),
    }
    hashes = {
        "airsenal": "1" * 64,
        "apex_proprietary": "2" * 64,
        "dastan": "3" * 64,
    }
    pitch_surface = surface("pitchside", range(1, 9), season=season)
    pitchside = {
        "provider_id": "pitchside",
        "health": "HEALTHY",
        "expected_official_hash": "c" * 64,
        "current_official_hash": "c" * 64,
        "post_capture_official_hash": "c" * 64,
        "generated_at": "2026-09-01T12:00:00Z",
        "qualified_horizons": list(range(1, 9)),
        "forecastable_player_count": 3,
        "official_unavailable_player_count": 0,
        "forecast_counts_by_horizon": {
            str(horizon): 3 for horizon in range(1, 9)
        },
        "unavailable_no_forecast_expected_by_horizon": {
            str(horizon): 0 for horizon in range(1, 9)
        },
        "missing_forecastable_ids_by_horizon": {
            str(horizon): [] for horizon in range(1, 9)
        },
        "source_bundle_sha256": "d" * 64,
        "surface_sha256": common.canonical_sha256(pitch_surface),
        "surface": pitch_surface,
    }
    openfpl = {
        "health": "HEALTHY",
        "state": "TRAINING_NOT_READY",
        "exact_rule_gameweek_count": 1,
        "minimum_exact_rule_gameweeks": 10,
        "observed_history_commit": "e" * 40,
        "observed_history_manifest_sha256": "f" * 64,
        "reasons": [
            "1 completed exact-rule gameweek; governed minimum is 10"
        ],
    }
    source_release = {
        "immutable": True,
        "tag_name": f"apex-v2/final/{season}/123-1",
        "id": 7,
    }
    return (
        public,
        governance,
        internal,
        hashes,
        pitchside,
        openfpl,
        source_release,
    )


def readiness(gameweek=3, season="2026-2027"):
    (
        public,
        governance,
        internal,
        hashes,
        pitchside,
        openfpl,
        release,
    ) = base_inputs(gameweek, season)
    return contract.build_readiness(
        public,
        governance,
        internal,
        source_release=release,
        internal_surface_sha256=hashes,
        pitchside_capture=pitchside,
        openfpl_readiness=openfpl,
        private_base_release_tag=(
            f"apex-v2/private-evaluation/{season}/123-1"
        ),
        private_tournament_release_tag=(
            f"apex-v2/private-tournament/{season}/123-1"
        ),
    )


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.content = json.dumps(payload).encode()
        self.response = self

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            error = common.requests.HTTPError(str(self.status_code))
            error.response = self
            raise error


class Session:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def get(self, url, timeout=30):
        self.calls.append(url)
        value = self.mapping[url]
        if isinstance(value, list):
            return value.pop(0)
        return value


def pitchside_session(
    *,
    missing_active=False,
    gws=None,
):
    gws = list(gws or range(3, 11))
    bootstrap = {
        "events": [
            {
                "id": 3,
                "deadline_time": "2026-09-04T17:30:00Z",
                "finished": False,
            }
        ],
        "elements": [
            {"id": 1, "code": 101, "status": "a", "team": 1},
            {"id": 2, "code": 202, "status": "u", "team": 2},
            {"id": 3, "code": 303, "status": "d", "team": 3},
        ],
    }
    fixtures = [
        {"id": 11, "event": 3, "team_h": 1, "team_a": 2},
        {"id": 12, "event": 3, "team_h": 3, "team_a": 4},
    ]
    forecasts = {
        "101": [3.0] * len(gws),
        "303": (
            [None] * len(gws)
            if missing_active
            else [4.0] * len(gws)
        ),
    }
    xp = {"gws": gws, "players": forecasts}
    meta = {
        "generated_utc": "2026-09-01T15:57:51Z",
        "season": 2026,
        "model_version": "2026-07-24T16:47:08+00:00",
    }
    base = common.PITCHSIDE_BASE
    return Session(
        {
            common.FPL_BOOTSTRAP: Response(bootstrap),
            common.FPL_FIXTURES: Response(fixtures),
            f"{base}/meta.json": [Response(meta), Response(meta)],
            f"{base}/xp.json": Response(xp),
            f"{base}/players.json": Response([]),
        }
    )


def live_payload(points):
    return {
        "elements": [
            {
                "id": player_id,
                "stats": {
                    "total_points": score,
                    "minutes": 90 if player_id % 2 else 30,
                },
            }
            for player_id, score in sorted(points.items())
        ]
    }


class TournamentContractTests(unittest.TestCase):
    def test_dastan_h1_only_enters_universal_not_strategic(self):
        result = readiness()
        row = result["providers"]["dastan"]
        self.assertEqual(row["h1"]["status"], "ENTERED")
        self.assertEqual(
            row["strategic_h2_h8"]["status"], "NOT_ENTERED"
        )
        self.assertIn("dastan", result["universal_h1_league"]["entrants"])

    def test_openfpl_below_floor_is_explicit_training_dns(self):
        result = readiness()
        row = result["providers"]["openfpl"]
        self.assertEqual(row["h1"]["dns_code"], common.DNS_TRAINING_NOT_READY)
        self.assertEqual(row["training_state"], "TRAINING_NOT_READY")
        self.assertEqual(row["history_commit"], "e" * 40)
        self.assertEqual(row["history_manifest_sha256"], "f" * 64)

    def test_openfpl_floor_without_model_is_not_entered(self):
        args = list(base_inputs())
        openfpl = args[5]
        openfpl["state"] = "READY_FOR_SHADOW_BUILD"
        openfpl["exact_rule_gameweek_count"] = 10
        result = contract.build_readiness(
            args[0],
            args[1],
            args[2],
            source_release=args[6],
            internal_surface_sha256=args[3],
            pitchside_capture=args[4],
            openfpl_readiness=openfpl,
            private_base_release_tag="private",
            private_tournament_release_tag="supplement",
        )
        row = result["providers"]["openfpl"]
        self.assertEqual(
            row["h1"]["dns_code"],
            common.DNS_TRAINING_READY_NO_MODEL,
        )
        self.assertEqual(row["training_state"], "READY_FOR_SHADOW_BUILD")

    def test_ready_candidate_has_no_observation_number(self):
        result = readiness()
        self.assertTrue(result["tournament_ready"])
        self.assertEqual(
            result["classification"], common.PROSPECTIVE_READY_CANDIDATE
        )
        self.assertIsNone(result["prospective_observation_number"])
        self.assertTrue(
            result["common_seal"][
                "eligible_common_predeadline_candidate"
            ]
        )

    def test_nonready_candidate_is_not_marked_common_seal_eligible(self):
        args = list(base_inputs())
        args[0]["manager_actionability"]["personalized_actionable"] = False
        result = contract.build_readiness(
            args[0],
            args[1],
            args[2],
            source_release=args[6],
            internal_surface_sha256=args[3],
            pitchside_capture=args[4],
            openfpl_readiness=args[5],
            private_base_release_tag="private",
            private_tournament_release_tag="supplement",
        )
        self.assertFalse(result["tournament_ready"])
        self.assertFalse(
            result["common_seal"][
                "eligible_common_predeadline_candidate"
            ]
        )

    def test_gw2_is_retained_noncanonical(self):
        result = readiness(gameweek=2)
        self.assertEqual(result["classification"], common.GW2_CLASSIFICATION)
        self.assertFalse(result["tournament_ready"])
        self.assertFalse(
            result["common_seal"][
                "eligible_common_predeadline_candidate"
            ]
        )
        self.assertFalse(
            result["gw2_policy"]["canonical_win_loss_allowed"]
        )

    def test_market_cannot_be_projection_entrant(self):
        args = base_inputs()
        with self.assertRaises(common.TournamentContractError):
            contract.build_readiness(
                args[0],
                args[1],
                args[2],
                source_release=args[6],
                internal_surface_sha256=args[3],
                pitchside_capture=args[4],
                openfpl_readiness=args[5],
                private_base_release_tag="private",
                private_tournament_release_tag="supplement",
                market_benchmark={
                    "status": "AVAILABLE",
                    "projection_league_entrant": True,
                },
            )

    def test_public_readiness_contains_no_raw_forecast_rows(self):
        encoded = json.dumps(readiness())
        self.assertNotIn('"rows"', encoded)
        self.assertNotIn('"expected_points"', encoded)

    def test_internal_provider_omission_fails_closed(self):
        args = list(base_inputs())
        args[1]["qualification_matrix"] = args[1][
            "qualification_matrix"
        ][:-1]
        with self.assertRaises(common.TournamentContractError):
            contract.build_readiness(
                args[0],
                args[1],
                args[2],
                source_release=args[6],
                internal_surface_sha256=args[3],
                pitchside_capture=args[4],
                openfpl_readiness=args[5],
                private_base_release_tag="private",
                private_tournament_release_tag="supplement",
            )

    def test_serving_authority_change_fails_closed(self):
        args = list(base_inputs())
        args[0]["serving_provider_by_horizon"]["4"] = "dastan"
        with self.assertRaises(common.TournamentContractError):
            contract.build_readiness(
                args[0],
                args[1],
                args[2],
                source_release=args[6],
                internal_surface_sha256=args[3],
                pitchside_capture=args[4],
                openfpl_readiness=args[5],
                private_base_release_tag="private",
                private_tournament_release_tag="supplement",
            )

    def test_latest_valid_predeadline_candidate_wins(self):
        first = readiness()
        second = json.loads(json.dumps(first))
        first["common_seal"]["snapshot_frozen_at"] = (
            "2026-09-01T12:00:00+00:00"
        )
        second["common_seal"]["snapshot_frozen_at"] = (
            "2026-09-04T15:00:00+00:00"
        )
        selected = contract.select_latest_valid_common_seal(
            [first, second], gameweek=3
        )
        self.assertEqual(
            selected["common_seal"]["snapshot_frozen_at"],
            "2026-09-04T15:00:00+00:00",
        )

    def test_selection_requires_deadline_and_marks_canonical_seal(self):
        selected = readiness()
        with self.assertRaises(common.TournamentContractError):
            contract.canonicalize_selected_observation(
                selected,
                observation_number=1,
                selected_at=datetime(
                    2026, 9, 4, 17, 0, tzinfo=timezone.utc
                ),
            )
        result = contract.canonicalize_selected_observation(
            selected,
            observation_number=1,
            selected_at=datetime(
                2026, 9, 4, 17, 31, tzinfo=timezone.utc
            ),
        )
        self.assertEqual(
            result["classification"],
            common.CANONICAL_PROSPECTIVE_OBSERVATION,
        )
        self.assertEqual(result["prospective_observation_number"], 1)
        self.assertTrue(
            result["selected_common_seal"][
                "canonical_last_valid_predeadline"
            ]
        )


class PitchsideCaptureTests(unittest.TestCase):
    def capture(self, *, session=None, current_hash="c" * 64, resolver=None):
        with tempfile.TemporaryDirectory() as tmp:
            return common.capture_pitchside(
                season="2026-2027",
                target_gameweek=3,
                expected_official_hash="c" * 64,
                current_official_hash=current_hash,
                deadline=datetime(
                    2026, 9, 4, 17, 30, tzinfo=timezone.utc
                ),
                output=Path(tmp) / "capture.json",
                now=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                session=session or pitchside_session(),
                official_hash_resolver=resolver,
            )

    def test_unavailable_player_is_no_forecast_expected(self):
        result = self.capture()
        self.assertEqual(result["health"], "HEALTHY")
        self.assertEqual(result["forecastable_player_count"], 2)
        self.assertEqual(result["official_unavailable_player_count"], 1)
        self.assertEqual(result["forecast_counts_by_horizon"]["1"], 2)
        self.assertEqual(
            result["missing_forecastable_ids_by_horizon"]["1"], []
        )
        row = next(
            row
            for row in result["surface"]["rows"]
            if row["horizon"] == 1 and row["element_id"] == 2
        )
        self.assertEqual(row["coverage_status"], "NO_FORECAST")
        self.assertEqual(
            row["coverage_reason"],
            "OFFICIAL_UNAVAILABLE_NO_FORECAST_EXPECTED",
        )

    def test_missing_forecastable_player_is_incomplete(self):
        result = self.capture(
            session=pitchside_session(missing_active=True)
        )
        self.assertEqual(result["health"], "INCOMPLETE")
        self.assertEqual(
            result["dns_code"], common.DNS_INCOMPLETE_UNIVERSE
        )
        self.assertEqual(
            result["missing_forecastable_ids_by_horizon"]["1"], [3]
        )

    def test_sparse_gameweek_vector_does_not_false_qualify_h2(self):
        result = self.capture(
            session=pitchside_session(gws=[3, 5, 6, 7, 8, 9, 10])
        )
        self.assertIn(1, result["qualified_horizons"])
        self.assertNotIn(2, result["qualified_horizons"])
        self.assertIn(3, result["qualified_horizons"])
        self.assertNotIn(2, result["surface"]["supported_horizons"])

    def test_exact_official_hash_mismatch_fails_before_network(self):
        result = self.capture(
            current_hash="d" * 64,
            session=Session({}),
        )
        self.assertEqual(result["dns_code"], common.DNS_OFFICIAL_HASH)
        self.assertIsNone(result["surface"])

    def test_post_capture_official_hash_drift_fails_closed(self):
        hashes = iter(["c" * 64, "d" * 64])

        def resolver(*, season):
            self.assertEqual(season, "2026-2027")
            return next(hashes)

        with tempfile.TemporaryDirectory() as tmp:
            result = common.capture_pitchside(
                season="2026-2027",
                target_gameweek=3,
                expected_official_hash="c" * 64,
                current_official_hash=None,
                deadline=datetime(
                    2026, 9, 4, 17, 30, tzinfo=timezone.utc
                ),
                output=Path(tmp) / "capture.json",
                now=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                session=pitchside_session(),
                official_hash_resolver=resolver,
            )
        self.assertEqual(result["dns_code"], common.DNS_OFFICIAL_HASH)
        self.assertIsNone(result["surface"])


class TournamentScoringTests(unittest.TestCase):
    def test_missing_entered_provider_fails_closed(self):
        with self.assertRaises(common.TournamentContractError):
            scoring.score_horizon(
                {"a": surface("a")},
                entrants=["a", "missing"],
                gameweek=3,
                horizon=1,
                live_payload=live_payload({1: 1, 2: 2, 3: 3}),
                decision_surface=frozenset({1, 2, 3}),
            )

    def test_h1_uses_exact_model_neutral_surface(self):
        result = scoring.score_horizon(
            {"a": surface("a"), "b": surface("b")},
            entrants=["a", "b"],
            gameweek=3,
            horizon=1,
            live_payload=live_payload({1: 1, 2: 2, 3: 3}),
            decision_surface=frozenset({1, 3}),
        )
        self.assertEqual(
            result["comparison_surface_method"],
            "MODEL_NEUTRAL_DECISION_SURFACE_V1",
        )
        self.assertEqual(result["comparison_surface_player_count"], 2)
        self.assertEqual(
            result["all_pairwise"]["a::b"]["paired_rows"], 2
        )

    def test_strategic_horizon_uses_common_forecast_intersection(self):
        surfaces = {
            "a": surface(
                "a", horizons=(2,), player_ids=(1, 2, 3)
            ),
            "b": surface(
                "b", horizons=(2,), player_ids=(2, 3, 4)
            ),
        }
        result = scoring.score_horizon(
            surfaces,
            entrants=["a", "b"],
            gameweek=4,
            horizon=2,
            live_payload=live_payload({1: 1, 2: 2, 3: 3, 4: 4}),
        )
        self.assertEqual(
            result["comparison_surface_method"],
            "COMMON_FORECAST_INTERSECTION",
        )
        self.assertEqual(result["comparison_surface_player_count"], 2)
        self.assertEqual(
            result["providers"]["a"]["comparison_surface_rows"], 2
        )
        self.assertEqual(
            result["providers"]["b"]["comparison_surface_rows"], 2
        )
        self.assertEqual(
            result["all_pairwise"]["a::b"]["paired_rows"], 2
        )

    def test_catastrophic_xp_residual_is_explicit(self):
        result = scoring.score_horizon(
            {
                "a": surface(
                    "a",
                    player_ids=(1,),
                    values={(1, 1): 10.0},
                )
            },
            entrants=["a"],
            gameweek=3,
            horizon=1,
            live_payload=live_payload({1: 0}),
            decision_surface=frozenset({1}),
        )
        residual = result["providers"]["a"]["xp_residuals"]
        self.assertEqual(
            residual["threshold_points"],
            scoring.CATASTROPHIC_XP_RESIDUAL,
        )
        self.assertEqual(residual["catastrophic_residual_count"], 1)

    def test_specialist_scores_only_supplied_components(self):
        result = scoring.specialist_metrics(
            surface("a", with_minutes=True),
            {
                "actual_points": {1: 1, 2: 2, 3: 3},
                "actual_minutes": {1: 90, 2: 0, 3: 60},
            },
            gameweek=3,
        )
        self.assertEqual(result["minutes"]["status"], "SCORED")
        self.assertEqual(
            result["appearance_probability"]["status"], "SCORED"
        )
        self.assertEqual(
            result["start_probability"]["status"],
            "NOT_SCOREABLE_NO_REALIZED_START_LABEL",
        )
        self.assertTrue(
            result["component_policy"]["no_hindsight_imputation"]
        )


if __name__ == "__main__":
    unittest.main()
