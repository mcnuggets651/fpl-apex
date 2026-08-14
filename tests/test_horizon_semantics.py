from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.services.pipeline import _horizon_totals, _summarise_horizons


def _surface() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "player_id": [1, 1, 1],
            "gw": [1, 2, 3],
            "canonical_ev_xp": [10.0, 10.0, 10.0],
            "risk_adjusted_xp": [10.0, 10.0, 10.0],
            "weighted_xp": [10.0, 9.0, 8.1],
            "projection_confidence": [0.8, 0.8, 0.8],
        }
    )


def test_xpts_are_raw_cumulative_expected_points_not_discounted_utility():
    summary = _summarise_horizons(_surface(), [1, 2, 3]).iloc[0]
    assert summary["xpts_1"] == pytest.approx(10.0)
    assert summary["xpts_3"] == pytest.approx(30.0)
    assert summary["xpts_3"] != pytest.approx(27.1)


def test_horizon_totals_expose_raw_xp_and_discounted_utility_separately():
    totals = _horizon_totals(_surface()).iloc[0]
    assert totals["raw_horizon_xp"] == pytest.approx(30.0)
    assert totals["horizon_xp"] == pytest.approx(30.0)
    assert totals["discounted_horizon_utility"] == pytest.approx(27.1)


def test_no_decay_makes_raw_xp_equal_utility():
    surface = _surface()
    surface["weighted_xp"] = surface["canonical_ev_xp"]
    totals = _horizon_totals(surface).iloc[0]
    assert totals["raw_horizon_xp"] == pytest.approx(totals["discounted_horizon_utility"])
