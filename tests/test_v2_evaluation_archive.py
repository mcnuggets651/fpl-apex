from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from apex.runtime.evaluation_archive import (
    PRIVATE_EVALUATION_RELEASE_ASSETS_V1,
    build_private_provider_evaluation_material,
    load_verified_private_provider_surfaces,
)
from apex.runtime.publication import _provider_forecast_archive
from apex.runtime.snapshot import SnapshotBuilder


def _surface(provider_id: str, expected_points: float) -> dict:
    return {
        "schema_version": 1,
        "provider_id": provider_id,
        "provider_version": "test-v1",
        "generated_at": "2026-08-29T12:00:00Z",
        "season": "2026-2027",
        "source_snapshot": "official-hash",
        "scoring_rules_version": "fpl-2026-27-v1",
        "supported_horizons": [1],
        "runtime_dependencies": [],
        "rows": [
            {
                "element_id": 1,
                "gameweek": 3,
                "horizon": 1,
                "expected_points": expected_points,
                "fixture_ids": [1],
                "n_fixtures": 1,
                "player_status_at_forecast": "a",
                "expected_minutes": 90.0,
                "p_appearance": 1.0,
                "p_start": 1.0,
                "p_60": 1.0,
                "coverage_status": "FORECAST",
                "coverage_reason": None,
                "metadata": {"provider-private-note": provider_id},
            }
        ],
    }


def _snapshot(tmp_path: Path):
    builder = SnapshotBuilder()
    builder.add_json("providers/airsenal.json", _surface("airsenal", 5.5))
    builder.add_json("providers/dastan.json", _surface("dastan", 4.5))
    return builder.freeze(tmp_path / "snapshots", metadata={"frozen_at": "test"})


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_private_evaluation_archive_is_exact_deterministic_and_publicly_bound(tmp_path: Path):
    snapshot = _snapshot(tmp_path)
    public_archive, _ = _provider_forecast_archive(
        snapshot,
        tmp_path / "public" / "provider_forecasts.tar.gz",
    )

    first = build_private_provider_evaluation_material(
        snapshot.root,
        tmp_path / "private-a",
        public_attempt_id="attempt-1",
    )
    second = build_private_provider_evaluation_material(
        snapshot.root,
        tmp_path / "private-b",
        public_attempt_id="attempt-1",
    )

    assert frozenset(first) == PRIVATE_EVALUATION_RELEASE_ASSETS_V1
    assert _sha(first["provider_forecasts.tar.gz"]) == _sha(
        second["provider_forecasts.tar.gz"]
    )
    surfaces = load_verified_private_provider_surfaces(
        public_archive,
        first,
        public_attempt_id="attempt-1",
    )
    assert set(surfaces) == {"providers/airsenal.json", "providers/dastan.json"}
    assert surfaces["providers/airsenal.json"]["rows"][0]["expected_points"] == 5.5
    assert surfaces["providers/airsenal.json"]["rows"][0]["metadata"] == {
        "provider-private-note": "airsenal"
    }

    attestation = json.loads(
        first["provider_attestation.json"].read_text(encoding="utf-8")
    )
    for name in sorted(surfaces):
        assert attestation["providers"][name]["sha256"] == snapshot.manifest["files"][name]["sha256"]
        assert attestation["providers"][name]["bytes"] == snapshot.manifest["files"][name]["bytes"]


def test_private_evaluation_archive_rejects_wrong_public_attempt(tmp_path: Path):
    snapshot = _snapshot(tmp_path)
    public_archive, _ = _provider_forecast_archive(
        snapshot,
        tmp_path / "public" / "provider_forecasts.tar.gz",
    )
    files = build_private_provider_evaluation_material(
        snapshot.root,
        tmp_path / "private",
        public_attempt_id="attempt-1",
    )

    with pytest.raises(RuntimeError, match="different public attempt"):
        load_verified_private_provider_surfaces(
            public_archive,
            files,
            public_attempt_id="attempt-2",
        )


def test_private_evaluation_archive_rejects_tampered_provider_bytes(tmp_path: Path):
    snapshot = _snapshot(tmp_path)
    public_archive, _ = _provider_forecast_archive(
        snapshot,
        tmp_path / "public" / "provider_forecasts.tar.gz",
    )
    files = build_private_provider_evaluation_material(
        snapshot.root,
        tmp_path / "private",
        public_attempt_id="attempt-1",
    )

    replacement = tmp_path / "tampered.tar.gz"
    payload = json.dumps(_surface("airsenal", 99.0), sort_keys=True).encode()
    with tarfile.open(replacement, "w:gz") as archive:
        for name in ("providers/airsenal.json", "providers/dastan.json"):
            data = payload if name.endswith("airsenal.json") else snapshot.read_bytes(name)
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    files["provider_forecasts.tar.gz"] = replacement

    with pytest.raises(RuntimeError, match="attestation digest"):
        load_verified_private_provider_surfaces(
            public_archive,
            files,
            public_attempt_id="attempt-1",
        )


def test_private_evaluation_archive_rejects_public_commitment_tampering(tmp_path: Path):
    snapshot = _snapshot(tmp_path)
    public_archive, _ = _provider_forecast_archive(
        snapshot,
        tmp_path / "public" / "provider_forecasts.tar.gz",
    )
    files = build_private_provider_evaluation_material(
        snapshot.root,
        tmp_path / "private",
        public_attempt_id="attempt-1",
    )
    attestation = json.loads(
        files["provider_attestation.json"].read_text(encoding="utf-8")
    )
    attestation["providers"]["providers/airsenal.json"]["sha256"] = "0" * 64
    files["provider_attestation.json"].write_text(
        json.dumps(attestation, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="public commitments"):
        load_verified_private_provider_surfaces(
            public_archive,
            files,
            public_attempt_id="attempt-1",
        )
