import pandas as pd

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
    assert out["effective_weight_apex_model"] == (1.0 / 3.0)
    assert out["effective_weight_official_ep"] == (1.0 / 3.0)
    assert out["effective_weight_airsenal"] == 0.0
    assert out["effective_weight_airsenal_fallback_apex"] == (1.0 / 3.0)
    assert bool(out["airsenal_source_absent"])


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
