from __future__ import annotations

import numpy as np
import pandas as pd

from apex_fpl.models.ensemble import blend_projection
from apex_fpl.services.projection_audit import (
    build_fixture_shadow_comparison,
    build_player_shadow_comparison,
    build_projection_decomposition,
    reprice_apex_for_fixture_shadow,
)


def test_expert_contributions_sum_to_canonical_xp() -> None:
    base = pd.DataFrame(
        {
            "player_id": [1, 2],
            "gw": [1, 1],
            "apex_xp": [4.0, 3.0],
            "official_xp": [5.0, np.nan],
            "airsenal_xp": [6.0, 4.0],
            "apex_sd": [1.0, 1.0],
            "minutes_confidence": [0.8, 0.8],
            "role_confidence": [0.8, 0.8],
            "xp_appearance": [1.5, 1.2],
            "xp_attack": [1.0, 0.8],
            "xp_clean_sheet": [0.5, 0.4],
            "xp_defensive_contribution": [0.4, 0.3],
            "xp_saves": [0.0, 0.0],
            "xp_bonus_prior": [0.4, 0.2],
            "xp_set_piece_prior": [0.2, 0.1],
        }
    )
    weights = {"official_ep": 0.24, "apex_model": 0.46, "airsenal": 0.20, "market": 0.10}
    out = blend_projection(base, weights, risk_penalty=0.15)
    contrib_cols = [
        "xp_expert_official_ep",
        "xp_expert_apex_model",
        "xp_expert_airsenal",
        "xp_expert_market",
    ]
    assert np.allclose(out[contrib_cols].sum(axis=1), out["xp"])


def test_decomposition_preserves_canonical_and_apex_totals() -> None:
    base = pd.DataFrame(
        {
            "player_id": [1],
            "gw": [1],
            "apex_xp": [4.0],
            "official_xp": [5.0],
            "airsenal_xp": [6.0],
            "apex_sd": [1.0],
            "minutes_confidence": [0.8],
            "role_confidence": [0.8],
            "xp_appearance": [1.0],
            "xp_attack": [1.0],
            "xp_clean_sheet": [0.5],
            "xp_defensive_contribution": [0.5],
            "xp_saves": [0.0],
            "xp_bonus_prior": [0.5],
            "xp_set_piece_prior": [0.5],
        }
    )
    weights = {"official_ep": 0.24, "apex_model": 0.46, "airsenal": 0.20, "market": 0.10}
    out = blend_projection(base, weights, risk_penalty=0.15)
    audit = build_projection_decomposition(out, [1])
    row = audit.iloc[0]
    expert_total = (
        row["raw_horizon_official_contribution"]
        + row["raw_horizon_apex_contribution"]
        + row["raw_horizon_airsenal_contribution"]
        + row["raw_horizon_market_contribution"]
    )
    component_total = sum(
        row[f"horizon_apex_{name}"]
        for name in [
            "appearance",
            "attack",
            "clean_sheet",
            "defcon",
            "saves",
            "bonus",
            "set_piece",
        ]
    )
    discounted_expert_total = (
        row["discounted_horizon_official_contribution"]
        + row["discounted_horizon_apex_contribution"]
        + row["discounted_horizon_airsenal_contribution"]
        + row["discounted_horizon_market_contribution"]
    )
    assert np.isclose(expert_total, row["raw_horizon_canonical_xp"])
    assert np.isclose(discounted_expert_total, row["discounted_horizon_utility"])
    # GW1 has discount 1.0, so the transparent Apex components reconcile exactly.
    assert np.isclose(component_total, row["raw_horizon_apex_contribution"])


def test_fixture_shadow_comparison_reports_deltas() -> None:
    prod = pd.DataFrame(
        {
            "gw": [1],
            "team": [1],
            "opponent": [2],
            "is_home": [True],
            "expected_team_goals": [1.4],
            "expected_goals_against": [1.2],
            "clean_sheet_prob": [0.30],
            "attack_multiplier": [0.9],
            "defence_multiplier": [1.1],
        }
    )
    shadow = prod.copy()
    shadow["expected_team_goals"] = 1.7
    shadow["clean_sheet_prob"] = 0.4
    audit = build_fixture_shadow_comparison(prod, shadow)
    assert np.isclose(audit.iloc[0]["delta_expected_team_goals"], 0.3)
    assert np.isclose(audit.iloc[0]["delta_clean_sheet_prob"], 0.1)


def test_fixture_shadow_repricing_changes_only_fixture_sensitive_components() -> None:
    projection = pd.DataFrame(
        {
            "player_id": [10],
            "gw": [1],
            "opponent": [2],
            "is_home": [True],
            "apex_xp": [5.0],
            "xp_appearance": [1.5],
            "xp_attack": [1.0],
            "xp_clean_sheet": [1.0],
            "xp_defensive_contribution": [0.5],
            "xp_saves": [0.2],
            "xp_bonus_prior": [0.5],
            "xp_set_piece_prior": [0.3],
        }
    )
    prod_fx = pd.DataFrame(
        {
            "gw": [1],
            "team": [1],
            "opponent": [2],
            "is_home": [True],
            "attack_multiplier": [1.0],
            "clean_sheet_prob": [0.25],
        }
    )
    shadow_fx = prod_fx.copy()
    shadow_fx["attack_multiplier"] = 1.2
    shadow_fx["clean_sheet_prob"] = 0.50
    teams = pd.DataFrame({"player_id": [10], "team": [1]})

    out = reprice_apex_for_fixture_shadow(projection, prod_fx, shadow_fx, teams)
    row = out.iloc[0]
    assert np.isclose(row["xp_attack"], 1.2)
    assert np.isclose(row["xp_clean_sheet"], 2.0)
    assert np.isclose(row["xp_defensive_contribution"], 0.5)
    assert np.isclose(row["xp_bonus_prior"], 0.5)
    assert np.isclose(row["apex_xp"], 6.2)


def test_player_shadow_comparison_separates_raw_xp_and_discounted_utility() -> None:
    prod = pd.DataFrame(
        {
            "player_id": [1, 1],
            "gw": [1, 2],
            "apex_xp": [4.0, 4.0],
            "xp_attack": [1.0, 1.0],
            "xp_clean_sheet": [1.0, 1.0],
        }
    )
    shadow = prod.copy()
    shadow["apex_xp"] = [5.0, 5.0]
    shadow["xp_attack"] = [1.5, 1.5]
    audit = build_player_shadow_comparison(prod, shadow, [1, 2], decay=0.9)
    row = audit.iloc[0]
    assert np.isclose(row["production_apex_xp_raw"], 8.0)
    assert np.isclose(row["shadow_apex_xp_raw"], 10.0)
    assert np.isclose(row["delta_apex_xp_raw"], 2.0)
    assert np.isclose(row["production_apex_xp_discounted_utility"], 7.6)
    assert np.isclose(row["shadow_apex_xp_discounted_utility"], 9.5)
    assert np.isclose(row["delta_apex_xp_discounted_utility"], 1.9)
