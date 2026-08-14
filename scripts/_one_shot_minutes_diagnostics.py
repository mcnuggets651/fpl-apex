from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected exactly one replacement target, found {count}")
    target.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/apex_fpl/models/minutes.py",
    '''    result = pd.DataFrame({\n        "expected_minutes": expected,\n        "start_probability": start,\n        "appearance_probability": appearance,\n        "minutes_60_plus_probability": p60,\n        "minutes_80_plus_probability": p80,\n        "minutes_confidence": confidence,\n        "preseason_role_weight": preseason_weight,\n        "preseason_effective_games": effective_preseason_games,\n    }, index=df.index)\n''',
    '''    result = pd.DataFrame({\n        "expected_minutes": expected,\n        "start_probability": start,\n        "appearance_probability": appearance,\n        "minutes_60_plus_probability": p60,\n        "minutes_80_plus_probability": p80,\n        "minutes_confidence": confidence,\n        # Decision-grade observability: these fields explain the incumbent model\n        # without changing it. A future decomposed challenger must be validated\n        # before it can replace expected_minutes/start_probability.\n        "historical_start_probability": hist_start_prob,\n        "historical_expected_minutes": historic_expected_minutes,\n        "preseason_start_probability": pre_start_prob,\n        "preseason_average_minutes": pre_avg_minutes,\n        "preseason_signal_minutes": preseason_signal,\n        "historical_signal_minutes": historic_signal,\n        "role_expected_minutes_pre_availability": base_minutes,\n        "role_start_probability_pre_availability": base_start,\n        "availability_probability": availability,\n        "preseason_role_weight": preseason_weight,\n        "preseason_effective_games": effective_preseason_games,\n    }, index=df.index)\n''',
)

replace_once(
    "src/apex_fpl/services/pipeline.py",
    '''        "minutes_confidence",\n        "tactical_role",\n''',
    '''        "minutes_confidence",\n        "historical_start_probability",\n        "historical_expected_minutes",\n        "preseason_start_probability",\n        "preseason_average_minutes",\n        "preseason_signal_minutes",\n        "historical_signal_minutes",\n        "role_expected_minutes_pre_availability",\n        "role_start_probability_pre_availability",\n        "availability_probability",\n        "preseason_role_weight",\n        "preseason_effective_games",\n        "tactical_role",\n''',
)

replace_once(
    "tests/test_minutes.py",
    '''def test_previous_season_prior_prevents_false_default_for_established_player():\n''',
    '''def test_minutes_diagnostics_reconcile_incumbent_expected_minutes_and_start_probability():\n    row = pd.DataFrame(\n        [\n            {\n                "minutes": 0,\n                "starts": 0,\n                "starts_per_90": 0,\n                "previous_start_probability": 0.80,\n                "previous_minutes_per_match": 68.0,\n                "preseason_minutes": 210,\n                "preseason_starts": 3,\n                "preseason_appearances": 3,\n                "status": "a",\n            }\n        ]\n    )\n    out = minutes_profile(row).iloc[0]\n    assert out["expected_minutes"] == pytest.approx(\n        out["role_expected_minutes_pre_availability"]\n        * out["availability_probability"]\n    )\n    assert out["start_probability"] == pytest.approx(\n        out["role_start_probability_pre_availability"]\n        * out["availability_probability"]\n    )\n    assert out["historical_start_probability"] == pytest.approx(0.80)\n    assert out["preseason_start_probability"] == pytest.approx(1.0)\n\n\ndef test_previous_season_prior_prevents_false_default_for_established_player():\n''',
)
