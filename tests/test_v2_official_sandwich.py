from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position
from apex.runtime import acquire as acquire_module


def _official(source_hash: str) -> OfficialSnapshot:
    return OfficialSnapshot(
        schema_version=1,
        season="2026-2027",
        acquired_at="2026-08-28T12:00:00+00:00",
        source_hash=source_hash,
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


def test_official_hash_mismatch_aborts_before_team_or_provider_processing(
    monkeypatch,
    tmp_path: Path,
):
    official = _official("final-hash")
    monkeypatch.setattr(
        acquire_module,
        "fetch_official_snapshot",
        lambda **_: (official, {"bootstrap": {}, "fixtures": []}),
    )

    team_called = False

    def unexpected_team_fetch(*args, **kwargs):
        nonlocal team_called
        team_called = True
        raise AssertionError("team fetch must not happen after Official seal mismatch")

    monkeypatch.setattr(
        acquire_module,
        "fetch_team_state",
        unexpected_team_fetch,
    )

    with pytest.raises(
        acquire_module.AcquisitionStageError,
        match="official_reanchor: RuntimeError: Official FPL authority state changed",
    ):
        acquire_module.acquire_and_freeze(
            _config(tmp_path),
            run_id="run-1",
            code_sha="abc",
            run_started_at="2026-08-28T11:59:00+00:00",
            workdir=tmp_path,
            expected_official_hash="pre-provider-hash",
        )
    assert not team_called


def test_matching_official_hash_is_frozen_as_provenance(
    monkeypatch,
    tmp_path: Path,
):
    official = _official("stable-hash")
    monkeypatch.setattr(
        acquire_module,
        "fetch_official_snapshot",
        lambda **_: (official, {"bootstrap": {}, "fixtures": []}),
    )
    monkeypatch.setattr(
        acquire_module,
        "fetch_team_state",
        lambda *args, **kwargs: None,
    )

    snapshot = acquire_module.acquire_and_freeze(
        _config(tmp_path),
        run_id="run-2",
        code_sha="abc",
        run_started_at="2026-08-28T11:59:00+00:00",
        workdir=tmp_path,
        expected_official_hash="stable-hash",
    )

    run = json.loads((snapshot.root / "run.json").read_text(encoding="utf-8"))
    assert run["official_pre_provider_hash"] == "stable-hash"
    assert run["official_final_hash"] == "stable-hash"
    assert run["official_acquisition_stable"] is True
    assert snapshot.manifest["metadata"]["official_pre_provider_hash"] == "stable-hash"
    assert snapshot.manifest["metadata"]["official_final_hash"] == "stable-hash"
