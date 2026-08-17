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

    # Configured weights normalise to one third each. A genuinely absent
    # AIrsenal source does not silently renormalise the surviving experts; its
    # one-third weight is explicitly delegated to Apex and remains auditable.
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
    # GW1 = (0.6*5 + 0.2*2.5 + 0.2*5) / 1.0.
    assert out.iloc[0]["xp"] == pytest.approx(4.5)
    # Official is unavailable after GW1, so Apex plus the explicit fallback retain
    # the whole usable weight rather than allowing the structural zero to suppress EV.
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
