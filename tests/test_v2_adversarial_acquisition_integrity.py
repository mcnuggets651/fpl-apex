from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from apex.domain.models import EvidenceEffect, EvidenceRecord, OfficialPlayer, OfficialSnapshot, Position, ProviderHealth, dataclass_to_dict
from apex.runtime import acquire as acquire_module
from apex.sources.team import TeamStateAcquisition


def record(text: str) -> EvidenceRecord:
    return EvidenceRecord("e1", 1, "Premier League", "https://www.premierleague.com/news/x", "official_league", "2026-08-28T10:00:00+00:00", "2026-08-28T11:00:00+00:00", "2099-08-29T10:00:00+00:00", "explicit_absence", 2, EvidenceEffect.HARD_EXCLUDE, "a" * 64, text)


def records_hash(records) -> str:
    raw = json.dumps([dataclass_to_dict(r) for r in records], sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def official() -> OfficialSnapshot:
    return OfficialSnapshot(1, "2026-2027", "2026-08-28T12:00:00+00:00", "stable-hash", (OfficialPlayer(1, "P1", 1, Position.MID, 50, "a", True),), (), {2: "2099-08-29T10:00:00Z"})


def config(tmp: Path, provider: bool = False) -> Path:
    p = tmp / "apex_v2.yaml"
    provider_yaml = "  - id: airsenal\n    role: CHAMPION\n    priority: 0\n    serve_authorized: true\n    max_age_hours: 48\n    requested_horizons: [1]\n    predictive_status: INSUFFICIENT_HISTORY\n    path: provider.json\n" if provider else ""
    p.write_text("schema_version: 1\nseason: '2026-2027'\nentry_id: 63984\nmax_horizon: 1\nsnapshot_dir: snapshots\nevidence:\n  required: true\n  sources_path: evidence_sources.yaml\n  records_path: evidence_records.json\n  manifest_path: evidence_manifest.json\nproviders:\n" + provider_yaml)
    return p


def write_evidence(tmp: Path, records=()):
    sources = tmp / "evidence_sources.yaml"
    if not sources.exists():
        sources.write_text("feeds:\n  - name: Premier League\n    url: https://www.premierleague.com/news\n    tier: official_league\n    required: true\n")
    (tmp / "evidence_records.json").write_text(json.dumps({"schema_version": 1, "records": [dataclass_to_dict(r) for r in records]}, sort_keys=True))
    manifest = {"schema_version": 1, "completed": True, "observed_official_hash": "stable-hash", "target_gameweek": 2, "record_count": len(records), "records_sha256": records_hash(records), "source_config_sha256": hashlib.sha256(sources.read_bytes()).hexdigest(), "required_source_failures": []}
    (tmp / "evidence_manifest.json").write_text(json.dumps(manifest, sort_keys=True))


def patch_common(monkeypatch, tmp: Path):
    monkeypatch.setattr(acquire_module, "fetch_official_snapshot", lambda **_: (official(), {"bootstrap": {}, "fixtures": []}))
    monkeypatch.setattr(acquire_module, "acquire_team_state", lambda *a, **k: TeamStateAcquisition(state=None, mode="NO_PUBLIC_DEADLINE", credential_present=False, target_gameweek=2, detail="test"))
    write_evidence(tmp)


def test_manifest_rejects_same_count_evidence_substitution(tmp_path: Path):
    original = (record("Player is ruled out."),)
    write_evidence(tmp_path, original)
    tampered = (record("Player is fully available."),)
    with pytest.raises(RuntimeError, match="evidence payload hash"):
        acquire_module._validate_evidence_acquisition(tmp_path / "evidence_manifest.json", tampered, required=True, official_hash="stable-hash", target_gameweek=2)


def test_required_evidence_source_config_is_sealed(monkeypatch, tmp_path: Path):
    patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(acquire_module, "collect_v2_evidence", lambda **_: SimpleNamespace())
    snapshot = acquire_module.acquire_and_freeze(config(tmp_path), run_id="source-seal", code_sha="abc", run_started_at="2026-08-28T11:59:00+00:00", workdir=tmp_path, expected_official_hash="stable-hash")
    sealed = snapshot.read_bytes("evidence_sources.yaml")
    manifest = snapshot.read_json("evidence_acquisition.json")
    assert hashlib.sha256(sealed).hexdigest() == manifest["source_config_sha256"]


def test_provider_raw_mutation_during_load_aborts(monkeypatch, tmp_path: Path):
    patch_common(monkeypatch, tmp_path)
    monkeypatch.setattr(acquire_module, "collect_v2_evidence", lambda **_: SimpleNamespace())
    path = tmp_path / "provider.json"
    path.write_text('{"version":"before"}\n')
    surface = SimpleNamespace(generated_at="2026-08-28T11:59:30+00:00", scoring_rules_version="fpl-2026-27-v1")
    def mutate(*a, **k):
        path.write_text('{"version":"after"}\n')
        return surface
    monkeypatch.setattr(acquire_module, "load_airsenal", mutate)
    monkeypatch.setattr(acquire_module, "qualify_surface", lambda *a, **k: SimpleNamespace(reasons=(), health=ProviderHealth.HEALTHY, qualified_horizons=(1,)))
    with pytest.raises(acquire_module.AcquisitionStageError) as err:
        acquire_module.acquire_and_freeze(config(tmp_path, True), run_id="provider-toctou", code_sha="abc", run_started_at="2026-08-28T11:59:00+00:00", workdir=tmp_path, expected_official_hash="stable-hash")
    assert err.value.stage == "provider_integrity"
    assert "changed during acquisition" in err.value.cause_message
