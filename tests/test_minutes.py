import pandas as pd

from apex_fpl.models.minutes import expected_minutes


def test_injury_reduces_expected_minutes():
    df = pd.DataFrame([
        {"minutes": 900, "starts": 10, "status": "a", "starts_per_90": 1.0},
        {"minutes": 900, "starts": 10, "status": "i", "starts_per_90": 1.0},
    ])
    m = expected_minutes(df)
    assert m.iloc[0] > 80
    assert m.iloc[1] < 10
