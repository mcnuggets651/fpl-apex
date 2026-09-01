from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import yaml

SCRIPT = Path(__file__).parents[1] / "scripts" / "apex_v2_shadow_provider_ops.py"
spec = importlib.util.spec_from_file_location("shadow_ops_unittest", SCRIPT)
shadow_ops = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = shadow_ops
spec.loader.exec_module(shadow_ops)


class Response:
    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.content = json.dumps(payload).encode()
        self.response = self

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            err = shadow_ops.requests.HTTPError(f"status {self.status_code}")
            err.response = self
            raise err


class Session:
    def __init__(self, mapping):
        self.mapping, self.calls = mapping, []

    def get(self, url, timeout):
        self.calls.append(url)
        value = self.mapping[url]
        return value.pop(0) if isinstance(value, list) else value


def config():
    return {
        "providers": [
            {"id": "airsenal", "role": "CHAMPION", "serve_authorized": True, "requested_horizons": list(range(1, 9))},
            {"id": "dastan", "role": "SHADOW", "serve_authorized": False, "requested_horizons": [1]},
            {"id": "pitchside", "role": "SHADOW", "serve_authorized": False, "requested_horizons": list(range(1, 9))},
            {"id": "apex_proprietary", "role": "SHADOW", "serve_authorized": False, "requested_horizons": list(range(1, 9))},
            {"id": "openfpl", "role": "SHADOW", "serve_authorized": False, "requested_horizons": [1]},
        ]
    }


def lock():
    return {"sources": {
        "dastan": {"repository": "qazybekb/smartplayfpl-dastan", "commit": "1" * 40},
        "openfpl": {"repository": "daniegr/OpenFPL", "commit": "2" * 40},
        "openfpl_current_history": {"repository": "vaastav/Fantasy-Premier-League", "commit": "3" * 40},
    }}


class ShadowProviderOpsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_runtime_boundary_keeps_dastan_and_champion(self):
        source = self.root / "config.yaml"
        output = self.root / "runtime.yaml"
        report = self.root / "report.json"
        source.write_text(yaml.safe_dump(config()))
        result = shadow_ops.derive_runtime_config(source, output, report)
        ids = [p["id"] for p in yaml.safe_load(output.read_text())["providers"]]
        self.assertEqual(ids, ["airsenal", "dastan", "apex_proprietary"])
        self.assertEqual(result["serving_provider"], "airsenal")
        self.assertEqual(result["production_influence"], "NONE")
        self.assertFalse(result["auto_promotion"])

    def _pitch_session(self, *, unavailable=False, missing_active=False, horizons=8):
        base = shadow_ops.PITCHSIDE_BASE
        elements = [
            {"id": 1, "code": 101, "status": "a"},
            {"id": 2, "code": 202, "status": "u" if unavailable else "a"},
            {"id": 3, "code": 303, "status": "d"},
        ]
        gws = list(range(3, 3 + horizons))
        xp = {"101": [1.0] * horizons}
        if not unavailable:
            xp["202"] = [2.0] * horizons
        if not missing_active:
            xp["303"] = [3.0] * horizons
        meta = {"generated_utc": "2026-09-01T03:00:00Z", "model_version": "v1"}
        players = [{"player_code": e["code"], "status": e["status"]} for e in elements]
        return Session({
            shadow_ops.FPL_BOOTSTRAP: Response({"events": [{"id": 3, "deadline_time": "2026-09-04T17:30:00Z"}], "elements": elements}),
            shadow_ops.FPL_FIXTURES: Response([]),
            f"{base}/meta.json": [Response(meta), Response(meta)],
            f"{base}/xp.json": Response({"gws": gws, "players": xp}),
            f"{base}/players.json": Response(players),
        })

    def test_pitchside_unavailable_identity_is_not_missing_forecast(self):
        result = shadow_ops.pitchside_health(
            report=self.root / "pitch.json",
            now=datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc),
            session=self._pitch_session(unavailable=True),
        )
        self.assertEqual(result["health"], "HEALTHY")
        self.assertEqual(result["decision_universe_coverage_ratio"], 1.0)
        self.assertEqual(result["missing_full_universe_ids"], [2])
        self.assertEqual(result["missing_decision_universe_ids"], [])
        self.assertEqual(result["excluded_unavailable_classification"], "NO_FORECAST_EXPECTED")
        self.assertTrue(result["h1_available"])
        self.assertTrue(result["h2_h8_available"])

    def test_pitchside_missing_active_identity_is_incomplete(self):
        result = shadow_ops.pitchside_health(
            report=self.root / "pitch.json",
            now=datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc),
            session=self._pitch_session(missing_active=True),
        )
        self.assertEqual(result["health"], "INCOMPLETE")
        self.assertEqual(result["missing_decision_universe_ids"], [3])

    def test_pitchside_h1_and_strategic_horizons_are_independent(self):
        result = shadow_ops.pitchside_health(
            report=self.root / "pitch.json",
            now=datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc),
            session=self._pitch_session(horizons=1),
        )
        self.assertEqual(result["health"], "HEALTHY")
        self.assertTrue(result["h1_available"])
        self.assertFalse(result["h2_h8_available"])
        self.assertEqual(result["qualified_horizons"], [1])

    def _openfpl_inputs(self):
        policy = self.root / "policy.yaml"
        lock_path = self.root / "lock.json"
        policy.write_text(yaml.safe_dump({
            "minimum_exact_rule_gameweeks": 10,
            "training_label_seasons": ["2026-27"],
            "model_contract": {"serve_authorized": False},
        }))
        lock_path.write_text(json.dumps(lock()))
        return policy, lock_path

    def _openfpl_session(self, n, sha="a" * 40):
        repo = "vaastav/Fantasy-Premier-League"
        events = [
            {"id": i, "deadline_time": "2026-08-01T18:30:00Z", "finished": True, "data_checked": True}
            for i in range(1, 12)
        ] + [{"id": 12, "deadline_time": "2026-11-20T18:30:00Z", "finished": False, "data_checked": False}]
        files = [{"name": f"gw{i}.csv", "sha": f"sha{i}", "size": i} for i in range(1, n + 1)]
        return Session({
            shadow_ops.FPL_BOOTSTRAP: Response({"events": events, "elements": []}),
            shadow_ops.FPL_FIXTURES: Response([]),
            f"{shadow_ops.GITHUB_API}/repos/{repo}/commits/master": Response({"sha": sha, "commit": {"committer": {"date": "2026-11-01T00:00:00Z"}}}),
            f"{shadow_ops.GITHUB_API}/repos/{repo}/contents/data/2026-27/gws?ref={sha}": Response(files),
        })

    def test_openfpl_advances_from_immutable_live_commit(self):
        policy, lock_path = self._openfpl_inputs()
        sha = "b" * 40
        result = shadow_ops.openfpl_readiness(
            policy_path=policy,
            lock_path=lock_path,
            report=self.root / "openfpl.json",
            now=datetime(2026, 11, 1, tzinfo=timezone.utc),
            session=self._openfpl_session(10, sha),
        )
        self.assertEqual(result["state"], "READY_FOR_SHADOW_BUILD")
        self.assertEqual(result["observed_history_commit"], sha)
        self.assertTrue(result["immutable_history_observation"])
        self.assertFalse(result["auto_build"])
        self.assertFalse(result["auto_promotion"])

    def test_openfpl_below_floor_is_dns_not_provider_error(self):
        policy, lock_path = self._openfpl_inputs()
        result = shadow_ops.openfpl_readiness(
            policy_path=policy,
            lock_path=lock_path,
            report=self.root / "openfpl.json",
            now=datetime(2026, 11, 1, tzinfo=timezone.utc),
            session=self._openfpl_session(9),
        )
        self.assertEqual(result["health"], "HEALTHY")
        self.assertEqual(result["state"], "TRAINING_NOT_READY")
        self.assertEqual(result["dns_reason"], "TRAINING_NOT_READY")

    def test_dastan_retries_transient_only(self):
        lock_path = self.root / "lock.json"
        lock_path.write_text(json.dumps(lock()))
        results = iter([
            SimpleNamespace(returncode=1, stdout="", stderr="fatal: could not resolve host github.com"),
            SimpleNamespace(returncode=0, stdout="ok", stderr=""),
        ])
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            return next(results)

        result = shadow_ops.run_dastan_with_retry(
            runner=Path("runner.py"), expected_official_hash="abc", lock_path=lock_path,
            report=self.root / "dastan.json", sleeper=lambda _: None, run_command=run,
        )
        self.assertEqual(result["health"], "HEALTHY")
        self.assertEqual(result["attempt_count"], 2)
        self.assertEqual(len(calls), 2)

    def test_dastan_does_not_retry_logical_failure(self):
        lock_path = self.root / "lock.json"
        lock_path.write_text(json.dumps(lock()))
        calls = []

        def run(command, **kwargs):
            calls.append(command)
            return SimpleNamespace(returncode=1, stdout="", stderr="Official hash mismatch")

        result = shadow_ops.run_dastan_with_retry(
            runner=Path("runner.py"), expected_official_hash="abc", lock_path=lock_path,
            report=self.root / "dastan.json", sleeper=lambda _: None, run_command=run,
        )
        self.assertEqual(result["failure_class"], "PROVIDER_LOGIC_OR_INVARIANT_FAILURE")
        self.assertEqual(len(calls), 1)

    def test_http_retry_does_not_retry_404(self):
        session = Session({"x": Response({}, 404)})
        client = shadow_ops.RetryHttp(session, attempts=4, base_sleep=0)
        with self.assertRaises(shadow_ops.requests.HTTPError):
            client.get("x")
        self.assertEqual(len(session.calls), 1)


if __name__ == "__main__":
    unittest.main()
