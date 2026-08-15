import pandas as pd

import apex_fpl.evaluation.bench_appearance_shadow as bench_shadow
from apex_fpl.evaluation.bench_appearance_shadow import (
    recent_season_robustness_gate,
    score_bench_appearance_shadow,
)


def test_bench_only_shadow_leaves_start_and_minutes_untouched_and_can_improve_appearance():
    scored = pd.DataFrame(
        [
            {
                "player_id": 1,
                "availability_probability": 1.0,
                "incumbent_start_probability": 0.8,
                "incumbent_appearance_probability": 0.904,
                "incumbent_bench_appearance_probability": 0.52,
                "challenger_role_bench_probability": 0.1,
                "actual_start": 1,
                "actual_appearance": 1,
                "actual_bench_appearance": 0,
            },
            {
                "player_id": 1,
                "availability_probability": 1.0,
                "incumbent_start_probability": 0.8,
                "incumbent_appearance_probability": 0.904,
                "incumbent_bench_appearance_probability": 0.52,
                "challenger_role_bench_probability": 0.1,
                "actual_start": 0,
                "actual_appearance": 0,
                "actual_bench_appearance": 0,
            },
        ]
    )

    result = score_bench_appearance_shadow(scored)
    assert result["start_probability_changed"] is False
    assert result["expected_minutes_changed"] is False
    assert result["bench_only_shadow"]["bench_appearance_brier"] < result["incumbent"][
        "bench_appearance_brier"
    ]


def test_recent_season_robustness_can_qualify_narrow_challenger_for_ab(monkeypatch):
    monkeypatch.setattr(bench_shadow, "MIN_RECENT_ROWS", 8)
    monkeypatch.setattr(bench_shadow, "MIN_RECENT_PLAYERS", 4)

    rows = []
    for player_id in range(1, 5):
        team_code = 10 if player_id <= 2 else 20
        for actual_start in (1, 0):
            rows.append(
                {
                    "player_id": player_id,
                    "team_code": team_code,
                    "availability_probability": 1.0,
                    "incumbent_start_probability": 0.5,
                    "incumbent_appearance_probability": 0.76,
                    "incumbent_bench_appearance_probability": 0.52,
                    "challenger_role_bench_probability": 0.0,
                    "actual_start": actual_start,
                    "actual_appearance": actual_start,
                    "actual_bench_appearance": 0,
                    "established_returning_starter": True,
                    "repeated_preseason_starter": True,
                }
            )

    result = recent_season_robustness_gate(pd.DataFrame(rows))
    assert result["recent_season_is_sufficient_if_robust"] is True
    assert result["eligible_for_production_ab"] is True
    assert result["promotion_allowed"] is False
    assert all(result["checks"].values())
    assert result["production_ab_required_before_promotion"] is True
