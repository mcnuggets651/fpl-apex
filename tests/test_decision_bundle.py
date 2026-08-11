from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from apex_fpl.config import Settings
from apex_fpl.optimisation.squad import SquadSolution
from apex_fpl.services.data_quality import DataQualityAssessment, QualityCheck
from apex_fpl.services.decision_bundle import DecisionBundle, dataframe_sha256
from apex_fpl.services.pipeline import PipelineOutput
from apex_fpl.services.provenance import SourceStatus
from apex_fpl.services.safety import SafetyAssessment


def _solution(players: pd.DataFrame) -> SquadSolution:
    return SquadSolution(
        status="Optimal",
        objective=42.5,
        squad=players.copy(),
        xi=players.head(1).copy(),
        captain=players.head(1).copy(),
        vice_captain=players.tail(1).copy(),
        bench=players.tail(1).copy(),
    )


def _output(projection_delta: float = 0.0) -> PipelineOutput:
    players = pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "One",
                "team": 1,
                "team_name": "A",
                "position": "MID",
                "price": 7.0,
                "expected_minutes": 82.0,
            },
            {
                "player_id": 2,
                "web_name": "Two",
                "team": 2,
                "team_name": "B",
                "position": "FWD",
                "price": 8.0,
                "expected_minutes": 79.0,
            },
        ]
    )
    projections = pd.DataFrame(
        [
            {"player_id": 1, "gw": 1, "xp": 5.0 + projection_delta},
            {"player_id": 2, "gw": 1, "xp": 4.0},
        ]
    )
    quality = DataQualityAssessment(
        ready=True,
        blockers=(),
        warnings=(),
        checks=(QualityCheck("surface", "pass", True, "complete", 1.0, 1.0),),
    )
    return PipelineOutput(
        players=players,
        projections=projections,
        integrity=pd.DataFrame(columns=["player_id", "issue"]),
        news_audit=pd.DataFrame([{"player_id": 1, "signal": "start"}]),
        scenarios={"unrestricted": _solution(players)},
        transfer_plan=None,
        sources=[
            SourceStatus(
                "official_fpl",
                True,
                detail=(
                    "https://private.example/odds https://private.example/news "
                    "must-never-be-persisted"
                ),
                checked_at="2026-08-11T08:00:00Z",
            )
        ],
        gameweeks=[1],
        safety=SafetyAssessment(True, True, [], []),
        snapshot={
            "snapshot_id": "fixture",
            "retrieved_at": "2026-08-11T08:00:00Z",
            "bootstrap_sha256": "a" * 64,
            "fixtures_sha256": "b" * 64,
        },
        data_quality=quality,
        upstreams={"fpl_core_insights": {"commit": "abc123"}},
        material_inputs={
            "core": {"rows": 2, "sha256": "c" * 64},
            "preseason": {"rows": 1, "sha256": "d" * 64},
        },
    )


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        horizon=1,
        cache_dir=tmp_path / "cache",
        snapshot_dir=tmp_path / "snapshots",
        report_dir=tmp_path / "reports",
        airsenal_csv=None,
        odds_api_key="must-never-be-persisted",
        odds_api_url="https://private.example/odds",
        news_feeds=["https://private.example/news"],
    )


def test_bundle_round_trip_preserves_replay_surface_and_lineage(tmp_path: Path) -> None:
    first = DecisionBundle.capture(
        _output(), _settings(tmp_path), tmp_path / "bundle-a", repo_root=Path.cwd()
    )
    second = DecisionBundle.capture(
        _output(), _settings(tmp_path), tmp_path / "bundle-b", repo_root=Path.cwd()
    )
    loaded = DecisionBundle.load(first.root)
    replay = loaded.to_pipeline_output()

    assert first.bundle_id == second.bundle_id == loaded.bundle_id
    assert (first.root / "projections.json").read_bytes() == (
        second.root / "projections.json"
    ).read_bytes()
    assert dataframe_sha256(replay.projections) == dataframe_sha256(_output().projections)
    assert replay.scenarios["unrestricted"].objective == 42.5
    assert replay.upstreams == _output().upstreams
    assert loaded.manifest["material_inputs"]["preseason"]["sha256"] == "d" * 64
    manifest_text = (first.root / "manifest.json").read_text(encoding="utf-8")
    assert "must-never-be-persisted" not in manifest_text
    assert "https://private.example" not in manifest_text


def test_any_projection_change_changes_bundle_identity(tmp_path: Path) -> None:
    base = DecisionBundle.capture(
        _output(), _settings(tmp_path), tmp_path / "base", repo_root=Path.cwd()
    )
    changed = DecisionBundle.capture(
        _output(0.001), _settings(tmp_path), tmp_path / "changed", repo_root=Path.cwd()
    )
    assert base.bundle_id != changed.bundle_id


def test_bundle_rejects_tampered_projection_artifact(tmp_path: Path) -> None:
    bundle = DecisionBundle.capture(
        _output(), _settings(tmp_path), tmp_path / "bundle", repo_root=Path.cwd()
    )
    path = bundle.root / "projections.json"
    path.write_text(path.read_text(encoding="utf-8") + " ", encoding="utf-8")
    with pytest.raises(ValueError, match="artifact hash mismatch"):
        DecisionBundle.load(bundle.root)


def test_bundle_rejects_tampered_readiness_metadata(tmp_path: Path) -> None:
    bundle = DecisionBundle.capture(
        _output(), _settings(tmp_path), tmp_path / "bundle", repo_root=Path.cwd()
    )
    path = bundle.root / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["safety"]["safe_to_act"] = False
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="metadata hash mismatch: safety"):
        DecisionBundle.load(bundle.root)


def test_decision_layers_have_no_live_retrieval_path() -> None:
    root = Path(__file__).resolve().parents[1]
    for script_name in ("run_pinnacle.py", "run_elite.py"):
        source = (root / "scripts" / script_name).read_text(encoding="utf-8")
        assert "run_pipeline" not in source
        assert "OfficialFPLClient" not in source
        assert "DecisionBundle.load" in source


def test_artifact_hash_is_the_exact_persisted_projection_bytes(tmp_path: Path) -> None:
    bundle = DecisionBundle.capture(
        _output(), _settings(tmp_path), tmp_path / "bundle", repo_root=Path.cwd()
    )
    raw = (bundle.root / "projections.json").read_bytes()
    expected = bundle.manifest["artifacts"]["projections"]["sha256"]
    assert hashlib.sha256(raw).hexdigest() == expected
    assert json.loads(raw)["columns"] == sorted(_output().projections.columns)
