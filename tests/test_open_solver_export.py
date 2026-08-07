from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest


def test_open_solver_export_uses_official_ids_and_gw_columns(tmp_path: Path):
    players = pd.DataFrame(
        [
            {
                "player_id": 101,
                "web_name": "Keeper",
                "position": "GK",
                "price": 4.5,
                "expected_minutes": 90.0,
            },
            {
                "player_id": 202,
                "web_name": "Forward",
                "position": "FWD",
                "price": 8.0,
                "expected_minutes": 80.0,
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
    players_path = tmp_path / "players.csv"
    projections_path = tmp_path / "projections.csv"
    output = tmp_path / "apex.csv"
    players.to_csv(players_path, index=False)
    projections.to_csv(projections_path, index=False)

    script = Path(__file__).parents[1] / "scripts" / "export_open_solver.py"
    subprocess.run(
        [sys.executable, str(script), str(players_path), str(projections_path), str(output)],
        check=True,
    )
    out = pd.read_csv(output).set_index("ID")
    assert set(out.index) == {101, 202}
    assert out.loc[101, "Pos"] == "G"
    assert out.loc[202, "Pos"] == "F"
    assert out.loc[202, "2_Pts"] == pytest.approx(7.0)
    assert out.loc[202, "2_xMins"] == pytest.approx(160.0)
