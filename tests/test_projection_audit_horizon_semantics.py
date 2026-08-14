from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.services.projection_audit import build_projection_decomposition


def test_projection_audit_separates_raw_xp_from_discounted_utility():
    rows = []
    for gw in (1, 2):
        row = {
            "player_id": 1,
            "gw": gw,
            "xp": 10.0,
            "apex_xp": 10.0,
            "xp_expert_official_ep": 2.0,
            "xp_expert_apex_model": 5.0,
            "xp_expert_airsenal": 3.0,
            "xp_expert_market": 0.0,
        }
        for col in (
            "xp_appearance",
            "xp_attack",
            "xp_clean_sheet",
            "xp_defensive_contribution",
            "xp_saves",
            "xp_bonus_prior",
            "xp_set_piece_prior",
        ):
            row[col] = 10.0 / 7.0
        rows.append(row)
    out = build_projection_decomposition(pd.DataFrame(rows), [1, 2], decay=0.90).iloc[0]
    assert out["raw_horizon_canonical_xp"] == pytest.approx(20.0)
    assert out["discounted_horizon_utility"] == pytest.approx(19.0)
    assert out["raw_horizon_official_contribution"] == pytest.approx(4.0)
    assert out["discounted_horizon_official_contribution"] == pytest.approx(3.8)
