from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd


def helper_module():
    path = Path(__file__).parents[1] / "scripts" / "shrinkage_shadow_surface.py"
    spec = importlib.util.spec_from_file_location("shrinkage_shadow_surface", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_shadow_replaces_only_apex_weighted_attack_contribution() -> None:
    module = helper_module()
    players = pd.DataFrame([
        {
            "player_id": 1,
            "web_name": "Example",
            "position": "MID",
            "price": 5.5,
            "minutes": 0.0,
            "previous_minutes": 90.0,
            "expected_goals_per_90": 1.0,
            "previous_expected_goals_per_90": 1.0,
            "expected_assists_per_90": 0.0,
            "previous_expected_assists_per_90": 0.0,
            "defensive_contribution_per_90": 0.0,
            "previous_defensive_contribution_per_90": 0.0,
        }
    ])
    projections = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "model_xg90": 1.0,
            "model_xa90": 0.0,
            "xp_attack": 5.0,
            "apex_xp": 7.0,
            "xp": 6.0,
            "xp_expert_apex_model": 3.5,
            "effective_weight_apex_model": 0.5,
        }
    ])
    _, audit, shadow = module.build_shadow(projections, players)
    assert audit.loc[0, "shrunk_xg90"] < audit.loc[0, "raw_xg90"]
    assert shadow.loc[0, "shrunk_apex_xp"] < shadow.loc[0, "raw_apex_xp"]
    expected = 6.0 - 3.5 + 0.5 * shadow.loc[0, "shrunk_apex_xp"]
    assert abs(shadow.loc[0, "shrunk_blended_xp"] - expected) < 1e-9


def test_horizon_gap_marks_low_evidence_player() -> None:
    module = helper_module()
    shadow = pd.DataFrame([
        {"player_id": 1, "gw": 1, "raw_apex_xp": 5.0, "shrunk_apex_xp": 3.0, "airsenal_xp": 2.0},
        {"player_id": 1, "gw": 2, "raw_apex_xp": 5.0, "shrunk_apex_xp": 3.0, "airsenal_xp": 2.0},
    ])
    audit = pd.DataFrame([
        {
            "player_id": 1,
            "web_name": "Example",
            "position": "MID",
            "price": 5.5,
            "xg90_combined_effective_evidence_minutes": 90.0,
            "xa90_combined_effective_evidence_minutes": 90.0,
        }
    ])
    gaps = module.horizon_gaps(shadow, audit, [1, 2], 1.0)
    assert gaps.loc[0, "evidence_minutes"] == 90.0
    assert gaps.loc[0, "shrunk_gap"] < gaps.loc[0, "raw_gap"]
