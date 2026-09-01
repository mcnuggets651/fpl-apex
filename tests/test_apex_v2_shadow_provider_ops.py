from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

SCRIPT = Path(__file__).parents[1] / "scripts" / "apex_v2_shadow_provider_ops.py"
spec = importlib.util.spec_from_file_location("shadow_ops", SCRIPT)
shadow_ops = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules[spec.name] = shadow_ops
spec.loader.exec_module(shadow_ops)


def _config():
    return {
        "schema_version": 1,
        "season": "2026-2027",
        "entry_id": 63984,
        "max_horizon": 8,
        "providers": [
            {"id": "airsenal", "role": "CHAMPION", "serve_authorized": True, "requested_horizons": list(range(1, 9))},
            {"id": "dastan", "role": "SHADOW", "serve_authorized": False, "requested_horizons": [1]},
            {"id": "pitchside", "role": "SHADOW", "serve_authorized": False, "requested_horizons": list(range(1, 9))},
            {"id": "apex_proprietary", "role": "SHADOW", "serve_authorized": False, "requested_horizons": list(range(1, 9))},
            {"id": "openfpl", "role": "SHADOW", "serve_authorized": False, "requested_horizons": [1]},
        ],
    }


def _lock():
    return {
        "sources": {
            "dastan": {"repository": "qazybekb/smartplayfpl-dastan", "commit": "1" * 40},
            "openfpl": {"repository": "daniegr/OpenFPL", "commit": "2" * 40},
            "openfpl_current_history": {
                "repository": "vaastav/Fantasy-Premier-League",
                "commit": "3" * 40,
                "coverage_note": "GW1 only",
            },
        }
    }


def test_runtime_config_externalises_only_external_diagnostics(tmp_path):
    source = tmp_path / "frozen.yaml"
    output = tmp_path / "runtime.yaml"
    report = tmp_path / "report.json"
    source.write_text(yaml.safe_dump(_config(), sort_keys=False))
    result = shadow_ops.derive_runtime_config(source, output, report)
    runtime = yaml.safe_load(output.read_text())
    assert [p["id"] for p in runtime["providers"]] == ["airsenal", "dastan", "apex_proprietary"]
    assert result["retained_shadow_providers"] == ["dastan", "apex_proprietary"]
    assert result["serving_provider"] == "airsenal"
    assert result["serving_horizons"] == list(range(1, 9))
    assert result["production_influence"] == "NONE"
    assert result["auto_promotion"] is False


def test_runtime_config_refuses_to_externalise_serving_provider(tmp_path):
    cfg = _config()
    next(p for p in cfg["providers"] if p["id"] == "pitchside")["serve_authorized"] = True
    source = tmp_path / "frozen.yaml"
    source.write_text(yaml.safe_dump(cfg, sort_keys=False))
    with pytest.raises(ValueError, match="serving-authorized"):
        shadow_ops.derive_runtime_config(source, tmp_path / "runtime.yaml", tmp_path / "report.json")


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
        if isinstance(value, list):
            return value.pop(0)
        return value


def _bootstrap(target=12):
    events = []
    for i in range(1, target):
        events.append({
            "id": i,
            "deadline_time": "2026-08-01T18:30:00Z",
            "finished": True,
            "data_checked": True,
        })
    events.append({
        "id": target,
        "deadline_time": "2026-11-20T18:30:00Z",
        "finished": False,
        "data_checked": False,
    })
    return {"events": events, "elements": []}


def _openfpl_files(n):
    return [{"name": f"gw{i}.csv", "sha": f"sha{i}", "size": 100 + i} for i in range(1, n + 1)]


def _openfpl_session(n, sha="a" * 40):
    repo = "vaastav/Fantasy-Premier-League"
    commit_url = f"{shadow_ops.GITHUB_API}/repos/{repo}/commits/master"
    content_url = f"{shadow_ops.GITHUB_API}/repos/{repo}/contents/data/2026-27/gws?ref={sha}"
    return Session({
        shadow_ops.FPL_BOOTSTRAP: Response(_bootstrap()),
        shadow_ops.FPL_FIXTURES: Response([]),
        commit_url: Response({"sha": sha, "commit": {"committer": {"date": "2026-11-01T00:00:00Z"}}}),
        content_url: Response(_openfpl_files(n)),
    })


