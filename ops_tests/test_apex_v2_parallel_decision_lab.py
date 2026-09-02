from __future__ import annotations

import inspect
import re
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts import apex_v2_decision_lab_parallel as parallel


CONTROL_SHA = "a" * 40
DEADLINE = "2026-09-04T17:30:00+00:00"


def _players():
    positions = ["GK", "GK"] + ["DEF"] * 5 + ["MID"] * 5 + ["FWD"] * 3
    return [
        {
            "element_id": index + 1,
            "web_name": f"P{index + 1}",
            "team_id": (index % 5) + 1,
            "position": position,
            "price_tenths": 50,
            "status": "a",
            "can_transact": True,
        }
        for index, position in enumerate(positions)
    ]


def _official():
    return {
        "schema_version": 1,
        "season": "2026-2027",
        "acquired_at": "2026-09-02T10:00:00+00:00",
        "source_hash": "official-hash",
        "players": _players(),
        "fixtures": [],
        "deadlines": {"3": DEADLINE},
    }


def _surface(provider_id: str, horizons: range):
    rows = []
    for horizon in horizons:
        for player in _players():
            rows.append(
                {
                    "element_id": player["element_id"],
                    "gameweek": 2 + horizon,
                    "horizon": horizon,
                    "expected_points": 3.0 + player["element_id"] / 100.0,
                    "expected_minutes": 75.0,
                    "p_appearance": 0.95,
                    "p_start": 0.85,
                    "p_60": 0.8,
                    "coverage_status": "FORECAST",
                }
            )
    return {
        "schema_version": 1,
        "provider_id": provider_id,
        "provider_version": f"{provider_id}-v1",
        "generated_at": "2026-09-02T10:00:00+00:00",
        "season": "2026-2027",
        "source_snapshot": "official-hash",
        "scoring_rules_version": "fpl-2026-27-v1",
        "supported_horizons": list(horizons),
        "runtime_dependencies": [],
        "rows": rows,
    }


def _context():
    surfaces = {
        "airsenal": _surface("airsenal", range(1, 9)),
        "apex_proprietary": _surface("apex_proprietary", range(1, 9)),
        "dastan": _surface("dastan", range(1, 2)),
    }
    hashes = {provider: f"hash-{provider}" for provider in surfaces}
    readiness = {
        "season": "2026-2027",
        "target_gameweek": 3,
        "readiness_sha256": "readiness-hash",
        "tournament_ready": True,
        "production_influence": "NONE",
        "production": {"serving_provider_by_horizon": {"1": "airsenal"}},
        "universal_h1_league": {
            "entrants": ["airsenal", "apex_proprietary", "dastan"]
        },
        "providers": {
            provider: {"artifact_sha256": hashes[provider]} for provider in surfaces
        },
        "common_seal": {
            "eligible_common_predeadline_candidate": True,
            "run_id": "33590896695-1",
            "public_attempt_id": "public-attempt",
            "candidate_release_tag": "apex-v2/tournament-candidate/2026-2027/33590896695-1",
            "snapshot_id": "snapshot",
            "official_snapshot_sha256": "official-snapshot-sha",
            "deadline": DEADLINE,
        },
    }
    squad = list(range(1, 16))
    private_attempt = {
        "canonical_forecast": {"official": _official()},
        "team_state": {
            "schema_version": 1,
            "entry_id": 63984,
            "published_gw": 2,
            "squad_ids": squad,
            "bank_tenths": 5,
            "free_transfers": 2,
            "purchase_prices_tenths": {str(pid): 50 for pid in squad},
            "selling_prices_tenths": {str(pid): 50 for pid in squad},
            "active_chip": None,
            "state_complete_for_transfers": True,
        },
        "system_decision": {
            "schema_version": 1,
            "squad_ids": squad,
            "xi_ids": [1, 3, 4, 5, 8, 9, 10, 11, 13, 14, 15],
            "captain_id": 13,
            "vice_captain_id": 8,
            "bench_order": [2, 6, 7, 12],
            "transfers_in": [],
            "transfers_out": [],
            "transfer_hits": 0,
            "decision_mode": "TRANSFER_HORIZON",
        },
        "transfer_plan": [{"horizon": horizon} for horizon in range(1, 9)],
    }
    return readiness, private_attempt, surfaces, hashes


