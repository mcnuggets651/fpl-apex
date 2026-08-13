from __future__ import annotations

import importlib.util
from pathlib import Path

import pandas as pd
import pytest


def module():
    path = Path(__file__).parents[1] / "scripts" / "shrinkage_shadow_parity.py"
    spec = importlib.util.spec_from_file_location("shadow", path)
    assert spec and spec.loader
    out = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(out)
    return out


def frame(with_evidence=True):
    mins = 90.0 if with_evidence else 0.0
    return pd.DataFrame([{
        "player_id": 1, "web_name": "P", "position": "MID", "price": 5.5,
        "minutes": mins, "previous_minutes": mins,
        "expected_goals_per_90": 1.0, "previous_expected_goals_per_90": 1.0,
        "expected_assists_per_90": 0.2, "previous_expected_assists_per_90": 0.2,
        "defensive_contribution_per_90": 0.0,
        "previous_defensive_contribution_per_90": 0.0,
        "preseason_minutes": 0.0,
    }])


def production(m, players):
    p = players.copy()
    p["shrinkage_group"] = m.position_price_tier_groups(p)
    s = m.shrink_player_rates(p).reset_index(drop=True)
    xg_ev = pd.to_numeric(s["xg90_combined_effective_evidence_minutes"], errors="coerce").fillna(0)
    xa_ev = pd.to_numeric(s["xa90_combined_effective_evidence_minutes"], errors="coerce").fillna(0)
    xg = pd.to_numeric(s["shrunk_xg90"]).where(xg_ev.gt(0), p["expected_goals_per_90"])
    xa = pd.to_numeric(s["shrunk_xa90"]).where(xa_ev.gt(0), p["expected_assists_per_90"])
    return pd.DataFrame([{
        "player_id": 1, "gw": 1, "model_xg90": float(xg.iloc[0]), "model_xa90": float(xa.iloc[0]),
        "xp_attack": 2.0, "apex_xp": 4.0, "xp": 3.5,
        "xp_expert_apex_model": 2.0, "effective_weight_apex_model": 0.5,
        "attack_rate_model": "active",
    }])


def test_activated_surface_is_not_shrunk_twice():
    m = module(); players = frame(True); proj = production(m, players)
    audit, shadow = m.parity_shadow(proj, players)
    assert audit.loc[0, "shrunk_model_xg90"] == pytest.approx(proj.loc[0, "model_xg90"])
    assert shadow.loc[0, "shrunk_blended_xp_v2"] == pytest.approx(shadow.loc[0, "xp"])
    assert "raw_counterfactual_blended_xp_v1" in shadow


def test_activated_surface_parity_fails_on_wrong_rate():
    m = module(); players = frame(True); proj = production(m, players)
    proj.loc[0, "model_xg90"] += 0.1
    with pytest.raises(ValueError, match="activated production parity failed"):
        m.parity_shadow(proj, players)


def test_zero_evidence_preserves_raw_rate():
    m = module(); players = frame(False); proj = production(m, players)
    audit, shadow = m.parity_shadow(proj, players)
    row = audit.iloc[0]
    assert row["xg90_prior_only_bypassed"] and row["xa90_prior_only_bypassed"]
    assert row["shrunk_model_xg90"] == pytest.approx(row["raw_model_xg90"])
    assert shadow.loc[0, "raw_counterfactual_blended_xp_v1"] == pytest.approx(shadow.loc[0, "xp"])
