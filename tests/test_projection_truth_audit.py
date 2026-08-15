from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "audit_projection_truth.py"
SPEC = importlib.util.spec_from_file_location("audit_projection_truth", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_source_authority_exposes_configured_but_inactive_and_effective_weights():
    projections = pd.DataFrame(
        {
            "player_id": [1, 2, 1, 2],
            "gw": [1, 1, 2, 2],
            "official_xp": [4.0, 5.0, None, None],
            "apex_xp": [6.0, 6.0, 6.0, 6.0],
            "airsenal_xp": [5.0, 5.0, 5.0, 5.0],
            "market_xp": [None, None, None, None],
            "effective_weight_official_ep": [0.24 / 0.90, 0.24 / 0.90, 0.0, 0.0],
            "effective_weight_apex_model": [0.46 / 0.90, 0.46 / 0.90, 0.46 / 0.66, 0.46 / 0.66],
            "effective_weight_airsenal": [0.20 / 0.90, 0.20 / 0.90, 0.20 / 0.66, 0.20 / 0.66],
            "effective_weight_market": [0.0, 0.0, 0.0, 0.0],
            "xp_expert_official_ep": [1.0, 1.2, 0.0, 0.0],
            "xp_expert_apex_model": [3.0, 3.0, 4.0, 4.0],
            "xp_expert_airsenal": [1.0, 1.0, 1.5, 1.5],
            "xp_expert_market": [0.0, 0.0, 0.0, 0.0],
        }
    )
    weights = {"official_ep": 0.24, "apex_model": 0.46, "airsenal": 0.20, "market": 0.10}
    authority = MODULE.build_source_authority(projections, weights)

    gw2_apex = authority[(authority["gw"] == 2) & (authority["expert"] == "apex_model")].iloc[0]
    gw2_air = authority[(authority["gw"] == 2) & (authority["expert"] == "airsenal")].iloc[0]
    market = authority[authority["expert"] == "market"]

    assert gw2_apex["mean_effective_weight"] == pytest.approx(0.46 / 0.66)
    assert gw2_air["mean_effective_weight"] == pytest.approx(0.20 / 0.66)
    assert market["configured_but_inactive"].all()


def test_explicit_available_blend_matches_canonical_renormalisation():
    projections = pd.DataFrame(
        {
            "gw": [1, 2],
            "official_xp": [4.0, None],
            "apex_xp": [6.0, 6.0],
            "airsenal_xp": [5.0, 5.0],
            "market_xp": [None, None],
            "xp": [
                (4.0 * 0.24 + 6.0 * 0.46 + 5.0 * 0.20) / 0.90,
                (6.0 * 0.46 + 5.0 * 0.20) / 0.66,
            ],
        }
    )
    weights = {"official_ep": 0.24, "apex_model": 0.46, "airsenal": 0.20, "market": 0.10}
    surfaces = MODULE.build_ablation_surfaces(projections, weights)
    assert surfaces["explicit_available_sources"].tolist() == pytest.approx(projections["xp"].tolist())


def test_shortlist_regret_uses_exact_candidate_objectives_without_extra_solve():
    players = pd.DataFrame({"player_id": [1, 2, 3], "web_name": ["One", "Two", "Three"]})
    solution = SimpleNamespace(squad=players.iloc[:2].copy())
    candidates = (
        SimpleNamespace(squad_ids=(1, 2), exact_objective=100.0),
        SimpleNamespace(squad_ids=(2, 3), exact_objective=98.5),
        SimpleNamespace(squad_ids=(1, 3), exact_objective=97.0),
    )
    decision = SimpleNamespace(
        status="Optimal",
        objective=100.0,
        solution=solution,
        candidates=candidates,
    )
    regret = MODULE.build_shortlist_regret(decision, players).set_index("player_id")
    assert regret.loc[1, "objective_regret"] == pytest.approx(1.5)
    assert regret.loc[2, "objective_regret"] == pytest.approx(3.0)
    assert regret.loc[1, "replacement_player_ids"] == [3]


def test_component_contributions_can_reconcile_to_xp():
    projections = pd.DataFrame(
        {
            "xp": [5.5],
            "xp_expert_official_ep": [1.1],
            "xp_expert_apex_model": [2.8],
            "xp_expert_airsenal": [1.6],
            "xp_expert_market": [0.0],
        }
    )
    contribution_cols = [column for column in projections.columns if column.startswith("xp_expert_")]
    assert projections[contribution_cols].sum(axis=1).iloc[0] == pytest.approx(projections["xp"].iloc[0])


def test_disagreement_report_separates_raw_xp_from_discounted_utility():
    projections = pd.DataFrame(
        {
            "player_id": [1, 1],
            "gw": [1, 2],
            "apex_xp": [4.0, 4.0],
            "airsenal_xp": [5.0, 5.0],
            "model_xg90": [0.4, 0.4],
            "model_xa90": [0.2, 0.2],
        }
    )
    players = pd.DataFrame(
        {
            "player_id": [1],
            "web_name": ["Example"],
            "position": ["FWD"],
            "price": [7.5],
            "minutes": [900],
            "previous_minutes": [1800],
        }
    )
    report = MODULE.build_disagreement_report(
        projections, players, [1, 2], decay=0.90
    ).iloc[0]
    assert report["apex_raw_horizon_xp"] == pytest.approx(8.0)
    assert report["airsenal_raw_horizon_xp"] == pytest.approx(10.0)
    assert report["raw_apex_minus_airsenal_xp"] == pytest.approx(-2.0)
    assert report["raw_absolute_disagreement_xp"] == pytest.approx(2.0)
    assert report["apex_discounted_horizon_utility"] == pytest.approx(7.6)
    assert report["airsenal_discounted_horizon_utility"] == pytest.approx(9.5)
    assert report["discounted_apex_minus_airsenal_utility"] == pytest.approx(-1.9)
