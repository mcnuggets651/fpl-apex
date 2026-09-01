from __future__ import annotations

import importlib.util
import sys
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "apex_v2_tournament_ops.py"
sys.path.insert(0, str(MODULE_PATH.parent))
spec = importlib.util.spec_from_file_location("tournament_ops", MODULE_PATH)
ops = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(ops)


def surface(provider: str, horizons=(1,), generated="2026-09-01T12:00:00Z", season="2026-2027", n=3, with_minutes=False):
    rows = []
    for horizon in horizons:
        for element_id in range(1, n + 1):
            row = {
                "element_id": element_id,
                "gameweek": 3 + horizon - 1,
                "horizon": horizon,
                "expected_points": float(element_id + horizon),
                "coverage_status": "FORECAST",
            }
            if with_minutes:
                row.update({"expected_minutes": 75.0, "p_appearance": 0.9, "p_start": 0.8, "p_60": 0.7})
            rows.append(row)
    return {
        "schema_version": 1,
        "provider_id": provider,
        "provider_version": f"{provider}-v1",
        "generated_at": generated,
        "season": season,
        "source_snapshot": "x",
        "scoring_rules_version": "fpl-2026-27-v1",
        "supported_horizons": list(horizons),
        "runtime_dependencies": [],
        "rows": rows,
    }


def qrow(provider: str, horizons=(1,), reasons=(), health="HEALTHY", role="SHADOW", serving=False):
    return {
        "provider_id": provider,
        "role": role,
        "health": health,
        "qualification_by_horizon": {str(h): ("QUALIFIED" if h in horizons else "UNQUALIFIED") for h in range(1, 9)},
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
        "certification": {"actionable": True, "valid_until": "2026-09-04T17:30:00Z"},
        "manager_actionability": {"personalized_actionable": True},
        "serving_provider_by_horizon": {str(h): "airsenal" for h in range(1, 9)},
    }
    governance = {
        "season": season,
        "target_gameweek": gameweek,
        "qualification_matrix": [
            qrow("airsenal", range(1, 9), role="CHAMPION", serving=True),
            qrow("apex_proprietary", range(1, 9)),
            qrow("dastan", (1,)),
        ],
    }
    internal = {
        "airsenal": surface("airsenal", range(1, 9), season=season),
        "apex_proprietary": surface("apex_proprietary", range(1, 9), season=season),
        "dastan": surface("dastan", (1,), season=season),
    }
    hashes = {pid: (str(i) * 64)[:64] for i, pid in enumerate(ops.INTERNAL_PROVIDERS, 1)}
    pitch_surface = surface("pitchside", range(1, 9), season=season)
    pitchside = {
        "provider_id": "pitchside",
        "health": "HEALTHY",
        "expected_official_hash": "c" * 64,
        "current_official_hash": "c" * 64,
        "generated_at": "2026-09-01T12:00:00Z",
        "qualified_horizons": list(range(1, 9)),
        "forecastable_player_count": 3,
        "official_unavailable_player_count": 0,
        "forecast_counts_by_horizon": {str(h): 3 for h in range(1, 9)},
        "unavailable_no_forecast_expected_by_horizon": {str(h): 0 for h in range(1, 9)},
        "missing_forecastable_ids_by_horizon": {str(h): [] for h in range(1, 9)},
        "source_bundle_sha256": "d" * 64,
        "surface_sha256": ops.canonical_sha256(pitch_surface),
        "surface": pitch_surface,
    }
    openfpl = {
        "health": "HEALTHY",
        "state": "DEFERRED_BY_GOVERNANCE",
        "exact_rule_gameweek_count": 1,
        "minimum_exact_rule_gameweeks": 10,
        "reasons": ["1 completed exact-rule gameweek; governed minimum is 10"],
    }
    source_release = {"immutable": True, "tag_name": f"apex-v2/final/{season}/123-1", "id": 7}
    return public, governance, internal, hashes, pitchside, openfpl, source_release


