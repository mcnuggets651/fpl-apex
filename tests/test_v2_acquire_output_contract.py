from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import apex.cli as cli
import apex.runtime.acquire as acquire_runtime


runner = CliRunner()


def _base_acquire_args() -> list[str]:
    return [
        "acquire",
        "--config",
        "config/apex_v2.yaml",
        "--run-id",
        "run-output-contract",
        "--code-sha",
        "deadbeef",
        "--run-started-at",
        "2026-08-30T12:42:00+00:00",
    ]


def test_snapshot_handoff_is_not_corrupted_by_noisy_provider_stdout(
    tmp_path: Path,
    monkeypatch,
):
    snapshot_root = tmp_path / "data/v2/snapshots/snapshot-123"
    snapshot_root.mkdir(parents=True)
    (snapshot_root / "manifest.json").write_text("{}\n", encoding="utf-8")

    def noisy_success(*args, **kwargs):
        # Production #40 exposed this class of failure: a shadow worker can write
        # structured output to stdout before the CLI prints the snapshot path.
        print('{"provider":"apex_proprietary","status":"healthy"}')
        return SimpleNamespace(root=snapshot_root)

    monkeypatch.setattr(acquire_runtime, "acquire_and_freeze", noisy_success)
    snapshot_output = tmp_path / "handoff/snapshot.txt"

    result = runner.invoke(
        cli.app,
        _base_acquire_args()
        + ["--snapshot-output", str(snapshot_output)],
    )

    assert result.exit_code == 0, result.output
    assert "apex_proprietary" in result.output
    assert str(snapshot_root) in result.output
    assert snapshot_output.read_text(encoding="utf-8") == f"{snapshot_root}\n"
    assert len(snapshot_output.read_text(encoding="utf-8").splitlines()) == 1


def test_unclassified_acquisition_failure_is_diagnostic_and_secret_safe(
    tmp_path: Path,
    monkeypatch,
):
    secret = "super-secret-token-must-not-leak"

    def fail_unwrapped(*args, **kwargs):
        raise ValueError(secret)

    monkeypatch.setattr(acquire_runtime, "acquire_and_freeze", fail_unwrapped)
    failure_output = tmp_path / "artifacts/v2/diagnostics/acquisition_failure.json"
    snapshot_output = tmp_path / "handoff/snapshot.txt"

    result = runner.invoke(
        cli.app,
        _base_acquire_args()
        + [
            "--failure-output",
            str(failure_output),
            "--snapshot-output",
            str(snapshot_output),
        ],
    )

    assert result.exit_code == 1
    assert failure_output.is_file()
    assert not snapshot_output.exists()
    payload = json.loads(failure_output.read_text(encoding="utf-8"))
    assert payload["stage"] == "acquire_unclassified"
    assert payload["cause_type"] == "ValueError"
    assert payload["run_id"] == "run-output-contract"
    assert payload["code_sha"] == "deadbeef"
    assert secret not in failure_output.read_text(encoding="utf-8")
    assert secret not in result.output


def test_production_and_diagnostic_workflows_use_explicit_snapshot_handoff() -> None:
    workflow = Path(".github/workflows/apex-v2-production.yml").read_text(
        encoding="utf-8"
    )

    # Both the authenticated production job and the non-publishing diagnostic
    # job must use the dedicated file channel. Stdout is never a GitHub-output
    # machine protocol again.
    assert workflow.count("--snapshot-output") == 2
    assert 'SNAPSHOT="$(apex-v2 acquire' not in workflow
    assert workflow.count('test -s "$SNAPSHOT_FILE"') == 2
    assert workflow.count('test -s "$SNAPSHOT/manifest.json"') == 2
    assert workflow.count("printf 'snapshot=%s\\n' \"$SNAPSHOT\" >> \"$GITHUB_OUTPUT\"") == 2
