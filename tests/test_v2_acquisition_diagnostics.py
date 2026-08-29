from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

import apex.cli as cli
import apex.runtime.acquire as acquire_runtime


runner = CliRunner()


def test_acquire_failure_defaults_to_uploaded_diagnostics_directory(
    tmp_path: Path,
    monkeypatch,
):
    def fail(*args, **kwargs):
        raise acquire_runtime.AcquisitionStageError(
            "team_state",
            RuntimeError("privacy-safe authenticated manager-state failure"),
        )

    monkeypatch.setattr(acquire_runtime, "acquire_and_freeze", fail)
    monkeypatch.chdir(tmp_path)

    result = runner.invoke(
        cli.app,
        [
            "acquire",
            "--config",
            "config/apex_v2.yaml",
            "--run-id",
            "run-1",
            "--code-sha",
            "abc123",
            "--run-started-at",
            "2026-08-29T19:00:00+00:00",
        ],
    )

    assert result.exit_code == 1
    failure = tmp_path / "artifacts/v2/diagnostics/acquisition_failure.json"
    assert failure.is_file()
    payload = json.loads(failure.read_text(encoding="utf-8"))
    assert payload["stage"] == "team_state"
    assert payload["cause_type"] == "RuntimeError"
    assert payload["cause_message"] == "privacy-safe authenticated manager-state failure"
    assert payload["run_id"] == "run-1"
    assert payload["code_sha"] == "abc123"