def readiness(gameweek=3, season="2026-2027"):
    public, governance, internal, hashes, pitchside, openfpl, release = base_inputs(gameweek, season)
    return ops.build_readiness(
        public,
        governance,
        internal,
        source_release=release,
        internal_surface_sha256=hashes,
        pitchside_capture=pitchside,
        openfpl_readiness=openfpl,
        private_base_release_tag=f"apex-v2/private-evaluation/{season}/123-1",
        private_tournament_release_tag=f"apex-v2/private-tournament/{season}/123-1",
    )


class Response:
    def __init__(self, payload, status=200):
        self.payload = payload
        self.status_code = status
        self.content = json.dumps(payload).encode()

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ops.requests.HTTPError(str(self.status_code))


class Session:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, url, timeout=30):
        value = self.mapping[url]
        if isinstance(value, list):
            return value.pop(0)
        return value


def pitchside_session(*, missing_active=False, omit_unavailable=True):
    bootstrap = {
        "events": [
            {"id": 3, "deadline_time": "2026-09-04T17:30:00Z", "finished": False}
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
    forecasts = {"101": [3.0] * 8, "303": ([None] * 8 if missing_active else [4.0] * 8)}
    if not omit_unavailable:
        forecasts["202"] = [None] * 8
    xp = {"gws": list(range(3, 11)), "players": forecasts}
    meta = {
        "generated_utc": "2026-09-01T15:57:51Z",
        "season": 2026,
        "model_version": "2026-07-24T16:47:08+00:00",
    }
    base = ops.PITCHSIDE_BASE
    return Session(
        {
            ops.FPL_BOOTSTRAP: Response(bootstrap),
            ops.FPL_FIXTURES: Response(fixtures),
            f"{base}/meta.json": [Response(meta), Response(meta)],
            f"{base}/xp.json": Response(xp),
            f"{base}/players.json": Response([]),
        }
    )


class TournamentOpsTests(unittest.TestCase):
    def test_dastan_h1_only_enters_universal_not_strategic(self):
        result = readiness()
        self.assertEqual(result["providers"]["dastan"]["h1"]["status"], "ENTERED")
        self.assertEqual(result["providers"]["dastan"]["strategic_h2_h8"]["status"], "NOT_ENTERED")
        self.assertIn("dastan", result["universal_h1_league"]["entrants"])

    def test_openfpl_is_explicit_training_dns(self):
        result = readiness()
        row = result["providers"]["openfpl"]
        self.assertEqual(row["h1"]["dns_code"], ops.DNS_TRAINING_NOT_READY)
        self.assertEqual(row["training_state"], "DEFERRED_BY_GOVERNANCE")

    def test_openfpl_floor_without_model_is_explicit_action_state(self):
        public, governance, internal, hashes, pitchside, openfpl, release = base_inputs()
        openfpl["state"] = "TRAINING_READY_NO_MODEL"
        openfpl["exact_rule_gameweek_count"] = 10
        result = ops.build_readiness(
            public, governance, internal,
            source_release=release,
            internal_surface_sha256=hashes,
            pitchside_capture=pitchside,
            openfpl_readiness=openfpl,
            private_base_release_tag="private",
            private_tournament_release_tag="supp",
        )
        self.assertEqual(result["providers"]["openfpl"]["h1"]["dns_code"], ops.DNS_TRAINING_READY_NO_MODEL)

    def test_pitchside_is_external_and_can_enter_h1_h8(self):
        result = readiness()
        row = result["providers"]["pitchside"]
        self.assertEqual(row["source"], "EXTERNAL_PREDEADLINE_CAPTURE")
        self.assertEqual(row["h1"]["status"], "ENTERED")
        self.assertEqual(row["strategic_h2_h8"]["status"], "ENTERED")

    def test_pitchside_capture_treats_u_as_no_forecast_expected(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ops.capture_pitchside(
                season="2026-2027",
                target_gameweek=3,
                expected_official_hash="c" * 64,
                current_official_hash="c" * 64,
                deadline=datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc),
                output=Path(tmp) / "capture.json",
                now=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                session=pitchside_session(),
            )
        self.assertEqual(result["health"], "HEALTHY")
        self.assertEqual(result["forecastable_player_count"], 2)
        self.assertEqual(result["official_unavailable_player_count"], 1)
        self.assertEqual(result["forecast_counts_by_horizon"]["1"], 2)
        self.assertEqual(result["unavailable_no_forecast_expected_by_horizon"]["1"], 1)
        self.assertEqual(result["missing_forecastable_ids_by_horizon"]["1"], [])
        rows = [r for r in result["surface"]["rows"] if r["horizon"] == 1]
        unavailable = next(r for r in rows if r["element_id"] == 2)
        self.assertEqual(unavailable["coverage_status"], "NO_FORECAST")
        self.assertEqual(unavailable["coverage_reason"], "OFFICIAL_UNAVAILABLE_NO_FORECAST_EXPECTED")

    def test_pitchside_missing_active_player_is_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ops.capture_pitchside(
                season="2026-2027",
                target_gameweek=3,
                expected_official_hash="c" * 64,
                current_official_hash="c" * 64,
                deadline=datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc),
                output=Path(tmp) / "capture.json",
                now=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                session=pitchside_session(missing_active=True),
            )
        self.assertEqual(result["health"], "INCOMPLETE")
        self.assertEqual(result["dns_code"], ops.DNS_INCOMPLETE_UNIVERSE)
        self.assertEqual(result["missing_forecastable_ids_by_horizon"]["1"], [3])

    def test_pitchside_exact_official_hash_mismatch_fails_before_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = ops.capture_pitchside(
                season="2026-2027",
                target_gameweek=3,
                expected_official_hash="c" * 64,
                current_official_hash="d" * 64,
                deadline=datetime(2026, 9, 4, 17, 30, tzinfo=timezone.utc),
                output=Path(tmp) / "capture.json",
                now=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
                session=Session({}),
            )
        self.assertEqual(result["dns_code"], ops.DNS_OFFICIAL_HASH)
        self.assertIsNone(result["surface"])

    def test_tournament_ready_candidate_has_no_observation_number(self):
        result = readiness()
        self.assertTrue(result["tournament_ready"])
        self.assertEqual(result["classification"], ops.PROSPECTIVE_READY_CANDIDATE)
        self.assertIsNone(result["prospective_observation_number"])
        self.assertTrue(result["production"]["serving_architecture_unchanged"])

    def test_public_readiness_does_not_embed_raw_provider_surface(self):
        result = readiness()
        encoded = json.dumps(result)
        self.assertNotIn('"rows"', encoded)
        self.assertNotIn('"expected_points"', encoded)

    def test_market_unavailable_does_not_block_ready_candidate(self):
        result = readiness()
        self.assertTrue(result["tournament_ready"])
        self.assertEqual(result["market_benchmark"]["status"], "UNAVAILABLE")

    def test_market_cannot_be_projection_entrant(self):
        public, governance, internal, hashes, pitchside, openfpl, release = base_inputs()
        with self.assertRaises(ops.TournamentContractError):
            ops.build_readiness(
                public, governance, internal,
                source_release=release,
                internal_surface_sha256=hashes,
                pitchside_capture=pitchside,
                openfpl_readiness=openfpl,
                private_base_release_tag="private",
                private_tournament_release_tag="supp",
                market_benchmark={"status": "AVAILABLE", "projection_league_entrant": True},
            )

    def test_gw2_is_retained_noncanonical(self):
        result = readiness(gameweek=2)
        self.assertEqual(result["classification"], ops.GW2_CLASSIFICATION)
        self.assertFalse(result["tournament_ready"])
        self.assertFalse(result["gw2_policy"]["canonical_win_loss_allowed"])

    def test_latest_valid_predeadline_candidate_wins(self):
        a = readiness()
        b = json.loads(json.dumps(a))
        a["common_seal"]["snapshot_frozen_at"] = "2026-09-01T12:00:00+00:00"
        b["common_seal"]["snapshot_frozen_at"] = "2026-09-04T15:00:00+00:00"
        selected = ops.select_latest_valid_common_seal([a, b], gameweek=3)
        self.assertEqual(selected["common_seal"]["snapshot_frozen_at"], "2026-09-04T15:00:00+00:00")

    def test_postdeadline_or_not_ready_candidate_cannot_displace_valid(self):
        good = readiness()
        late = json.loads(json.dumps(good))
        late["common_seal"]["snapshot_frozen_at"] = "2026-09-04T18:00:00+00:00"
        not_ready = json.loads(json.dumps(good))
        not_ready["tournament_ready"] = False
        not_ready["common_seal"]["snapshot_frozen_at"] = "2026-09-04T16:00:00+00:00"
        selected = ops.select_latest_valid_common_seal([good, late, not_ready], gameweek=3)
        self.assertIs(selected, good)

    def test_canonicalization_requires_deadline_passed(self):
        candidate = readiness()
        with self.assertRaises(ops.TournamentContractError):
            ops.canonicalize_selected_observation(
                candidate,
                observation_number=1,
                selected_at=datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc),
            )
        selected = ops.canonicalize_selected_observation(
            candidate,
            observation_number=1,
            selected_at=datetime(2026, 9, 4, 17, 31, tzinfo=timezone.utc),
        )
        self.assertEqual(selected["classification"], ops.CANONICAL_PROSPECTIVE_OBSERVATION)
        self.assertEqual(selected["prospective_observation_number"], 1)
        self.assertEqual(selected["selection_rule"], "LAST_VALID_COMMON_PREDEADLINE_SEAL")

    def test_serving_authority_change_fails_closed(self):
        public, governance, internal, hashes, pitchside, openfpl, release = base_inputs()
        public["serving_provider_by_horizon"]["3"] = "apex_proprietary"
        with self.assertRaises(ops.TournamentContractError):
            ops.build_readiness(
                public, governance, internal,
                source_release=release,
                internal_surface_sha256=hashes,
                pitchside_capture=pitchside,
                openfpl_readiness=openfpl,
                private_base_release_tag="private",
                private_tournament_release_tag="supp",
            )

    def test_internal_provider_omission_fails_closed(self):
        public, governance, internal, hashes, pitchside, openfpl, release = base_inputs()
        governance["qualification_matrix"] = [r for r in governance["qualification_matrix"] if r["provider_id"] != "dastan"]
        with self.assertRaises(ops.TournamentContractError):
            ops.build_readiness(
                public, governance, internal,
                source_release=release,
                internal_surface_sha256=hashes,
                pitchside_capture=pitchside,
                openfpl_readiness=openfpl,
                private_base_release_tag="private",
                private_tournament_release_tag="supp",
            )

    def test_season_is_not_hardcoded(self):
        result = readiness(season="2027-2028")
        self.assertEqual(result["season"], "2027-2028")
        self.assertEqual(result["providers"]["airsenal"]["h1"]["status"], "ENTERED")

    def test_reliability_tracks_dns_rate(self):
        a = readiness()
        b = json.loads(json.dumps(a))
        b["providers"]["dastan"]["h1"] = {"status": "DNS", "dns_code": ops.DNS_UPSTREAM, "reasons": []}
        summary = ops.reliability_summary([a, b])
        self.assertEqual(summary["providers"]["dastan"]["submission_rate"], 0.5)
        self.assertEqual(summary["providers"]["dastan"]["dns_counts"][ops.DNS_UPSTREAM], 1)

    def test_specialist_scores_only_sealed_components(self):
        s = surface("dastan", (1,), with_minutes=True)
        outcome = {
            "actual_points": {"1": 2, "2": 5, "3": 0},
            "actual_minutes": {"1": 90, "2": 0, "3": 60},
            "actual_started": {"1": 1, "2": 0, "3": 1},
        }
        result = ops.specialist_metrics(s, outcome, gameweek=3)
        self.assertEqual(result["minutes"]["status"], "SCORED")
        self.assertEqual(result["appearance_probability"]["status"], "SCORED")
        self.assertEqual(result["start_probability"]["status"], "SCORED")
        self.assertTrue(result["component_policy"]["no_hindsight_imputation"])

    def test_selection_before_cutoff_returns_none_when_required(self):
        candidate = readiness()
        selected = ops.select_latest_valid_common_seal(
            [candidate],
            gameweek=3,
            as_of=datetime(2026, 9, 4, 17, 0, tzinfo=timezone.utc),
            require_cutoff_passed=True,
        )
        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
