import pandas as pd

from apex_fpl.evaluation.bench_appearance_shadow import score_bench_appearance_shadow


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
