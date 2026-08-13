from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def load_module(name: str, filename: str):
    path = Path(__file__).parents[1] / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parity_shadow_reconstructs_production_preseason_blend() -> None:
    module = load_module("shrinkage_shadow_parity", "shrinkage_shadow_parity.py")
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
            "expected_assists_per_90": 0.2,
            "previous_expected_assists_per_90": 0.2,
            "defensive_contribution_per_90": 0.0,
            "previous_defensive_contribution_per_90": 0.0,
            "preseason_minutes": 135.0,
            "preseason_xg90": 0.5,
            "preseason_xa90": 0.1,
        }
    ])
    pre_weight = 0.35 * 0.5
    model_xg = 1.0 * (1 - pre_weight) + 0.5 * pre_weight
    model_xa = 0.2 * (1 - pre_weight) + 0.1 * pre_weight
    projections = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "model_xg90": model_xg,
            "model_xa90": model_xa,
            "xp_attack": 4.0,
            "apex_xp": 6.0,
            "xp": 5.0,
            "xp_expert_apex_model": 3.0,
            "effective_weight_apex_model": 0.5,
        }
    ])
    audit, shadow = module.parity_shadow(projections, players)
    assert abs(audit.loc[0, "raw_model_xg90"] - model_xg) < 1e-12
    assert abs(audit.loc[0, "raw_model_xa90"] - model_xa) < 1e-12
    assert "shrunk_blended_xp_v2" in shadow.columns


def test_parity_shadow_fails_when_reconstructed_rate_differs_from_production() -> None:
    module = load_module("shrinkage_shadow_parity", "shrinkage_shadow_parity.py")
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
            "expected_assists_per_90": 0.2,
            "previous_expected_assists_per_90": 0.2,
            "defensive_contribution_per_90": 0.0,
            "previous_defensive_contribution_per_90": 0.0,
            "preseason_minutes": 0.0,
        }
    ])
    projections = pd.DataFrame([
        {
            "player_id": 1,
            "gw": 1,
            "model_xg90": 0.7,
            "model_xa90": 0.2,
            "xp_attack": 4.0,
            "apex_xp": 6.0,
            "xp": 5.0,
            "xp_expert_apex_model": 3.0,
            "effective_weight_apex_model": 0.5,
        }
    ])
    with pytest.raises(ValueError, match="production input parity failed"):
        module.parity_shadow(projections, players)
