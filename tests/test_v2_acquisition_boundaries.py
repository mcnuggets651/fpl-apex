from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from apex.domain.models import (
    CoverageStatus,
    EvidenceEffect,
    EvidenceRecord,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    ProviderHealth,
)
from apex.runtime import acquire as acquire_module
from apex.sources.team import TeamStateAcquisition


def _official(*, deadline: datetime | None = None) -> OfficialSnapshot:
    deadline = deadline or datetime(2099, 8, 29, 10, tzinfo=timezone.utc)
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T12:00:00+00:00",
        "stable-hash",
        (
            OfficialPlayer(
                1,
                "P1",
                1,
                Position.MID,
                50,
                "a",
                True,
            ),
        ),
        (),
        {2: deadline.isoformat()},
    )


def _team() -> TeamStateAcquisition:
    return TeamStateAcquisition(
        state=None,
        mode="NO_PUBLIC_DEADLINE",
        credential_present=False,
        target_gameweek=2,
        detail="boundary test",
    )


def _surface(provider_id: str, *, generated_at: str) -> ProjectionSurface:
    return ProjectionSurface(
        1,
        provider_id,
        "boundary-v1",
        generated_at,
        "2026-2027",
        "stable-hash",
        "fpl-2026-27-v1",
        (1,),
        (),
        (
            ProjectionRow(
                1,
                2,
                1,
                5.0,
                expected_minutes=90.0,
                p_appearance=1.0,
                p_start=1.0,
                p_60=1.0,
                coverage_status=CoverageStatus.FORECAST,
            ),
        ),
    )


def _config(tmp_path: Path, *, provider_id: str | None = None) -> Path:
    provider_yaml = "providers: []\n"
    if provider_id is not None:
        suffix = ".json" if provider_id == "pitchside" else ".csv"
        provider_yaml = (
            "providers:\n"
            f"  - id: {provider_id}\n"
            "    role: SHADOW\n"
            "    priority: 10\n"
            "    serve_authorized: false\n"
            "    max_age_hours: 48\n"
            "    requested_horizons: [1]\n"
            "    predictive_status: INSUFFICIENT_HISTORY\n"
            f"    path: provider{suffix}\n"
        )
    path = tmp_path / "apex_v2.yaml"
    path.write_text(
        "schema_version: 1\n"
        "season: '2026-2027'\n"
        "entry_id: 63984\n"
        "max_horizon: 1\n"
        "snapshot_dir: snapshots\n"
        "evidence:\n"
        "  required: false\n"
        + provider_yaml,
        encoding="utf-8",
    )
    return path


