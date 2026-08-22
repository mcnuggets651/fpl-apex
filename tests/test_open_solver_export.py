from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from apex_fpl.services.open_solver_export import export_bundle


def test_open_solver_export_uses_sealed_official_ids_and_gw_columns(tmp_path: Path):
    players = pd.DataFrame(
        [
            {
                "player_id": 101,
                "web_name": "Keeper",
                "position": "GK",
                "price": 4.5,
                "expected_minutes": 90.0,
                "team": 1,
            },
            {
                "player_id": 202,
                "web_name": "Forward",
                "position": "FWD",
                "price": 8.0,
                "expected_minutes": 80.0,
                "team": 2,
            },
        ]
    )
    projections = pd.DataFrame(
        [
            {"player_id": 101, "gw": 1, "risk_adjusted_xp": 4.2},
            {"player_id": 202, "gw": 1, "risk_adjusted_xp": 5.1},
            # DGW: two fixture rows must sum for the external solver.
            {"player_id": 202, "gw": 2, "risk_adjusted_xp": 4.0},
            {"player_id": 202, "gw": 2, "risk_adjusted_xp": 3.0},
            {"player_id": 101, "gw": 2, "risk_adjusted_xp": 3.8},
        ]
    )
    bundle = SimpleNamespace(
        players=players,
        projections=projections,
        manifest={"gameweeks": [1, 2]},
        bundle_id="test-sealed-bundle",
    )
    output = tmp_path / "apex.csv"

    export_bundle(bundle, output, projection_col="risk_adjusted_xp")

    out = pd.read_csv(output).set_index("ID")
    assert set(out.index) == {101, 202}
    assert out.loc[101, "Pos"] == "G"
    assert out.loc[202, "Pos"] == "F"
    assert out.loc[101, "TeamId"] == 1
    assert out.loc[202, "TeamId"] == 2
    assert out.loc[202, "2_Pts"] == pytest.approx(7.0)
    assert out.loc[202, "2_xMins"] == pytest.approx(160.0)