def _openfpl_inputs(tmp_path):
    policy = {
        "minimum_exact_rule_gameweeks": 10,
        "training_label_seasons": ["2026-27"],
        "model_contract": {"serve_authorized": False},
    }
    pp, lp, out = tmp_path / "policy.yaml", tmp_path / "lock.json", tmp_path / "out.json"
    pp.write_text(yaml.safe_dump(policy))
    lp.write_text(json.dumps(_lock()))
    return pp, lp, out


def test_openfpl_is_training_not_ready_not_broken(tmp_path):
    pp, lp, out = _openfpl_inputs(tmp_path)
    result = shadow_ops.openfpl_readiness(
        policy_path=pp,
        lock_path=lp,
        report=out,
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
        session=_openfpl_session(9),
    )
    assert result["health"] == "HEALTHY"
    assert result["state"] == "TRAINING_NOT_READY"
    assert result["dns_reason"] == "TRAINING_NOT_READY"
    assert result["exact_rule_gameweek_count"] == 9
    assert result["history_remaining_to_floor"] == 1
    assert result["serve_authorized"] is False


def test_openfpl_resolves_live_branch_once_then_reads_exact_commit(tmp_path):
    pp, lp, out = _openfpl_inputs(tmp_path)
    sha = "b" * 40
    session = _openfpl_session(10, sha=sha)
    result = shadow_ops.openfpl_readiness(
        policy_path=pp,
        lock_path=lp,
        report=out,
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
        session=session,
    )
    assert result["health"] == "HEALTHY"
    assert result["state"] == "READY_FOR_SHADOW_BUILD"
    assert result["observed_history_commit"] == sha
    assert result["immutable_history_observation"] is True
    assert result["auto_build"] is False
    assert result["auto_promotion"] is False
    assert any(url.endswith(f"?ref={sha}") for url in session.calls)
    assert not any(url.endswith("/gws") for url in session.calls)


def test_openfpl_refuses_missing_frozen_history_source(tmp_path):
    pp, lp, out = _openfpl_inputs(tmp_path)
    lock = _lock()
    del lock["sources"]["openfpl_current_history"]
    lp.write_text(json.dumps(lock))
    with pytest.raises(ValueError, match="openfpl_current_history"):
        shadow_ops.openfpl_readiness(policy_path=pp, lock_path=lp, report=out, session=_openfpl_session(9))


def _pitchside_session(*, generated="2026-09-01T03:00:00Z", missing_id=None, unavailable_id=None, horizons=8):
    base = shadow_ops.PITCHSIDE_BASE
    elements = [
        {"id": 1, "code": 101, "status": "a"},
        {"id": 2, "code": 202, "status": "u" if unavailable_id == 2 else "a"},
        {"id": 3, "code": 303, "status": "d"},
    ]
    bootstrap = {
        "events": [{"id": 3, "deadline_time": "2026-09-04T17:30:00Z"}],
        "elements": elements,
    }
    gws = list(range(3, 3 + horizons))
    players = [
        {"player_code": 101, "status": "a"},
        {"player_code": 202, "status": "u" if unavailable_id == 2 else "a"},
        {"player_code": 303, "status": "d"},
    ]
    xp_players = {}
    for code, eid in [(101, 1), (202, 2), (303, 3)]:
        if eid == missing_id or eid == unavailable_id:
            continue
        xp_players[str(code)] = [float(eid)] * horizons
    meta = {"generated_utc": generated, "season": 2026, "model_version": "v1"}
    return Session({
        shadow_ops.FPL_BOOTSTRAP: Response(bootstrap),
        shadow_ops.FPL_FIXTURES: Response([]),
        f"{base}/meta.json": [Response(meta), Response(meta)],
        f"{base}/xp.json": Response({"gws": gws, "players": xp_players}),
        f"{base}/players.json": Response(players),
    })


def test_pitchside_unavailable_players_are_explicit_not_missing(tmp_path):
    now = datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc)
    result = shadow_ops.pitchside_health(
        report=tmp_path / "p.json",
        now=now,
        session=_pitchside_session(unavailable_id=2),
    )
    assert result["health"] == "HEALTHY"
    assert result["identity_universe_count"] == 3
    assert result["decision_universe_count"] == 2
    assert result["decision_universe_coverage_ratio"] == 1.0
    assert result["missing_decision_universe_ids"] == []
    assert result["missing_full_universe_ids"] == [2]
    assert result["excluded_unavailable_ids"] == [2]
    assert result["excluded_unavailable_classification"] == "NO_FORECAST_EXPECTED"
    assert result["h1_available"] is True
    assert result["h2_h8_available"] is True


