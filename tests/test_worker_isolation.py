from pathlib import Path

import pytest

from apex_fpl.ports.workers import WorkerKind, WorkerResponse, WorkerRuntime


ROOT = Path(__file__).resolve().parents[1]


def test_airsenal_install_uses_separate_frozen_worker_environment() -> None:
    text = (ROOT / "scripts/install_pinned_airsenal.sh").read_text(encoding="utf-8")
    assert 'python -m venv "$uv_venv"' in text
    assert "uv==0.12.3" in text
    assert '"$uv_venv/bin/uv" sync --frozen --project "$checkout" --no-dev' in text
    assert 'worker_python="$checkout/.venv/bin/python"' in text
    assert "AIRSENAL_WORKER_PYTHON" in text
    assert "AIRSENAL_WORKER_BIN" in text
    assert "AIrsenal uv.lock BPL revision disagrees" in text
    assert '\npip install "$checkout"' not in text


def test_worker_response_is_data_only_and_typed() -> None:
    runtime = WorkerRuntime(WorkerKind.AIRSENAL, "sha256:runtime", "a" * 40)
    response = WorkerResponse(
        kind=WorkerKind.AIRSENAL,
        request_id="request-1",
        runtime=runtime,
        output_artifact_ids=("sha256:output",),
        success=True,
    )
    assert response.schema_version == 1
    with pytest.raises(ValueError, match="kind mismatch"):
        WorkerResponse(
            kind=WorkerKind.REFERENCE_SOLVER,
            request_id="request-1",
            runtime=runtime,
            output_artifact_ids=("sha256:output",),
            success=True,
        )