def _patch_runtime(monkeypatch, official: OfficialSnapshot | None = None) -> None:
    official = official or _official()
    monkeypatch.setattr(
        acquire_module,
        "fetch_official_snapshot",
        lambda **_: (official, {"bootstrap": {}, "fixtures": []}),
    )
    monkeypatch.setattr(
        acquire_module,
        "acquire_team_state",
        lambda *args, **kwargs: _team(),
    )
    monkeypatch.delenv("FPL_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("FPL_X_API_AUTHORIZATION", raising=False)
    monkeypatch.setenv("APEX_ENABLE_PRIVATE_MANAGER_STATE", "0")


def test_stage_wraps_unknown_error_and_preserves_stage_error():
    with pytest.raises(acquire_module.AcquisitionStageError) as wrapped:
        acquire_module._stage("boundary", lambda: (_ for _ in ()).throw(ValueError("bad")))
    assert wrapped.value.stage == "boundary"
    assert wrapped.value.cause_type == "ValueError"
    assert wrapped.value.cause_message == "bad"

    original = acquire_module.AcquisitionStageError("inner", RuntimeError("already classified"))
    with pytest.raises(acquire_module.AcquisitionStageError) as preserved:
        acquire_module._stage("outer", lambda: (_ for _ in ()).throw(original))
    assert preserved.value is original


def test_target_gameweek_uses_earliest_future_deadline_and_rejects_finished_season():
    now = datetime(2026, 8, 28, 12, tzinfo=timezone.utc)
    official = _official()
    official = OfficialSnapshot(
        official.schema_version,
        official.season,
        official.acquired_at,
        official.source_hash,
        official.players,
        official.fixtures,
        {
            1: (now - timedelta(days=1)).isoformat(),
            3: (now + timedelta(days=7)).isoformat(),
            2: (now + timedelta(days=1)).isoformat(),
        },
    )
    assert acquire_module._target_gameweek(official, now) == 2

    finished = OfficialSnapshot(
        official.schema_version,
        official.season,
        official.acquired_at,
        official.source_hash,
        official.players,
        official.fixtures,
        {1: (now - timedelta(days=1)).isoformat()},
    )
    with pytest.raises(RuntimeError, match="no future Official FPL deadline"):
        acquire_module._target_gameweek(finished, now)


@pytest.mark.parametrize(
    ("flag", "cookie", "authorization", "expected"),
    [
        ("x", "", "", "must be exactly '0' or '1'"),
        ("0", "session=secret", "", "credentials are present"),
        ("1", "", "", "no FPL owner credential is present"),
        ("0", "", "", None),
        ("1", "", "token", None),
    ],
)
def test_private_manager_opt_in_is_explicit(
    monkeypatch,
    flag: str,
    cookie: str,
    authorization: str,
    expected: str | None,
):
    monkeypatch.setenv("APEX_ENABLE_PRIVATE_MANAGER_STATE", flag)
    monkeypatch.setenv("FPL_SESSION_COOKIE", cookie)
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", authorization)
    if expected is None:
        acquire_module.assert_private_manager_credential_opt_in()
    else:
        with pytest.raises(RuntimeError, match=expected):
            acquire_module.assert_private_manager_credential_opt_in()


def _evidence_record() -> EvidenceRecord:
    return EvidenceRecord(
        "e1",
        1,
        "Premier League",
        "https://example.test/e1",
        "official_league",
        "2026-08-28T10:00:00+00:00",
        "2026-08-28T11:00:00+00:00",
        "2099-08-29T10:00:00+00:00",
        "explicit_absence",
        2,
        EvidenceEffect.HARD_EXCLUDE,
        "a" * 64,
        "P1 ruled out",
    )


def _valid_evidence_manifest(records: tuple[EvidenceRecord, ...]) -> dict:
    return {
        "schema_version": 1,
        "completed": True,
        "observed_official_hash": "stable-hash",
        "target_gameweek": 2,
        "record_count": len(records),
        "records_sha256": acquire_module._canonical_records_hash(records),
        "source_config_sha256": "b" * 64,
        "required_source_failures": [],
    }


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda row: row.update(schema_version=2), "manifest schema invalid"),
        (lambda row: row.update(completed=False), "did not complete"),
        (lambda row: row.update(observed_official_hash="other"), "does not match final authority"),
        (lambda row: row.update(target_gameweek=3), "target gameweek does not match"),
        (lambda row: row.update(record_count=99), "record count does not match"),
        (lambda row: row.pop("records_sha256"), "does not bind evidence payload hash"),
        (lambda row: row.update(records_sha256="0" * 64), "evidence payload hash does not match"),
        (lambda row: row.update(required_source_failures=["League"]), "source failures remain"),
    ],
)
def test_required_evidence_manifest_fails_closed(mutation, message: str):
    records = (_evidence_record(),)
    manifest = _valid_evidence_manifest(records)
    mutation(manifest)
    with pytest.raises(RuntimeError, match=message):
        acquire_module._validate_evidence_manifest(
            manifest,
            records,
            required=True,
            official_hash="stable-hash",
            target_gameweek=2,
        )


def test_optional_missing_evidence_manifest_is_explicitly_not_required(tmp_path: Path):
    result = acquire_module._validate_evidence_acquisition(
        tmp_path / "missing.json",
        (),
        required=False,
        official_hash="stable-hash",
        target_gameweek=2,
    )
    assert result["mode"] == "NOT_REQUIRED"
    assert result["record_count"] == 0


def test_required_missing_evidence_manifest_fails(tmp_path: Path):
    with pytest.raises(RuntimeError, match="manifest is missing"):
        acquire_module._validate_evidence_acquisition(
            tmp_path / "missing.json",
            (),
            required=True,
            official_hash="stable-hash",
            target_gameweek=2,
        )


def test_missing_provider_is_frozen_as_error_status(monkeypatch, tmp_path: Path):
    _patch_runtime(monkeypatch)
    snapshot = acquire_module.acquire_and_freeze(
        _config(tmp_path, provider_id="airsenal"),
        run_id="missing-provider",
        code_sha="abc",
        run_started_at="2026-08-28T11:59:00+00:00",
        workdir=tmp_path,
        expected_official_hash="stable-hash",
    )
    matrix = snapshot.read_json("qualification_matrix.json")
    assert matrix[0]["health"] == "ERROR"
    assert "provider export missing" in matrix[0]["reasons"][0]