class ParallelPlanTests(unittest.TestCase):
    def plan(self):
        readiness, private_attempt, surfaces, hashes = _context()
        return parallel._derive_plan(
            readiness=readiness,
            private_attempt=private_attempt,
            surfaces=surfaces,
            surface_hashes=hashes,
            public_files={},
            control_plane_sha=CONTROL_SHA,
        )

    def test_provider_neutral_plan_preserves_h1_only_dastan_truth(self):
        plan = self.plan()
        kinds_by_provider = {}
        for task in plan["tasks"]:
            kinds_by_provider.setdefault(task["provider_id"], set()).add(task["kind"])
        self.assertIn("PURE_PROVIDER_CONTIGUOUS_PLAN", kinds_by_provider["apex_proprietary"])
        self.assertNotIn("PURE_PROVIDER_CONTIGUOUS_PLAN", kinds_by_provider["dastan"])
        self.assertEqual(
            plan["experiment_matrix"]["dastan"]["pure_provider_plan"],
            "NOT_SUPPORTED_H1_ONLY_OR_INCOMPLETE_H2",
        )
        self.assertEqual(len(plan["tasks"]), 8)

    def test_plan_exposes_no_manager_player_ids(self):
        plan = self.plan()
        rendered = repr(plan)
        for forbidden_key in (
            "squad_ids",
            "xi_ids",
            "bench_order",
            "captain_id",
            "vice_captain_id",
            "element_id",
            "purchase_prices_tenths",
            "selling_prices_tenths",
        ):
            self.assertNotIn(forbidden_key, rendered)
        self.assertFalse(plan["decision_universe_player_ids_published"])

    def test_task_ids_are_deterministic_and_tag_safe(self):
        first = parallel._task_id("CHALLENGER_H1_AIRSENAL_H2_PLUS", "A Provider/With Spaces")
        second = parallel._task_id("CHALLENGER_H1_AIRSENAL_H2_PLUS", "A Provider/With Spaces")
        self.assertEqual(first, second)
        self.assertRegex(first, r"^[a-z0-9-]+(?:--[a-z0-9-]+)?$")
        tag = parallel._task_release_tag(
            season="2026-2027",
            run_id="run-1",
            control_plane_sha=CONTROL_SHA,
            task_id=first,
        )
        self.assertIn(CONTROL_SHA[:12], tag)

    def test_control_plane_revision_gets_distinct_staging_namespace(self):
        task_id = parallel._task_id("BASELINE_REPRODUCTION")
        first = parallel._task_release_tag(
            season="2026-2027",
            run_id="run-1",
            control_plane_sha="a" * 40,
            task_id=task_id,
        )
        second = parallel._task_release_tag(
            season="2026-2027",
            run_id="run-1",
            control_plane_sha="b" * 40,
            task_id=task_id,
        )
        self.assertNotEqual(first, second)

    def test_task_fingerprint_changes_with_control_plane(self):
        plan = self.plan()
        task = plan["tasks"][0]
        first = parallel._task_fingerprint(plan, task)
        changed = dict(plan)
        changed["control_plane_sha"] = "b" * 40
        second = parallel._task_fingerprint(changed, task)
        self.assertNotEqual(first, second)


class ParallelSafetyTests(unittest.TestCase):
    def test_task_release_must_be_published_and_sealed_predeadline(self):
        release = {"published_at": "2026-09-04T16:00:00+00:00"}
        payload = {"sealed_at": "2026-09-04T15:59:00+00:00"}
        self.assertTrue(parallel._release_predeadline(release, payload, DEADLINE))
        release["published_at"] = "2026-09-04T18:00:00+00:00"
        self.assertFalse(parallel._release_predeadline(release, payload, DEADLINE))

    def test_assembly_fails_closed_when_required_task_is_missing(self):
        plan = {
            "source": {
                "season": "2026-2027",
                "run_id": "run-1",
                "candidate_readiness_sha256": "ready",
                "deadline": DEADLINE,
            },
            "tasks": [
                {
                    "task_id": "baseline",
                    "kind": "BASELINE_REPRODUCTION",
                    "provider_id": "airsenal",
                }
            ],
        }
        with self.assertRaises(RuntimeError):
            parallel._assemble_one(
                private_store=object(),
                private_releases=[],
                plan=plan,
                private_attempt={},
                surfaces={},
                surface_hashes={},
                public_files={},
                control_plane_sha=CONTROL_SHA,
                root=Path("/tmp/not-used"),
            )

    def test_full_optimizer_is_centralized_to_one_call_site(self):
        source = inspect.getsource(parallel._optimise_once)
        self.assertEqual(source.count("optimise_transfer_horizon("), 1)
        solve_source = inspect.getsource(parallel._solve_task_from_context)
        self.assertNotIn("optimise_transfer_horizon(", solve_source)
        self.assertNotIn("for task in", solve_source)

    def test_new_task_start_has_explicit_deadline_gate(self):
        source = inspect.getsource(parallel.solve_task)
        self.assertIn("if _utc_now() >= deadline", source)
        self.assertIn("finished after deadline and will not be sealed", source)

    def test_parallel_contract_never_authorizes_serving(self):
        source = Path("scripts/apex_v2_decision_lab_parallel.py").read_text(encoding="utf-8")
        self.assertIn('"production_influence": "NONE"', source)
        self.assertIn('"serving_authorized": False', source)
        self.assertIn('"automatic_serving_change": False', source)


class ParallelWorkflowContractTests(unittest.TestCase):
    def test_workflow_is_matrix_bounded_private_and_read_only(self):
        text = Path(".github/workflows/apex-v2-decision-quality.yml").read_text(
            encoding="utf-8"
        )
        for needle in (
            "contents: read",
            "strategy:",
            "matrix: ${{ fromJSON(needs.prepare.outputs.matrix) }}",
            "max-parallel: 8",
            "--mode prepare",
            "--mode solve-task",
            "--mode assemble",
            "--mode postoutcome",
            "apex_v2_decision_lab_parallel.py",
            "APEX_V2_PRIVATE_REPO_TOKEN",
            parallel.FROZEN_APEX_SHA,
        ):
            self.assertIn(needle, text)
        for forbidden in (
            "contents: write",
            "apex-v2 acquire",
            "apex-v2 solve",
            "apex-v2 publish",
            "run_airsenal_worker.py",
            "acquire_dastan",
        ):
            self.assertNotIn(forbidden, text)

    def test_prepare_output_explicitly_checks_matrix_privacy(self):
        text = Path(".github/workflows/apex-v2-decision-quality.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn(".private_manager_state_in_matrix == false", text)


if __name__ == "__main__":
    unittest.main()
