import numpy as np
import pandas as pd

from apex_fpl.models.minute_states import (
    clean_sheet_eligibility_probability,
    expected_appearance_points,
    minute_state_probabilities,
)
from apex_fpl.models.minutes import minutes_profile


def test_minute_states_are_mutually_exclusive_and_expectation_preserving():
    states = minute_state_probabilities(
        [0.70],
        [0.85],
        [0.60],
        [0.25],
    )
    row = states.iloc[0]
    assert np.isclose(float(row.sum()), 1.0)
    assert np.isclose(row["minutes_state_p0"], 0.15)
    assert np.isclose(row["minutes_state_p1_29"], 0.15)
    assert np.isclose(row["minutes_state_p30_59"], 0.10)
    assert np.isclose(row["minutes_state_p60_79"], 0.35)
    assert np.isclose(row["minutes_state_p80_90"], 0.25)
    # Old appearance formula p_app + p60 is exactly preserved in expectation.
    assert np.isclose(expected_appearance_points(states)[0], 1.45)
    assert np.isclose(clean_sheet_eligibility_probability(states)[0], 0.60)


def test_minutes_profile_publishes_state_surface_without_changing_expected_minutes():
    frame = pd.DataFrame(
        [{
            "status": "a",
            "minutes": 2500,
            "starts": 30,
            "starts_per_90": 0.9,
            "previous_start_probability": 0.8,
            "previous_minutes_per_match": 68,
            "current_team_matches": 0,
        }]
    )
    out = minutes_profile(frame)
    cols = [
        "minutes_state_p0",
        "minutes_state_p1_29",
        "minutes_state_p30_59",
        "minutes_state_p60_79",
        "minutes_state_p80_90",
    ]
    assert np.isclose(out.loc[0, cols].sum(), 1.0)
    assert 0.0 <= out.loc[0, "expected_minutes"] <= 90.0
    assert np.isclose(
        clean_sheet_eligibility_probability(out[cols])[0],
        out.loc[0, "minutes_60_plus_probability"],
    )
