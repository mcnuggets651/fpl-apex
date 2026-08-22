from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _run_apex_module():
    path = ROOT / "scripts" / "run_apex.py"
    spec = importlib.util.spec_from_file_location("run_apex_identity_contract", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_certified_run_uses_run_scoped_airsenal_identity_witness(monkeypatch):
    module = _run_apex_module()
    run_scoped = "data/generated/runs/12345/airsenal.csv"
    monkeypatch.setenv("AIRSENAL_PROJECTIONS_CSV", run_scoped)
    assert module._identity_airsenal_path(None) == run_scoped


def test_explicit_airsenal_identity_witness_overrides_environment(monkeypatch):
    module = _run_apex_module()
    monkeypatch.setenv("AIRSENAL_PROJECTIONS_CSV", "data/generated/runs/old/airsenal.csv")
    assert module._identity_airsenal_path("/tmp/sealed/airsenal.csv") == "/tmp/sealed/airsenal.csv"


def test_identity_gate_surfaces_machine_readable_blockers(tmp_path):
    module = _run_apex_module()
    report = tmp_path / "player_identity_audit.json"
    report.write_text(
        json.dumps(
            {
                "ready": False,
                "blockers": [
                    "airsenal row 17: player_id=10 name conflict source='Beta' official='Alpha'",
                    "airsenal is missing 1 Official FPL player IDs: [40]",
                ],
            }
        ),
        encoding="utf-8",
    )
    detail = module._gate_blocker_details(report)
    assert "name conflict" in detail
    assert "missing 1 Official FPL player IDs" in detail


def test_identity_audit_is_run_scoped_and_checks_staged_recommendation():
    source = (ROOT / "scripts" / "run_apex.py").read_text(encoding="utf-8")
    assert 'identity_report_path = output_dir / "player_identity_audit.json"' in source
    assert 'identity_csv_path = output_dir / "player_identity_audit.csv"' in source
    assert '"--recommendation"' in source
    assert 'str(output_dir / "apex_recommendation_latest.json")' in source
    assert '"--output"' in source
    assert 'str(identity_report_path)' in source
    assert '"--csv"' in source
    assert 'str(identity_csv_path)' in source
    assert "report_path=identity_report_path" in source
