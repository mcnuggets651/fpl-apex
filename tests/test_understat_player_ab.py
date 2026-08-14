from __future__ import annotations

import pandas as pd

from apex_fpl.evaluation.understat_player_ab import (
    map_understat_to_current_ids,
    reprice_projection_surface,
)


def test_map_understat_to_current_ids_uses_unique_full_names_only():
    core = pd.DataFrame(
        {
            "player_id": [1, 2],
            "first_name": ["João", "Alpha"],
            "second_name": ["Pedro", "Two"],
        }
    )
    understat = pd.DataFrame(
        {
            "player_name": ["Joao Pedro", "Alpha Two"],
            "understat_xg90": [0.5, 0.2],
            "understat_xa90": [0.2, 0.3],
        }
    )
    mapped = map_understat_to_current_ids(core, understat)
    assert set(mapped["player_id"]) == {1, 2}
    assert mapped.set_index("player_id").loc[1, "understat_xg90"] == 0.5


def test_reprice_projection_surface_changes_only_matched_attacking_signal():
    players = pd.DataFrame(
        {
            "player_id": [1, 2],
            "position": ["MID", "MID"],
            "expected_minutes": [90.0, 90.0],
        }
    )
    projections = pd.DataFrame(
        {
            "player_id": [1, 2],
            "gw": [1, 1],
            "apex_xp": [5.0, 4.0],
            "apex_sd": [1.5, 1.4],
            "xp_attack": [2.0, 1.0],
            "model_xg90": [0.4, 0.2],
            "model_xa90": [0.2, 0.1],
            "minutes_confidence": [0.9, 0.9],
            "role_confidence": [0.9, 0.9],
            "decay": [1.0, 1.0],
        }
    )
    rates = pd.DataFrame(
        {
            "player_id": [1],
            "understat_xg90": [0.8],
            "understat_xa90": [0.4],
        }
    )
    challenger, diag = reprice_projection_surface(
        players,
        projections,
        rates,
        {"apex_model": 1.0},
        0.15,
        xg_weight=0.5,
        xa_weight=0.3,
    )
    rows = challenger.set_index("player_id")
    assert rows.loc[1, "challenger_model_xg90"] == 0.6
    assert rows.loc[1, "challenger_model_xa90"] == 0.26
    assert rows.loc[1, "xp"] > 5.0
    assert rows.loc[2, "xp"] == 4.0
    assert diag["matched_players"] == 1
    assert diag["zero_base_unrepriced_players"] == 0
