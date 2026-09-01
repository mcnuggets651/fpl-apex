from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

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


def test_runtime_config_externalises_only_external_diagnostics(tmp_path):
    source = tmp_path / "frozen.yaml"
    output = tmp_path / "runtime.yaml"
    report = tmp_path / "report.json"
    source.write_text(yaml.safe_dump(_config(), sort_keys=False))
    result = shadow_ops.derive_runtime_config(source, output, report)
    runtime = yaml.safe_load(output.read_text())
    assert [p["id"] for p in runtime["providers"]] == ["airsenal", "dastan", "apex_proprietary"]
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
            item = value.pop(0)
            return item
        return value


def _openfpl_files(n):
    return [{"name": f"gw{i}.csv", "sha": f"sha{i}", "size": 100 + i} for i in range(1, n + 1)]


def _openfpl_session(n):
    repo = "vaastav/Fantasy-Premier-League"
    bootstrap = {
        "events": [
            *[
                {
                    "id": i,
                    "deadline_time": f"2026-10-{min(i, 28):02d}T18:30:00Z",
                    "finished": True,
                    "data_checked": True,
                }
                for i in range(1, 12)
            ],
            {
                "id": 12,
                "deadline_time": "2026-11-20T18:30:00Z",
                "finished": False,
                "data_checked": False,
            },
        ],
        "elements": [],
    }
    return Session(
        {
            shadow_ops.FPL_BOOTSTRAP: Response(bootstrap),
            shadow_ops.FPL_FIXTURES: Response([]),
            f"https://api.github.com/repos/{repo}/contents/data/2026-27/gws": Response(_openfpl_files(n)),
        }
    )


def _openfpl_inputs(tmp_path):
    policy = {
        "minimum_exact_rule_gameweeks": 10,
        "training_label_seasons": ["2026-27"],
        "model_contract": {"serve_authorized": False},
    }
    lock = {
        "sources": {
            "openfpl": {"repository": "daniegr/OpenFPL", "commit": "abc"},
            "openfpl_current_history": {
                "repository": "vaastav/Fantasy-Premier-League",
                "commit": "def",
                "coverage_note": "GW1 only",
            },
        }
    }
    pp, lp, out = tmp_path / "policy.yaml", tmp_path / "lock.json", tmp_path / "out.json"
    pp.write_text(yaml.safe_dump(policy))
    lp.write_text(json.dumps(lock))
    return pp, lp, out


def test_openfpl_is_governance_deferred_not_broken(tmp_path):
    pp, lp, out = _openfpl_inputs(tmp_path)
    result = shadow_ops.openfpl_readiness(
        policy_path=pp,
        lock_path=lp,
        report=out,
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
        session=_openfpl_session(9),
    )
    assert result["health"] == "HEALTHY"
    assert result["state"] == "DEFERRED_BY_GOVERNANCE"
    assert result["exact_rule_gameweek_count"] == 9
    assert result["history_remaining_to_floor"] == 1
    assert result["model_export_expected_in_frozen_v2"] is False
    assert result["serve_authorized"] is False
    assert result["production_influence"] == "NONE"


def test_openfpl_readiness_advances_at_governed_floor_without_auto_promotion(tmp_path):
    pp, lp, out = _openfpl_inputs(tmp_path)
    result = shadow_ops.openfpl_readiness(
        policy_path=pp,
        lock_path=lp,
        report=out,
        now=datetime(2026, 11, 1, tzinfo=timezone.utc),
        session=_openfpl_session(10),
    )
    assert result["health"] == "HEALTHY"
    assert result["state"] == "READY_FOR_SHADOW_BUILD"
    assert result["exact_rule_gameweek_count"] == 10
    assert result["auto_build"] is False
    assert result["auto_promotion"] is False
    assert result["serve_authorized"] is False


def _pitchside_session(*, generated="2026-09-01T03:00:00Z", missing=False):
    base = shadow_ops.PITCHSIDE_BASE
    elements = [{"id": 1, "code": 101}, {"id": 2, "code": 202}]
    bootstrap = {
        "events": [{"id": 3, "deadline_time": "2026-09-04T17:30:00Z"}],
        "elements": elements,
    }
    xp_players = {"101": [3.0], "202": [None if missing else 4.0]}
    meta = {"generated_utc": generated, "season": 2026, "model_version": "v1"}
    return Session(
        {
            shadow_ops.FPL_BOOTSTRAP: Response(bootstrap),
            shadow_ops.FPL_FIXTURES: Response([]),
            f"{base}/meta.json": [Response(meta), Response(meta)],
            f"{base}/xp.json": Response({"gws": [3], "players": xp_players}),
            f"{base}/players.json": Response([]),
        }
    )


def test_pitchside_pre_attempt_snapshot_can_be_healthy_when_fresh_and_complete(tmp_path):
    # Regression for run 33469824474: external publication before Apex's run
    # is not itself a fault; max-age + coverage are the correct gates.
    now = datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc)
    result = shadow_ops.pitchside_health(
        report=tmp_path / "p.json", now=now, session=_pitchside_session()
    )
    assert result["health"] == "HEALTHY"
    assert result["source_generated_before_check"] is True
    assert result["coverage_ratio"] == 1.0


def test_pitchside_missing_official_forecast_is_incomplete(tmp_path):
    now = datetime(2026, 9, 1, 4, 49, tzinfo=timezone.utc)
    result = shadow_ops.pitchside_health(
        report=tmp_path / "p.json", now=now, session=_pitchside_session(missing=True)
    )
    assert result["health"] == "INCOMPLETE"
    assert result["missing_official_ids"] == [2]


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
