import pandas as pd

from apex_fpl.data.official import OfficialSnapshot
from apex_fpl.models.ensemble import blend_projection
from apex_fpl.models.minutes import minutes_profile
from apex_fpl.services.provenance import SourceStatus
from apex_fpl.services.safety import assess_safety


def test_ensemble_quantifies_disagreement():
    df = pd.DataFrame({
        "apex_xp": [8.0, 6.0], "official_xp": [8.1, 6.1], "airsenal_xp": [7.9, 1.0],
        "apex_sd": [1.0, 1.0], "minutes_confidence": [0.9, 0.9], "role_confidence": [0.8, 0.8],
    })
    out = blend_projection(df, {"apex_model": .5, "official_ep": .2, "airsenal": .3}, .15)
    assert out.loc[1, "expert_disagreement_sd"] > out.loc[0, "expert_disagreement_sd"]
    assert out.loc[1, "projection_confidence"] < out.loc[0, "projection_confidence"]
    assert (out["projection_floor_80"] <= out["xp"]).all()
    assert (out["projection_ceiling_80"] >= out["xp"]).all()


def test_minutes_profile_has_probabilities():
    df = pd.DataFrame({"minutes": [900], "starts": [10], "starts_per_90": [1], "status": ["a"]})
    out = minutes_profile(df)
    assert 70 <= out.loc[0, "expected_minutes"] <= 90
    assert 0 <= out.loc[0, "start_probability"] <= 1
    assert out.loc[0, "appearance_probability"] >= out.loc[0, "start_probability"]
    assert 0 <= out.loc[0, "minutes_confidence"] <= 1


def test_full_apex_gate_blocks_unconfigured_required_sources():
    players = pd.DataFrame({"player_id": [1], "position": ["FWD"]})
    snap = OfficialSnapshot(players, pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}, retrieved_at="")
    sources = [
        SourceStatus("official_fpl", True), SourceStatus("fpl_core_playerstats", True),
        SourceStatus("airsenal", True, configured=False), SourceStatus("news_feeds", True, configured=False),
    ]
    projection = pd.DataFrame({"player_id": [1], "projection_confidence": [.8]})
    class Sol: status = "Optimal"
    out = assess_safety(snap, sources, pd.DataFrame(), projection, {"x": Sol()}, ["official_fpl", "fpl_core_playerstats", "airsenal", "news_feeds"])
    assert not out.safe_to_act
    assert not out.full_apex_ready
    assert any("airsenal" in x for x in out.blockers)
