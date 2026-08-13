from __future__ import annotations

import numpy as np
import pandas as pd


STATE_COLUMNS = (
    "minutes_state_p0",
    "minutes_state_p1_29",
    "minutes_state_p30_59",
    "minutes_state_p60_79",
    "minutes_state_p80_90",
)


def minute_state_probabilities(
    start_probability,
    appearance_probability,
    minutes_60_plus_probability,
    minutes_80_plus_probability,
) -> pd.DataFrame:
    """Decompose role uncertainty into mutually exclusive FPL minute states.

    The state model is deliberately expectation-preserving. It does not invent a
    second minutes forecast; it exposes the probability mass already implied by
    Apex's coherent hierarchy ``appearance >= start >= p60 >= p80``:

    - 0 minutes: no appearance;
    - 1-29: substitute/cameo appearance beyond start probability;
    - 30-59: starts/long appearances that miss the 60-minute threshold;
    - 60-79: reaches the FPL 60-minute threshold but not 80;
    - 80-90: high-minutes state.

    This makes appearance points, clean-sheet eligibility, autosub risk and future
    scenario calibration auditable without treating probability of 90 minutes as a
    selection objective.
    """
    start = np.clip(np.asarray(start_probability, dtype=float), 0.0, 1.0)
    app = np.clip(np.asarray(appearance_probability, dtype=float), 0.0, 1.0)
    p60 = np.clip(np.asarray(minutes_60_plus_probability, dtype=float), 0.0, 1.0)
    p80 = np.clip(np.asarray(minutes_80_plus_probability, dtype=float), 0.0, 1.0)

    # Defensively restore the monotone probability hierarchy if a caller provides
    # malformed external overrides.
    start = np.minimum(start, app)
    p60 = np.minimum(p60, start)
    p80 = np.minimum(p80, p60)

    states = np.column_stack(
        [
            1.0 - app,
            app - start,
            start - p60,
            p60 - p80,
            p80,
        ]
    )
    states = np.clip(states, 0.0, 1.0)
    total = states.sum(axis=1)
    states = np.divide(
        states,
        total[:, None],
        out=np.zeros_like(states),
        where=total[:, None] > 0,
    )
    return pd.DataFrame(states, columns=STATE_COLUMNS)


def expected_appearance_points(states: pd.DataFrame) -> np.ndarray:
    """Expected FPL appearance points implied by the minute-state surface."""
    return (
        states["minutes_state_p1_29"].to_numpy(float)
        + states["minutes_state_p30_59"].to_numpy(float)
        + 2.0 * states["minutes_state_p60_79"].to_numpy(float)
        + 2.0 * states["minutes_state_p80_90"].to_numpy(float)
    )


def clean_sheet_eligibility_probability(states: pd.DataFrame) -> np.ndarray:
    """Probability of reaching the 60-minute clean-sheet threshold."""
    return (
        states["minutes_state_p60_79"].to_numpy(float)
        + states["minutes_state_p80_90"].to_numpy(float)
    )
