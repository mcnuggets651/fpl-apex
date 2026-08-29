from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest


def _load_dastan_shadow_module():
    path = Path(__file__).resolve().parents[1] / "scripts" / "acquire_dastan_shadow.py"
    spec = importlib.util.spec_from_file_location("apex_test_acquire_dastan_shadow", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dastan_shadow = _load_dastan_shadow_module()


def test_dastan_subprocess_receives_and_enforces_timeout(monkeypatch):
    observed = {}

    def fake_run(command, *, check, env, timeout):
        observed.update(
            {
                "command": command,
                "check": check,
                "env": env,
                "timeout": timeout,
            }
        )
        raise subprocess.TimeoutExpired(command, timeout)

    monkeypatch.setattr(dastan_shadow.subprocess, "run", fake_run)

    with pytest.raises(subprocess.TimeoutExpired):
        dastan_shadow._run(
            ["python", "worker.py"],
            env={"A": "B"},
            timeout_seconds=12.5,
        )

    assert observed["command"] == ["python", "worker.py"]
    assert observed["check"] is True
    assert observed["env"] == {"A": "B"}
    assert observed["timeout"] == 12.5


def test_remaining_budget_fails_closed_after_deadline(monkeypatch):
    monkeypatch.setattr(dastan_shadow.time, "monotonic", lambda: 100.0)
    with pytest.raises(TimeoutError, match="total time budget"):
        dastan_shadow._remaining_seconds(99.0)
    assert dastan_shadow._remaining_seconds(112.0) == 12.0
