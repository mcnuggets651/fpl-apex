import numpy as np
import pandas as pd

from apex_fpl.models.scenarios import generate_projection_scenarios


def test_low_confidence_player_has_persistent_cross_gw_uncertainty():
    players = pd.DataFrame([{"player_id": 1, "team": 1}, {"player_id": 2, "team": 2}])
    rows = []
    for gw in (1, 2):
        rows += [
            {
                "player_id": 1,
                "gw": gw,
                "opponent": 2,
                "xp": 5.0,
                "apex_xp": 5.0,
                "projection_sd": 1.5,
                "minutes_confidence": 0.35,
                "role_confidence": 0.35,
                "xp_attack": 2.0,
            },
            {
                "player_id": 2,
                "gw": gw,
                "opponent": 1,
                "xp": 5.0,
                "apex_xp": 5.0,
                "projection_sd": 1.5,
                "minutes_confidence": 0.95,
                "role_confidence": 0.95,
                "xp_attack": 2.0,
            },
        ]
    scenarios = generate_projection_scenarios(
        players, pd.DataFrame(rows), [1, 2], n_scenarios=4096, seed=77
    )
    low = scenarios.values[:, 0, :]
    high = scenarios.values[:, 1, :]
    low_corr = np.corrcoef(low[:, 0], low[:, 1])[0, 1]
    high_corr = np.corrcoef(high[:, 0], high[:, 1])[0, 1]
    assert low_corr > high_corr + 0.03
    assert low_corr > 0.05
