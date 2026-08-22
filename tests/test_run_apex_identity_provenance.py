from __future__ import annotations

import importlib.util
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
