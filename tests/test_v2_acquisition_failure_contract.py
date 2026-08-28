from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from apex.cli import app
from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position
from apex.runtime import acquire as acquire_module


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        schema_version=1,
        season="2026-2027",
        acquired_at="2026-08-28T12:00:00+00:00",
        source_hash="stable-hash",
        players=(
            OfficialPlayer(
                element_id=1,
                web_name="P1",
                team_id=1,
                position=Position.MID,
                price_tenths=50,
                status="a",
                can_transact=True,
            ),
        ),
        fixtures=(),
        deadlines={2: "2099-08-29T10:00:00Z"},
    )


def _config(tmp_path: Path) -> Path:
    path = tmp_path / "apex_v2.yaml"
    path.write_text(
        "\n".join(
            (
                "season: '2026-2027'",
                "entry_id: 63984",
                "max_horizon: 1",
                "snapshot_dir: snapshots",
                "providers: []",
                "",
            )
        ),
        encoding="utf-8",
    )
    return path


def test_team_state_failure_has_stable_stage(monkeypatch, tmp_path):
    official = _official()
    monkeypatch.setattr(
        acquire_module,
        "fetch_official_snapshot",
        lambda **_: (official, {"bootstrap": {}, "fixtures": []}),
    )
    monkeypatch.setattr(
        acquire_module,
        "acquire_team_state",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("entry unavailable")),
    )

    with pytest.raises(acquire_module.AcquisitionStageError) as observed:
        acquire_module.acquire_and_freeze(
            _config(tmp_path),
            run_id="run-team-failure",
            code_sha="abc",
            run_started_at="2026-08-28T11:59:00+00:00",
            workdir=tmp_path,
            expected_official_hash="stable-hash",
        )

    assert observed.value.stage == "team_state"
    assert observed.value.cause_type == "RuntimeError"
    assert observed.value.cause_message == "entry unavailable"


def test_acquisition_seals_explicit_freeze_timestamp(monkeypatch, tmp_path):
    official = _official()
    monkeypatch.setattr(
        acquire_module,
        "fetch_official_snapshot",
        lambda **_: (official, {"bootstrap": {}, "fixtures": []}),
    )
    team_acquisition = SimpleNamespace(
        state=None,
        mode="PUBLIC_DEADLINE_FALLBACK",
        public_transfers=(),
        provenance=lambda: {"mode": "PUBLIC_DEADLINE_FALLBACK"},
    )
    monkeypatch.setattr(
        acquire_module,
        "acquire_team_state",
        lambda *args, **kwargs: team_acquisition,
    )

    snapshot = acquire_module.acquire_and_freeze(
        _config(tmp_path),
        run_id="run-freeze-provenance",
        code_sha="abc",
        run_started_at="2026-08-28T11:59:00+00:00",
        workdir=tmp_path,
        expected_official_hash="stable-hash",
    )

    manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
    run = json.loads((snapshot / "run.json").read_text(encoding="utf-8"))
    frozen_at = manifest["metadata"]["frozen_at"]
    parsed = datetime.fromisoformat(frozen_at.replace("Z", "+00:00"))

    assert frozen_at
    assert parsed.tzinfo is not None
    assert run["frozen_at"] == frozen_at


def test_cli_persists_machine_readable_failure(monkeypatch, tmp_path):
    failure = acquire_module.AcquisitionStageError(
        "official_reanchor",
        RuntimeError("authority changed"),
    )

    def fail(*args, **kwargs):
        del args, kwargs
        raise failure

    monkeypatch.setattr(acquire_module, "acquire_and_freeze", fail)
    output = tmp_path / "acquisition_failure.json"
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "acquire",
            "--config",
            str(tmp_path / "unused.yaml"),
            "--run-id",
            "run-123",
            "--code-sha",
            "deadbeef",
            "--run-started-at",
            "2026-08-28T12:00:00+00:00",
            "--failure-output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-123"
    assert payload["code_sha"] == "deadbeef"
    assert payload["stage"] == "official_reanchor"
    assert payload["cause_type"] == "RuntimeError"
    assert payload["cause_message"] == "authority changed"