def test_pitchside_missing_forecastable_player_is_incomplete(tmp_path):
    now = datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc)
    result = shadow_ops.pitchside_health(
        report=tmp_path / "p.json",
        now=now,
        session=_pitchside_session(missing_id=3),
    )
    assert result["health"] == "INCOMPLETE"
    assert result["missing_decision_universe_ids"] == [3]
    assert result["coverage_ratio"] < 1.0


def test_pitchside_horizon_contract_is_independent_of_h1(tmp_path):
    now = datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc)
    result = shadow_ops.pitchside_health(
        report=tmp_path / "p.json",
        now=now,
        session=_pitchside_session(horizons=1),
    )
    assert result["health"] == "HEALTHY"
    assert result["h1_available"] is True
    assert result["h2_h8_available"] is False
    assert result["qualified_horizons"] == [1]


def test_dastan_pin_preflight_verifies_exact_frozen_commit(tmp_path):
    lock = tmp_path / "lock.json"
    out = tmp_path / "d.json"
    lock.write_text(json.dumps(_lock()))
    source = _lock()["sources"]["dastan"]
    url = f"{shadow_ops.GITHUB_API}/repos/{source['repository']}/commits/{source['commit']}"
    session = Session({url: Response({"sha": source["commit"]})})
    result = shadow_ops.dastan_pin_health(lock_path=lock, report=out, session=session)
    assert result["health"] == "HEALTHY"
    assert result["observed_commit"] == source["commit"]


def test_dastan_retries_transient_network_failure_then_succeeds(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(_lock()))
    out = tmp_path / "d.json"
    results = iter([
        SimpleNamespace(returncode=1, stdout="", stderr="fatal: could not resolve host github.com"),
        SimpleNamespace(returncode=0, stdout="ok\n", stderr=""),
    ])
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return next(results)

    result = shadow_ops.run_dastan_with_retry(
        runner=Path("runner.py"),
        expected_official_hash="abc",
        lock_path=lock,
        report=out,
        max_attempts=2,
        sleeper=lambda _: None,
        run_command=run,
    )
    assert result["health"] == "HEALTHY"
    assert result["attempt_count"] == 2
    assert result["attempts"][0]["transient"] is True
    assert len(calls) == 2


def test_dastan_never_retries_logical_or_invariant_failure(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(_lock()))
    out = tmp_path / "d.json"
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout="", stderr="Official hash mismatch: expected abc observed def")

    result = shadow_ops.run_dastan_with_retry(
        runner=Path("runner.py"),
        expected_official_hash="abc",
        lock_path=lock,
        report=out,
        max_attempts=2,
        sleeper=lambda _: None,
        run_command=run,
    )
    assert result["health"] == "ERROR"
    assert result["failure_class"] == "PROVIDER_LOGIC_OR_INVARIANT_FAILURE"
    assert result["attempt_count"] == 1
    assert len(calls) == 1


def test_dastan_timeout_is_bounded_and_reported(tmp_path):
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps(_lock()))
    out = tmp_path / "d.json"

    def run(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    result = shadow_ops.run_dastan_with_retry(
        runner=Path("runner.py"),
        expected_official_hash="abc",
        lock_path=lock,
        report=out,
        max_attempts=1,
        wall_clock_seconds=1,
        sleeper=lambda _: None,
        run_command=run,
    )
    assert result["health"] == "ERROR"
    assert result["attempt_count"] == 1


def test_retry_retries_5xx_then_succeeds(monkeypatch):
    monkeypatch.setattr(shadow_ops.time, "sleep", lambda _: None)
    session = Session({"x": [Response({}, 503), Response({"ok": True}, 200)]})
    client = shadow_ops.RetryHttp(session, attempts=2, base_sleep=0)
    assert client.get("x").json() == {"ok": True}
    assert len(session.calls) == 2


def test_retry_does_not_retry_permanent_404(monkeypatch):
    monkeypatch.setattr(shadow_ops.time, "sleep", lambda _: None)
    session = Session({"x": Response({}, 404)})
    client = shadow_ops.RetryHttp(session, attempts=4, base_sleep=0)
    with pytest.raises(shadow_ops.requests.HTTPError):
        client.get("x")
    assert len(session.calls) == 1


def test_atomic_json_leaves_no_partial_temp(tmp_path):
    out = tmp_path / "x.json"
    shadow_ops._atomic_json(out, {"ok": True})
    assert json.loads(out.read_text()) == {"ok": True}
    assert not (tmp_path / "x.json.tmp").exists()
