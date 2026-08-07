from __future__ import annotations

import pandas as pd


# Prospective 2026/27 evidence floors. These are deliberately shared by the
# optimisers and the publication gate: an ineligible captain must never be
# allowed to win a solve and then be rejected only after the fact.
MIN_CAPTAIN_EXPECTED_MINUTES = 60.0
MIN_CAPTAIN_START_PROBABILITY = 0.50
MIN_CAPTAIN_APPEARANCE_PROBABILITY = 0.75
MIN_CAPTAIN_PROJECTION_CONFIDENCE = 0.40


def captain_eligible_ids(players: pd.DataFrame) -> set[int]:
    """Return players with complete evidence above every captaincy floor."""
    required = {
        "player_id",
        "expected_minutes",
        "start_probability",
        "appearance_probability",
        "projection_confidence",
    }
    if not required.issubset(players.columns):
        return set()

    d = players.drop_duplicates("player_id").copy()
    numeric = d[list(required)].apply(pd.to_numeric, errors="coerce")
    eligible = (
        numeric["player_id"].notna()
        & numeric["expected_minutes"].ge(MIN_CAPTAIN_EXPECTED_MINUTES)
        & numeric["start_probability"].ge(MIN_CAPTAIN_START_PROBABILITY)
        & numeric["appearance_probability"].ge(
            MIN_CAPTAIN_APPEARANCE_PROBABILITY
        )
        & numeric["projection_confidence"].ge(
            MIN_CAPTAIN_PROJECTION_CONFIDENCE
        )
    )
    return set(numeric.loc[eligible, "player_id"].astype(int))
