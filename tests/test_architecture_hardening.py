from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from apex_fpl.data.airsenal import AIrsenalProjectionAdapter, validate_airsenal_forecast
from apex_fpl.models.ensemble import blend_projection


ROOT = Path(__file__).resolve().parents[1]


def _script(name: str):
    path = ROOT / "scripts" / name
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_airsenal_whole_club_zero_surface_becomes_explicit_abstention(tmp_path: Path):
    worker = _script("run_airsenal_worker.py")
    path = tmp_path / "airsenal.csv"
    rows = []
    for gw in (1, 2):
        rows.extend(
            [
                {"player_id": 1, "gw": gw, "xp": 0.0},
                {"player_id": 2, "gw": gw, "xp": 0.0},
                # A zero bench player on a team with a real forecast must remain a
                # genuine zero, not be blanket-classified as unsupported.
                {"player_id": 3, "gw": gw, "xp": 0.0},
                {"player_id": 4, "gw": gw, "xp": 4.0},
            ]
        )
    pd.DataFrame(rows).to_csv(path, index=False)

    abstentions = worker._annotate_semantic_support(
        path,
        {1: 10, 2: 10, 3: 20, 4: 20},
        {10: "Unsupported FC", 20: "Supported FC"},
        [1, 2],
    )
    out = pd.read_csv(path)
    assert abstentions == {10: "Unsupported FC"}
    assert set(out.loc[out.player_id.isin([1, 2]), "source_supported"].astype(str).str.lower()) == {"false"}
    assert set(out.loc[out.player_id.isin([3, 4]), "source_supported"].astype(str).str.lower()) == {"true"}
    assert out.loc[out.player_id.isin([1, 2]), "support_reason"].str.contains(
        "structural_all_zero_team_surface"
    ).all()


def test_airsenal_abstention_preserves_raw_truth_but_removes_expert_vote(tmp_path: Path):
    now = datetime.now(timezone.utc).isoformat()
    path = tmp_path / "airsenal.csv"
    pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "xp": 0.0,
                "generated_at": now,
                "source_version": "pin",
                "prediction_tag": "tag",
                "source_supported": False,
                "support_reason": "structural_all_zero_team_surface:Promoted FC",
            }
        ]
    ).to_csv(path, index=False)
    forecast = AIrsenalProjectionAdapter(str(path)).load(valid_ids={1})
    assert forecast.loc[0, "airsenal_raw_xp"] == pytest.approx(0.0)
    assert pd.isna(forecast.loc[0, "airsenal_xp"])
    assert bool(forecast.loc[0, "airsenal_source_supported"]) is False

    ok, detail = validate_airsenal_forecast(
        forecast,
        {1},
        [1],
        expected_source_version="pin",
        min_player_coverage=1.0,
    )
    assert ok, detail
    assert "semantic abstention rows=1" in detail

    base = pd.DataFrame(
        {
            "player_id": [1],
            "gw": [1],
            "apex_xp": [4.0],
            "apex_sd": [1.0],
            "airsenal_xp": [forecast.loc[0, "airsenal_xp"]],
            "xp_appearance": [1.5],
            "minutes_confidence": [0.8],
            "role_confidence": [0.8],
            "apex_model_reliability": [1.0],
        }
    )
    blended = blend_projection(
        base,
        {"official_ep": 0.0, "apex_model": 0.5, "airsenal": 0.5, "market": 0.0},
        0.15,
    )
    assert blended.loc[0, "xp"] == pytest.approx(4.0)
    assert blended.loc[0, "effective_weight_airsenal"] == pytest.approx(0.0)
    assert blended.loc[0, "effective_weight_airsenal_fallback_apex"] == pytest.approx(0.5)


def test_airsenal_raw_matrix_contract_rejects_missing_player_gameweek_pair(tmp_path: Path):
    worker = _script("run_airsenal_worker.py")
    path = tmp_path / "airsenal.csv"
    pd.DataFrame(
        [
            {"player_id": 1, "gw": 1, "xp": 1.0},
            {"player_id": 1, "gw": 2, "xp": 1.0},
            {"player_id": 2, "gw": 1, "xp": 1.0},
        ]
    ).to_csv(path, index=False)
    with pytest.raises(SystemExit, match="complete official player/Gameweek matrix"):
        worker._assert_export_contract(path, {1, 2}, [1, 2])


def test_validated_bundle_publication_never_overwrites_old_target_on_capture_failure(
    tmp_path: Path, monkeypatch
):
    module = _script("build_decision_bundle.py")
    target = tmp_path / "decision_bundle"
    target.mkdir()
    (target / "manifest.json").write_text("old", encoding="utf-8")

    class FakeBundle:
        @staticmethod
        def capture(*args, **kwargs):
            staging = Path(args[2])
            staging.mkdir(parents=True, exist_ok=True)
            (staging / "partial").write_text("partial", encoding="utf-8")
            raise RuntimeError("capture failed")

        @staticmethod
        def load(path):  # pragma: no cover - must never be reached
            raise AssertionError(path)

    monkeypatch.setattr(module, "DecisionBundle", FakeBundle)
    with pytest.raises(RuntimeError, match="capture failed"):
        module._capture_validated_bundle(
            SimpleNamespace(),
            SimpleNamespace(),
            target,
            repo_root=ROOT,
        )
    assert (target / "manifest.json").read_text(encoding="utf-8") == "old"
    assert not any(tmp_path.glob(".decision_bundle.staging-*"))


def test_validated_bundle_publication_promotes_only_after_reopen_validation(
    tmp_path: Path, monkeypatch
):
    module = _script("build_decision_bundle.py")
    target = tmp_path / "decision_bundle"
    target.mkdir()
    (target / "manifest.json").write_text("old", encoding="utf-8")
    loaded_paths = []

    class FakeBundle:
        @staticmethod
        def capture(*args, **kwargs):
            staging = Path(args[2])
            staging.mkdir(parents=True, exist_ok=True)
            (staging / "manifest.json").write_text("new", encoding="utf-8")
            return SimpleNamespace(bundle_id="sealed")

        @staticmethod
        def load(path):
            path = Path(path)
            loaded_paths.append(path.name)
            assert (path / "manifest.json").read_text(encoding="utf-8") == "new"
            return SimpleNamespace(bundle_id="sealed")

    monkeypatch.setattr(module, "DecisionBundle", FakeBundle)
    result = module._capture_validated_bundle(
        SimpleNamespace(),
        SimpleNamespace(),
        target,
        repo_root=ROOT,
    )
    assert result.bundle_id == "sealed"
    assert (target / "manifest.json").read_text(encoding="utf-8") == "new"
    assert len(loaded_paths) == 2
