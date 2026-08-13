import pandas as pd

from apex_fpl.models.projection import _evidence_qualified_attack_rates


def test_zero_evidence_preserves_raw_rates():
    players = pd.DataFrame([
        {
            "player_id": 1,
            "team": 1,
            "position": "FWD",
            "price": 5.0,
            "minutes": 0.0,
            "previous_minutes": 0.0,
            "expected_goals_per_90": 0.10,
            "expected_assists_per_90": 0.05,
        },
        {
            "player_id": 2,
            "team": 2,
            "position": "FWD",
            "price": 6.0,
            "minutes": 900.0,
            "previous_minutes": 900.0,
            "expected_goals_per_90": 0.60,
            "previous_expected_goals_per_90": 0.60,
            "expected_assists_per_90": 0.20,
            "previous_expected_assists_per_90": 0.20,
        },
    ])
    out = _evidence_qualified_attack_rates(players)
    row = out.loc[out.player_id.eq(1)].iloc[0]
    assert row["expected_goals_per_90"] == 0.10
    assert row["expected_assists_per_90"] == 0.05
    assert not row["xg90_shrinkage_applied"]
    assert not row["xa90_shrinkage_applied"]


def test_low_sample_extreme_rate_shrinks():
    rows = []
    for pid in range(1, 8):
        rows.append(
            {
                "player_id": pid,
                "team": pid,
                "position": "MID",
                "price": 6.0,
                "minutes": 900.0,
                "previous_minutes": 900.0,
                "expected_goals_per_90": 0.20,
                "previous_expected_goals_per_90": 0.20,
                "expected_assists_per_90": 0.15,
                "previous_expected_assists_per_90": 0.15,
            }
        )
    rows.append(
        {
            "player_id": 99,
            "team": 8,
            "position": "MID",
            "price": 6.0,
            "minutes": 90.0,
            "previous_minutes": 0.0,
            "expected_goals_per_90": 1.20,
            "expected_assists_per_90": 0.60,
        }
    )
    out = _evidence_qualified_attack_rates(pd.DataFrame(rows))
    low = out.loc[out.player_id.eq(99)].iloc[0]
    established = out.loc[out.player_id.eq(1)].iloc[0]
    assert low["xg90_shrinkage_applied"]
    assert low["expected_goals_per_90"] < 1.20
    assert low["expected_assists_per_90"] < 0.60
    assert abs(established["expected_goals_per_90"] - 0.20) < 0.01
