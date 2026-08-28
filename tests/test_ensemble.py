import pandas as pd
import pytest

from apex_fpl.models.ensemble import blend_projection


def test_missing_configured_airsenal_weight_is_explicitly_delegated_to_apex():
    df = pd.DataFrame([{"apex_xp": 6.0, "official_xp": 4.0, "apex_sd": 0.0}])
    out = blend_projection(
        df,
        {"apex_model": 0.5, "official_ep": 0.5, "airsenal": 0.5},
        0,
    ).iloc[0]

    assert abs(out["xp"] - (16.0 / 3.0)) < 1e-9
    assert out["effective_weight_apex_model"] == (2.0 / 3.0)
    assert out["effective_weight_apex_model_direct"] == (1.0 / 3.0)
    assert out["effective_weight_official_ep"] == (1.0 / 3.0)
    assert out["effective_weight_airsenal"] == 0.0
    assert out["effective_weight_airsenal_fallback_apex"] == (1.0 / 3.0)
    assert bool(out["airsenal_source_absent"])


def test_positive_market_weight_without_market_surface_fails_closed():
    df = pd.DataFrame(
        [{"apex_xp": 6.0, "official_xp": 4.0, "airsenal_xp": 5.0, "apex_sd": 0.0}]
    )
    with pytest.raises(ValueError, match="positive market ensemble weight"):
        blend_projection(
            df,
            {
                "apex_model": 0.46,
                "official_ep": 0.24,
                "airsenal": 0.20,
                "market": 0.10,
            },
            0,
        )


def test_airsenal_structural_zero_abstains_when_current_role_sources_disagree():
    df = pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 1,
                "apex_xp": 5.0,
                "official_xp": 2.5,
                "airsenal_xp": 0.0,
                "xp_appearance": 1.5,
                "apex_sd": 0.0,
            },
            {
                "player_id": 1,
                "gw": 2,
                "apex_xp": 4.5,
                "official_xp": None,
                "airsenal_xp": 0.0,
                "xp_appearance": 1.4,
                "apex_sd": 0.0,
            },
        ]
    )
    out = blend_projection(
        df,
        {"apex_model": 0.6, "official_ep": 0.2, "airsenal": 0.2, "market": 0.0},
        0,
    )

    assert out["airsenal_abstained_role_conflict"].tolist() == [True, True]
    assert out["source_present_airsenal"].tolist() == [True, True]
    assert out["source_usable_airsenal"].tolist() == [False, False]
    assert out["effective_weight_airsenal"].tolist() == [0.0, 0.0]
    assert (out["effective_weight_airsenal_fallback_apex"] > 0).all()
    assert out.iloc[0]["effective_weight_apex_model"] == pytest.approx(0.8)
    assert out.iloc[0]["effective_weight_apex_model_direct"] == pytest.approx(0.6)
    assert out.iloc[0]["xp"] == pytest.approx(4.5)
    assert out.iloc[1]["xp"] == pytest.approx(4.5)


def test_airsenal_zero_remains_valid_when_current_role_evidence_does_not_conflict():
    df = pd.DataFrame(
        [{
            "player_id": 2,
            "gw": 1,
            "apex_xp": 0.4,
            "official_xp": 0.2,
            "airsenal_xp": 0.0,
            "xp_appearance": 0.3,
            "apex_sd": 0.0,
        }]
    )
    out = blend_projection(
        df,
        {"apex_model": 0.6, "official_ep": 0.2, "airsenal": 0.2, "market": 0.0},
        0,
    ).iloc[0]

    assert bool(out["airsenal_abstained_role_conflict"]) is False
    assert bool(out["source_usable_airsenal"]) is True
    assert out["effective_weight_airsenal"] == pytest.approx(0.2)
    assert out["xp"] == pytest.approx(0.28)


def test_forecast_uncertainty_excludes_match_outcome_variance():
    df = pd.DataFrame(
        [{"apex_xp": 6.0, "official_xp": 6.0, "apex_sd": 10.0}]
    )
    out = blend_projection(
        df,
        {"apex_model": 0.5, "official_ep": 0.5},
        0,
    ).iloc[0]
    assert out["projection_sd"] >= 10.0
    assert out["forecast_uncertainty_sd"] < 2.0


