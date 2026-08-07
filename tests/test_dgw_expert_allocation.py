import pandas as pd

from apex_fpl.models.ensemble import blend_projection


def test_full_gameweek_experts_are_allocated_once_across_dgw_fixture_rows():
    rows = pd.DataFrame(
        [
            {
                "player_id": 1,
                "gw": 10,
                "apex_xp": 3.0,
                "official_xp": 8.0,
                "airsenal_xp": 10.0,
                "apex_sd": 0.0,
                "minutes_confidence": 1.0,
                "role_confidence": 1.0,
            },
            {
                "player_id": 1,
                "gw": 10,
                "apex_xp": 4.0,
                "official_xp": 8.0,
                "airsenal_xp": 10.0,
                "apex_sd": 0.0,
                "minutes_confidence": 1.0,
                "role_confidence": 1.0,
            },
        ]
    )
    out = blend_projection(
        rows,
        {"apex_model": 1.0, "official_ep": 1.0, "airsenal": 1.0},
        risk_penalty=0.0,
    )
    # Each external expert is a GW total and is split 50/50 across the two
    # transparent fixture rows. Their totals therefore remain 8 and 10, not 16/20.
    assert out["expert_allocation_count"].tolist() == [2, 2]
    assert abs(out["official_xp"].sum() - 8.0) < 1e-9
    assert abs(out["airsenal_xp"].sum() - 10.0) < 1e-9
    # Blended total = [(3+4) + 8 + 10] / 3 = 25/3.
    assert abs(out["xp"].sum() - (25.0 / 3.0)) < 1e-9
