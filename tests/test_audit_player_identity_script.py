from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts" / "audit_player_identity.py"
    spec = importlib.util.spec_from_file_location(
        "audit_player_identity_script_contract", path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _official() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "Raya",
                "first_name": "David",
                "second_name": "Raya",
                "team": 1,
                "team_name": "Arsenal",
                "position": "GK",
            },
            {
                "player_id": 2,
                "web_name": "João Pedro",
                "first_name": "João",
                "second_name": "Pedro",
                "team": 2,
                "team_name": "Chelsea",
                "position": "FWD",
            },
            {
                "player_id": 3,
                "web_name": "Guéhi",
                "first_name": "Marc",
                "second_name": "Guéhi",
                "team": 3,
                "team_name": "Man City",
                "position": "DEF",
            },
        ]
    )


class _Bundle:
    bundle_id = "bundle-test-123"
    settings = {"source_configuration": {"airsenal_configured": True}}

    def to_pipeline_output(self):
        return SimpleNamespace(players=_official())


def _args(
    tmp_path: Path, airsenal: Path, recommendation: Path | None = None
) -> argparse.Namespace:
    return argparse.Namespace(
        bundle_dir=str(tmp_path / "bundle"),
        airsenal=str(airsenal),
        specialist=str(tmp_path / "missing-specialist.csv"),
        transfer=str(tmp_path / "missing-transfer.csv"),
        availability=str(tmp_path / "missing-availability.csv"),
        tactical=str(tmp_path / "missing-tactical.csv"),
        hierarchy=str(tmp_path / "missing-hierarchy.csv"),
        recommendation=str(recommendation) if recommendation else None,
        output=str(tmp_path / "run" / "player_identity_audit.json"),
        csv=str(tmp_path / "run" / "player_identity_audit.csv"),
    )


def _write_manifest(tmp_path: Path) -> None:
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir(parents=True)
    (bundle_dir / "manifest.json").write_text(
        json.dumps({"source_snapshot_ids": {"official_fpl": "official-snapshot-abc"}}),
        encoding="utf-8",
    )


def _write_airsenal(path: Path, ids: list[int]) -> None:
    names = {1: "Raya", 2: "Joao Pedro", 3: "Guehi"}
    pd.DataFrame(
        [
            {
                "player_id": pid,
                "source_player_name": names[pid],
                "identity_witness_type": "airsenal_name",
                "gw": 2,
                "xp": 4.0,
            }
            for pid in ids
        ]
    ).to_csv(path, index=False)


