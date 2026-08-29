from __future__ import annotations

import subprocess

import pytest

import scripts.acquire_dastan_shadow as dastan_shadow


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