def test_shadow_adapter_error_is_contained_and_raw_bytes_are_sealed(
    monkeypatch,
    tmp_path: Path,
):
    _patch_runtime(monkeypatch)
    config = _config(tmp_path, provider_id="airsenal")
    raw = b"bad provider bytes\n"
    (tmp_path / "provider.csv").write_bytes(raw)
    monkeypatch.setattr(
        acquire_module,
        "load_airsenal",
        lambda *args, **kwargs: (_ for _ in ()).throw(ValueError("adapter rejected export")),
    )
    snapshot = acquire_module.acquire_and_freeze(
        config,
        run_id="adapter-error",
        code_sha="abc",
        run_started_at="2026-08-28T11:59:00+00:00",
        workdir=tmp_path,
        expected_official_hash="stable-hash",
    )
    matrix = snapshot.read_json("qualification_matrix.json")
    assert matrix[0]["health"] == "ERROR"
    assert any("adapter rejected export" in reason for reason in matrix[0]["reasons"])
    assert snapshot.read_bytes("provider_raw/airsenal.csv") == raw


@pytest.mark.parametrize(
    ("provider_id", "loader_name"),
    [
        ("airsenal", "load_airsenal"),
        ("dastan", "load_dastan"),
        ("pitchside", "load_pitchside"),
        ("apex_proprietary", "load_apex_proprietary"),
        ("openfpl", "load_openfpl"),
    ],
)
def test_every_provider_adapter_dispatches_from_captured_bytes(
    monkeypatch,
    tmp_path: Path,
    provider_id: str,
    loader_name: str,
):
    _patch_runtime(monkeypatch)
    config = _config(tmp_path, provider_id=provider_id)
    suffix = ".json" if provider_id == "pitchside" else ".csv"
    raw_path = tmp_path / f"provider{suffix}"
    raw_path.write_bytes(f"{provider_id}-raw\n".encode())
    calls = []

    def loader(path, **kwargs):
        calls.append((Path(path), kwargs))
        assert Path(path) != raw_path
        assert Path(path).read_bytes() == raw_path.read_bytes()
        return _surface(provider_id, generated_at="2026-08-28T12:00:00+00:00")

    monkeypatch.setattr(acquire_module, loader_name, loader)
    monkeypatch.setattr(
        acquire_module,
        "qualify_surface",
        lambda *args, **kwargs: SimpleNamespace(
            reasons=(),
            health=ProviderHealth.HEALTHY,
            qualified_horizons=(1,),
        ),
    )
    snapshot = acquire_module.acquire_and_freeze(
        config,
        run_id=f"dispatch-{provider_id}",
        code_sha="abc",
        run_started_at="2026-08-28T11:59:00+00:00",
        workdir=tmp_path,
        expected_official_hash="stable-hash",
    )
    assert len(calls) == 1
    matrix = snapshot.read_json("qualification_matrix.json")
    assert matrix[0]["health"] == "HEALTHY"
    assert snapshot.read_bytes(f"provider_raw/{provider_id}{suffix}") == raw_path.read_bytes()


def test_provider_forecast_predating_attempt_is_degraded(monkeypatch, tmp_path: Path):
    _patch_runtime(monkeypatch)
    config = _config(tmp_path, provider_id="airsenal")
    (tmp_path / "provider.csv").write_bytes(b"raw\n")
    monkeypatch.setattr(
        acquire_module,
        "load_airsenal",
        lambda *args, **kwargs: _surface(
            "airsenal",
            generated_at="2026-08-28T10:00:00+00:00",
        ),
    )
    monkeypatch.setattr(
        acquire_module,
        "qualify_surface",
        lambda *args, **kwargs: SimpleNamespace(
            reasons=(),
            health=ProviderHealth.HEALTHY,
            qualified_horizons=(1,),
        ),
    )
    snapshot = acquire_module.acquire_and_freeze(
        config,
        run_id="predates-attempt",
        code_sha="abc",
        run_started_at="2026-08-28T11:00:00+00:00",
        workdir=tmp_path,
        expected_official_hash="stable-hash",
    )
    row = snapshot.read_json("qualification_matrix.json")[0]
    assert row["health"] == "INCOMPLETE"
    assert any("predates this production attempt" in reason for reason in row["reasons"])


def test_optional_pitchside_acquisition_failure_is_diagnostic(monkeypatch, tmp_path: Path):
    _patch_runtime(monkeypatch)
    config = _config(tmp_path, provider_id="pitchside")
    monkeypatch.setattr(
        acquire_module,
        "acquire_pitchside_shadow",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("shadow unavailable")),
    )
    snapshot = acquire_module.acquire_and_freeze(
        config,
        run_id="pitchside-failure",
        code_sha="abc",
        run_started_at="2026-08-28T11:00:00+00:00",
        workdir=tmp_path,
        expected_official_hash="stable-hash",
    )
    row = snapshot.read_json("qualification_matrix.json")[0]
    assert row["health"] == "ERROR"
    assert any("optional provider acquisition failed" in reason for reason in row["reasons"])
    assert any("provider export missing" in reason for reason in row["reasons"])