def test_risk_is_diagnostic_and_cannot_lower_canonical_expected_points():
    df = pd.DataFrame(
        [{
            "apex_xp": 7.0,
            "official_xp": 7.0,
            "apex_sd": 4.0,
            "minutes_confidence": 0.35,
            "role_confidence": 0.35,
        }]
    )
    out = blend_projection(
        df,
        {"apex_model": 0.5, "official_ep": 0.5},
        0.20,
    ).iloc[0]
    assert out["xp"] == 7.0
    assert out["canonical_ev_xp"] == 7.0
    assert out["risk_adjusted_xp"] == 7.0
    assert out["downside_adjusted_xp"] < 7.0
    assert out["projection_confidence"] < 1.0


def test_nyoni_class_unsupported_apex_outlier_is_attenuated_and_propagates():
    """Research-regression for a large Apex/independent-model disagreement.

    Production no longer uses this blended path. This deliberately non-production
    weight set keeps the legacy comparison machinery testable without encoding a
    second canonical policy.
    """
    df = pd.DataFrame(
        [
            {
                "player_id": 375,
                "gw": 1,
                "apex_xp": 7.93,
                "official_xp": 1.50,
                "airsenal_xp": 1.03,
                "apex_model_reliability": 0.25,
                "apex_sd": 1.0,
            },
            {
                "player_id": 375,
                "gw": 2,
                "apex_xp": 7.40,
                "official_xp": None,
                "airsenal_xp": 1.03,
                "apex_model_reliability": 0.25,
                "apex_sd": 1.0,
            },
        ]
    )
    weights = {
        "official_ep": 0.30,
        "apex_model": 0.50,
        "airsenal": 0.20,
        "market": 0.0,
    }
    out = blend_projection(df, weights, 0)

    gw1, gw2 = out.iloc[0], out.iloc[1]
    assert bool(gw1["apex_reliability_conflict"]) is True
    assert bool(gw1["apex_reliability_conflict_inherited"]) is False
    assert gw1["independent_expert_count"] == 2
    assert gw1["apex_reliability_weight_multiplier"] == pytest.approx(0.25)
    assert gw1["xp"] < 3.20
    assert gw1["xp"] < 4.68

    assert bool(gw2["apex_reliability_conflict"]) is False
    assert bool(gw2["apex_reliability_conflict_inherited"]) is True
    assert gw2["independent_expert_count"] == 1
    assert gw2["apex_reliability_weight_multiplier"] == pytest.approx(0.25)
    assert gw2["xp"] < 3.50


def test_high_reliability_apex_outlier_keeps_nominal_research_vote():
    df = pd.DataFrame(
        [{
            "player_id": 9,
            "gw": 1,
            "apex_xp": 7.93,
            "official_xp": 1.50,
            "airsenal_xp": 1.03,
            "apex_model_reliability": 1.0,
            "apex_sd": 1.0,
        }]
    )
    weights = {
        "official_ep": 0.30,
        "apex_model": 0.50,
        "airsenal": 0.20,
        "market": 0.0,
    }
    out = blend_projection(df, weights, 0).iloc[0]
    expected = 7.93 * weights["apex_model"] + 1.50 * weights["official_ep"] + 1.03 * weights["airsenal"]

    assert bool(out["apex_reliability_conflict"]) is False
    assert out["apex_reliability_weight_multiplier"] == pytest.approx(1.0)
    assert out["xp"] == pytest.approx(expected)


def test_weak_reliability_without_independent_disagreement_does_not_penalise_ev():
    df = pd.DataFrame(
        [{
            "player_id": 10,
            "gw": 1,
            "apex_xp": 5.0,
            "official_xp": 4.8,
            "airsenal_xp": 4.9,
            "apex_model_reliability": 0.20,
            "minutes_confidence": 0.35,
            "role_confidence": 0.35,
            "apex_sd": 1.0,
        }]
    )
    weights = {"apex_model": 0.5, "official_ep": 0.3, "airsenal": 0.2}
    out = blend_projection(df, weights, 0).iloc[0]
    expected = 5.0 * 0.5 + 4.8 * 0.3 + 4.9 * 0.2

    assert bool(out["apex_reliability_conflict"]) is False
    assert out["apex_reliability_weight_multiplier"] == pytest.approx(1.0)
    assert out["xp"] == pytest.approx(expected)
