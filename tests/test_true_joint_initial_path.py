import pandas as pd

from apex_fpl.services.joint_initial_path import optimise_joint_initial_path


def _players() -> pd.DataFrame:
    rows = []
    positions = {
        1: "GK",
        2: "GK",
        3: "DEF",
        4: "DEF",
        5: "DEF",
        6: "DEF",
        7: "DEF",
        8: "MID",
        9: "MID",
        10: "MID",
        11: "MID",
        12: "MID",  # GW1 punt A
        13: "MID",  # steady static pick B
        14: "FWD",
        15: "FWD",
        16: "FWD",
    }
    for pid, position in positions.items():
        rows.append(
            {
                "player_id": pid,
                "web_name": f"P{pid}",
                "team": f"T{pid}",
                "team_name": f"T{pid}",
                "position": position,
                "price": 5.0,
                "appearance_probability": 1.0,
                "xi_evidence_eligible": True,
            }
        )
    return pd.DataFrame(rows)


def _projections() -> pd.DataFrame:
    rows = []
    for gw in (1, 2):
        for pid in range(1, 17):
            if pid == 1:
                xp = 8.0
            elif pid == 2:
                xp = 0.0
            elif 3 <= pid <= 7:
                xp = 3.0
            elif 8 <= pid <= 11:
                xp = 20.0
            elif pid == 12:
                xp = 7.0 if gw == 1 else 0.0
            elif pid == 13:
                xp = 6.0
            else:
                xp = 4.0
            rows.append({"player_id": pid, "gw": gw, "xp": xp})
    return pd.DataFrame(rows)


def test_true_joint_path_selects_gw1_punt_then_uses_free_transfer() -> None:
    players = _players()
    projections = _projections()
    eligible = set(players["player_id"].astype(int))

    result = optimise_joint_initial_path(
        players,
        projections,
        [1, 2],
        budget=100.0,
        max_per_team=3,
        decay=1.0,
        projection_col="xp",
        captain_eligible=eligible,
        xi_eligible=eligible,
        per_view_candidates=3,
        transfer_candidate_limit=40,
        exact_candidate_limit=4,
    )

    assert result.status == "optimal"
    assert result.baseline is not None
    assert result.selected is not None

    # Exact fixed-squad mechanics can rotate a zero-point P12 to a four-point bench
    # alternative in GW2. The static hold therefore prefers P13: 6 + 6 = 12 beats
    # P12's 7 + 4 = 11. The transfer-aware policy can do better than either hold.
    assert 13 in result.baseline.squad_ids
    assert 12 not in result.baseline.squad_ids

    # The joint policy correctly starts P12 for GW1 and swaps to P13 in GW2:
    # 7 + 6 = 13, with the GW2 move covered by the one free transfer.
    assert 12 in result.selected.squad_ids
    assert 13 not in result.selected.squad_ids
    assert result.selected.total_objective > result.baseline.total_objective
    assert result.candidate_pool_stable is True

    assert len(result.selected.weeks) == 1
    gw2 = result.selected.weeks[0]
    assert gw2["gw"] == 2
    assert gw2["free_transfers_before"] == 1
    assert gw2["transfers"] == 1
    assert gw2["hit_cost"] == 0
    assert {row["player_id"] for row in gw2["transfers_out"]} == {12}
    assert {row["player_id"] for row in gw2["transfers_in"]} == {13}
