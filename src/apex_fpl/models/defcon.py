from __future__ import annotations

import numpy as np
import pandas as pd


def expected_defensive_contribution_points(position: pd.Series, actions_per90: pd.Series, minutes_share: pd.Series) -> np.ndarray:
    """Approximate 2026/27 DC expected points from the official 10/12-action thresholds.

    Defenders need 10 CBIT; midfielders/forwards need 12 CBIRT. Because we only
    have an average rate here, a logistic probability around the threshold is used
    instead of pretending a deterministic per-match threshold crossing.
    """
    threshold = position.map({"DEF": 10.0, "MID": 12.0, "FWD": 12.0}).fillna(999.0).to_numpy(float)
    actions = pd.to_numeric(actions_per90, errors="coerce").fillna(0).to_numpy(float)
    share = pd.to_numeric(minutes_share, errors="coerce").fillna(0).to_numpy(float)
    expected_actions = actions * share
    z = np.clip((expected_actions - threshold) / 1.8, -12, 12)
    p_threshold = 1.0 / (1.0 + np.exp(-z))
    return 2.0 * p_threshold
