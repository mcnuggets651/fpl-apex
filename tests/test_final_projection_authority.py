import pandas as pd
import pytest

from apex_fpl.config import Settings, load_settings
from apex_fpl.data.understat import UnderstatDataError, decode_league_payload
from apex_fpl.models.ensemble import blend_projection
from apex_fpl.services.prospective_ledger import provider_ledger_from_forecast


def _weights():
    return {"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0}


def test_airsenal_is_direct_production_authority_and_apex_is_shadow():
    base = pd.DataFrame([{
        "player_id": 1, "gw": 2, "apex_xp": 39.0, "official_xp": 25.0,
        "airsenal_xp": 21.0, "minutes_confidence": 0.8, "role_confidence": 0.8,
    }])
    row = blend_projection(base, _weights(), 0.15).iloc[0]
    assert row["xp"] == pytest.approx(21.0)
    assert row["production_xp"] == pytest.approx(21.0)
    assert row["apex_shadow_xp"] == pytest.approx(39.0)
    assert row["projection_provider"] == "AIrsenal"
    assert row["projection_authority"] == "production"
    assert row["apex_projection_authority"] == "shadow"
    assert row["model_disagreement"] == "high"


def test_shadow_change_cannot_modify_canonical_xp():
    base = pd.DataFrame([{"player_id": 1, "gw": 2, "apex_xp": 39.0, "airsenal_xp": 21.0}])
    changed = base.assign(apex_xp=99.0)
    assert blend_projection(base, _weights(), 0).iloc[0]["xp"] == pytest.approx(21.0)
    assert blend_projection(changed, _weights(), 0).iloc[0]["xp"] == pytest.approx(21.0)


def test_missing_canonical_airsenal_never_falls_back_to_apex():
    base = pd.DataFrame([{"player_id": 1, "gw": 2, "apex_xp": 39.0, "airsenal_xp": None}])
    row = blend_projection(base, _weights(), 0).iloc[0]
    assert pd.isna(row["xp"])
    assert bool(row["airsenal_source_absent"])
    assert row["effective_weight_airsenal_fallback_apex"] == 0.0


def test_default_and_live_config_are_one_hot_airsenal_and_core_is_optional():
    for settings in (Settings(), load_settings()):
        assert settings.weights == {"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0}
        assert "airsenal" in settings.required_sources
        assert "fpl_core_playerstats" not in settings.required_sources
        assert "fixture_model" not in settings.required_sources
        assert settings.understat_team_model_mode == "shadow"


def test_understat_empty_http_200_payload_is_unhealthy():
    with pytest.raises(UnderstatDataError, match="empty"):
        decode_league_payload({"dates": [], "teams": {}})


def test_provider_ledger_marks_airsenal_production_and_apex_shadow():
    forecast = pd.DataFrame([{
        "player_id": 1, "gw": 2, "deadline_time": "2026-08-29T10:00:00+00:00",
        "forecast_generated_at": "2026-08-28T09:00:00+00:00", "official_snapshot_id": "abc",
        "airsenal_xp": 4.2, "apex_shadow_xp": 6.1, "official_xp": 4.0,
        "expected_minutes": 80, "appearance_probability": 0.98, "position": "MID",
        "price": 7.0, "team_name": "Example",
    }])
    ledger = provider_ledger_from_forecast(forecast, season="2026-2027", source_versions={"AIrsenal": "sha"})
    air = ledger[ledger.provider == "AIrsenal"].iloc[0]
    apex = ledger[ledger.provider == "Apex proprietary"].iloc[0]
    assert air.authority == "production" and air.provider_version == "sha"
    assert apex.authority == "shadow"