def test_sealed_audit_accepts_complete_roster_and_records_provenance(
    tmp_path, monkeypatch
):
    module = _module()
    _write_manifest(tmp_path)
    airsenal = tmp_path / "airsenal.csv"
    _write_airsenal(airsenal, [1, 2, 3])
    recommendation = tmp_path / "recommendation.json"
    recommendation.write_text(
        json.dumps(
            {"squad_ids": [1, 2, 3], "captain_id": 2, "vice_captain_id": 1}
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(module.DecisionBundle, "load", lambda _: _Bundle())

    audit = module._run(_args(tmp_path, airsenal, recommendation))

    assert audit["ready"]
    assert audit["decision_bundle_id"] == "bundle-test-123"
    assert audit["official_snapshot_id"] == "official-snapshot-abc"
    assert audit["official_player_count"] == 3
    assert audit["airsenal_full_roster_coverage"]["ready"]
    assert audit["airsenal_full_roster_coverage"]["source_ids"] == 3
    assert audit["selected_references"]["ready"]
    assert audit["selected_references"]["player_ids"] == [1, 2, 3]
    assert audit["selected_references"]["invalid_references"] == []
    assert audit["inputs"]["airsenal"]["sha256"]
    assert audit["inputs"]["airsenal"]["rows"] == 3


def test_sealed_audit_fails_closed_when_airsenal_roster_is_incomplete(
    tmp_path, monkeypatch
):
    module = _module()
    _write_manifest(tmp_path)
    airsenal = tmp_path / "airsenal.csv"
    _write_airsenal(airsenal, [1, 2])
    monkeypatch.setattr(module.DecisionBundle, "load", lambda _: _Bundle())

    audit = module._run(_args(tmp_path, airsenal))

    assert not audit["ready"]
    assert audit["airsenal_full_roster_coverage"]["missing_ids"] == [3]
    assert any(
        "missing 1 Official FPL player IDs" in blocker for blocker in audit["blockers"]
    )


def test_sealed_audit_rejects_null_airsenal_identity_witness_type(
    tmp_path, monkeypatch
):
    module = _module()
    _write_manifest(tmp_path)
    airsenal = tmp_path / "airsenal.csv"
    _write_airsenal(airsenal, [1, 2, 3])
    frame = pd.read_csv(airsenal)
    frame.loc[1, "identity_witness_type"] = None
    frame.to_csv(airsenal, index=False)
    monkeypatch.setattr(module.DecisionBundle, "load", lambda _: _Bundle())

    audit = module._run(_args(tmp_path, airsenal))

    assert not audit["ready"]
    assert audit["airsenal_full_roster_coverage"]["ready"]
    assert any(
        "null/non-authoritative identity_witness_type" in blocker
        for blocker in audit["blockers"]
    )


def test_sealed_audit_rejects_unknown_selected_player_id(tmp_path, monkeypatch):
    module = _module()
    _write_manifest(tmp_path)
    airsenal = tmp_path / "airsenal.csv"
    _write_airsenal(airsenal, [1, 2, 3])
    recommendation = tmp_path / "recommendation.json"
    recommendation.write_text(
        json.dumps({"squad_ids": [1, 2, 999]}), encoding="utf-8"
    )
    monkeypatch.setattr(module.DecisionBundle, "load", lambda _: _Bundle())

    audit = module._run(_args(tmp_path, airsenal, recommendation))

    assert not audit["ready"]
    assert audit["selected_references"]["unknown_ids"] == [999]
    assert any(
        "recommendation references unknown" in blocker for blocker in audit["blockers"]
    )


def test_sealed_audit_rejects_fractional_selected_player_id(tmp_path, monkeypatch):
    module = _module()
    _write_manifest(tmp_path)
    airsenal = tmp_path / "airsenal.csv"
    _write_airsenal(airsenal, [1, 2, 3])
    recommendation = tmp_path / "recommendation.json"
    recommendation.write_text(
        json.dumps({"squad_ids": [1, 2, 3.5]}), encoding="utf-8"
    )
    monkeypatch.setattr(module.DecisionBundle, "load", lambda _: _Bundle())

    audit = module._run(_args(tmp_path, airsenal, recommendation))

    assert not audit["ready"]
    invalid = audit["selected_references"]["invalid_references"]
    assert len(invalid) == 1
    assert "non-integral" in invalid[0]["reason"]
    assert 3 not in audit["selected_references"]["player_ids"]
    assert any(
        "malformed/non-integral player ID" in blocker for blocker in audit["blockers"]
    )


def test_main_persists_machine_readable_failure_when_bundle_load_raises(
    tmp_path, monkeypatch
):
    module = _module()
    bundle_dir = tmp_path / "broken-bundle"
    bundle_dir.mkdir()
    airsenal = tmp_path / "airsenal.csv"
    airsenal.write_text(
        "player_id,source_player_name,identity_witness_type\n", encoding="utf-8"
    )
    output = tmp_path / "run" / "player_identity_audit.json"
    csv_path = tmp_path / "run" / "player_identity_audit.csv"

    def explode(_):
        raise RuntimeError("sealed bundle cannot be loaded")

    monkeypatch.setattr(module.DecisionBundle, "load", explode)
    monkeypatch.setattr(
        "sys.argv",
        [
            "audit_player_identity.py",
            "--bundle-dir",
            str(bundle_dir),
            "--airsenal",
            str(airsenal),
            "--output",
            str(output),
            "--csv",
            str(csv_path),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        module.main()

    assert exc.value.code == 1
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["ready"] is False
    assert payload["failure_kind"] == "internal_or_input_error"
    assert "sealed bundle cannot be loaded" in payload["blockers"][0]
    assert csv_path.exists()
