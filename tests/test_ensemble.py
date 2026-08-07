import pandas as pd

from apex_fpl.models.ensemble import blend_projection


def test_weights_renormalise_when_expert_missing():
    df = pd.DataFrame([{"apex_xp": 6.0, "official_xp": 4.0, "apex_sd": 0.0}])
    out = blend_projection(df, {"apex_model": .5, "official_ep": .5, "airsenal": .5}, 0)
    assert abs(out.iloc[0]["xp"] - 5.0) < 1e-9


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
