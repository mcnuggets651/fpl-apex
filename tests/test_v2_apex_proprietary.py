from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from apex.domain.models import (
    OfficialFixture,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
)
from apex.forecast.adapters.apex_proprietary import load_apex_proprietary
from apex.runtime.config import CURRENT_SCORING_RULES_VERSION


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        schema_version=1,
        season="2026-2027",
        acquired_at="2026-08-30T10:00:00+00:00",
        source_hash="official-hash",
        players=(
            OfficialPlayer(1, "Alpha", 1, Position.MID, 70, "a", True, 1001),
            OfficialPlayer(2, "Beta", 2, Position.FWD, 75, "a", True, 1002),
        ),
        fixtures=(
            OfficialFixture(10, 3, 1, 2, "2026-09-04T19:00:00Z"),
            OfficialFixture(11, 4, 2, 1, "2026-09-12T14:00:00Z"),
        ),
        deadlines={
            3: "2026-09-04T17:30:00Z",
            4: "2026-09-12T12:30:00Z",
        },
    )


def _worker_module():
    script = Path(__file__).resolve().parents[1] / "scripts/acquire_apex_proprietary_shadow.py"
    spec = importlib.util.spec_from_file_location("apex_proprietary_worker", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_apex_proprietary_adapter_is_a_separate_v2_surface(tmp_path):
    path = tmp_path / "apex.csv"
    pd.DataFrame(
        [
            {
                "element_id": player,
                "gameweek": gw,
                "expected_points": points,
                "expected_minutes": 80.0,
                "generated_at": "2026-08-30T11:00:00+00:00",
                "provider_version": "apex-proprietary-v1@test",
                "scoring_rules_version": CURRENT_SCORING_RULES_VERSION,
                "source_snapshot": "official-hash",
                "coverage_status": "FORECAST",
            }
            for player, gw, points in (
                (1, 3, 5.5),
                (2, 3, 4.0),
                (1, 4, 4.5),
                (2, 4, 5.0),
            )
        ]
    ).to_csv(path, index=False)

    surface = load_apex_proprietary(path, official=_official(), target_gameweek=3)
    assert surface.provider_id == "apex_proprietary"
    assert surface.supported_horizons == (1, 2)
    assert surface.source_snapshot == "official-hash"
    assert len(surface.rows) == 4


def test_raw_export_ignores_legacy_blended_columns():
    module = _worker_module()
    projections = pd.DataFrame(
        [
            {"player_id": 1, "gw": 3, "apex_xp": 5.0, "risk_adjusted_xp": 99.0},
            {"player_id": 2, "gw": 3, "apex_xp": 3.0, "risk_adjusted_xp": 99.0},
            {"player_id": 1, "gw": 4, "apex_xp": 4.0, "risk_adjusted_xp": 99.0},
            {"player_id": 2, "gw": 4, "apex_xp": 6.0, "risk_adjusted_xp": 99.0},
        ]
    )
    players = pd.DataFrame(
        [
            {
                "player_id": 1,
                "expected_minutes": 80.0,
                "appearance_probability": 0.95,
                "start_probability": 0.90,
                "minutes_60_plus_probability": 0.85,
            },
            {
                "player_id": 2,
                "expected_minutes": 75.0,
                "appearance_probability": 0.93,
                "start_probability": 0.86,
                "minutes_60_plus_probability": 0.80,
            },
        ]
    )
    exported = module._export_raw_apex(
        projections,
        players,
        official=_official(),
        gameweeks=[3, 4],
        generated_at="2026-08-30T11:00:00+00:00",
        code_sha="abcdef1234567890",
    )
    assert exported["expected_points"].tolist() == [5.0, 4.0, 3.0, 6.0]
    assert 99.0 not in set(exported["expected_points"])
    assert set(exported["model_contract"]) == {"RAW_APEX_XP_ONLY_V1"}


def test_runtime_core_lock_pins_resolved_commit_without_mutating_repo_lock(tmp_path):
    module = _worker_module()
    base = tmp_path / "base.lock.json"
    original = {
        "schema_version": 1,
        "sources": {
            "fpl_core_insights": {
                "repository": module.CORE_REPOSITORY,
                "commit": "a" * 40,
                "committed_at": "2026-08-18T00:00:00+00:00",
                "required_for_full_apex": True,
            },
            "airsenal": {"commit": "b" * 40},
        },
    }
    base.write_text(json.dumps(original), encoding="utf-8")
    runtime = module._runtime_core_lock(
        base,
        tmp_path / "runtime.lock.json",
        resolved={
            "sha": "c" * 40,
            "committed_at": "2026-08-30T01:30:01+00:00",
            "age_hours": 10.5,
        },
        now=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc),
    )
    assert json.loads(base.read_text(encoding="utf-8")) == original
    payload = json.loads(runtime.read_text(encoding="utf-8"))
    core = payload["sources"]["fpl_core_insights"]
    assert core["commit"] == "c" * 40
    assert core["required_for_full_apex"] is False
    assert payload["sources"]["airsenal"]["commit"] == "b" * 40


def test_internal_source_gate_rejects_degraded_challenger():
    module = _worker_module()
    sources = [
        SimpleNamespace(name=name, ok=(name != "fpl_core_previous_season"), detail=name, version="v")
        for name in module.REQUIRED_INTERNAL_SOURCES
    ]
    with pytest.raises(RuntimeError, match="fpl_core_previous_season"):
        module._assert_internal_source_health(sources)
