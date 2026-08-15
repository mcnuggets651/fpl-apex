from __future__ import annotations

import json
from pathlib import Path

from apex_fpl.evaluation.projection_policy_readiness import (
    build_projection_policy_readiness,
)


def test_readiness_blocks_decay_and_behavioral_promotion_without_historical_archives(
    tmp_path: Path,
):
    apex = tmp_path / "apex"
    core = tmp_path / "core"
    payload = build_projection_policy_readiness(apex, core)
    assert payload["fixture_decay"]["candidates"] == [1.0, 0.97, 0.95, 0.9]
    assert payload["fixture_decay"]["incumbent"] == 0.9
    assert payload["fixture_decay"]["promotion_allowed"] is False
    assert payload["fixture_decay"]["result"] == "blocked_missing_predeadline_apex_bundles"
    assert payload["preseason_return_fallback"]["promotion_allowed"] is False
    assert payload["minutes_decomposition"]["promotion_allowed"] is False
    assert payload["bench_appearance_propensity"]["promotion_allowed"] is False
    assert payload["bench_appearance_propensity"]["eligible_for_production_ab"] is False


def test_broad_historical_preseason_readiness_still_requires_both_calibration_seasons(
    tmp_path: Path,
):
    apex = tmp_path / "apex"
    core = tmp_path / "core"
    for season in ("2024-2025", "2025-2026"):
        (core / "data" / season / "By Tournament" / "Friendlies").mkdir(parents=True)
    payload = build_projection_policy_readiness(apex, core)
    assert payload["preseason_return_fallback"]["historical_validation_ready"] is True
    assert payload["minutes_decomposition"]["historical_validation_ready"] is True
    assert payload["preseason_return_fallback"]["promotion_allowed"] is False
    assert payload["minutes_decomposition"]["promotion_allowed"] is False


def test_readiness_recognizes_recovered_git_history_for_broad_model_gate(tmp_path: Path):
    apex = tmp_path / "apex"
    core = tmp_path / "core"
    historical = tmp_path / "historical.json"
    historical.write_text(
        json.dumps(
            {
                "seasons": [
                    {
                        "season": "2025-2026",
                        "feature_ref": "predeadline-sha",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = build_projection_policy_readiness(
        apex,
        core,
        historical_audit_path=historical,
    )
    minutes = payload["minutes_decomposition"]
    assert minutes["historical_friendlies_available"] == {
        "2024-2025": False,
        "2025-2026": True,
    }
    assert minutes["historical_friendlies_sources"]["2025-2026"] == "git_history"
    assert minutes["historical_validation_ready"] is False
    assert minutes["promotion_allowed"] is False
    assert minutes["blockers"] == [
        "missing historical preseason player-match archive for broad model validation: 2024-2025"
    ]


def test_narrow_bench_challenger_can_advance_from_one_robust_recent_season(
    tmp_path: Path,
):
    apex = tmp_path / "apex"
    core = tmp_path / "core"
    bench = tmp_path / "bench.json"
    checks = {
        "minimum_rows": True,
        "minimum_players": True,
        "overall_all_metrics_improve": True,
        "player_clustered_ci_all_negative": True,
        "team_clustered_ci_all_negative": True,
        "leave_one_team_out_all_negative": True,
        "key_cohorts_all_improve": True,
    }
    bench.write_text(
        json.dumps(
            {
                "recent_season_robustness": {
                    "eligible_for_production_ab": True,
                    "checks": checks,
                },
                "blockers": ["production projection/decision A/B has not been run"],
            }
        ),
        encoding="utf-8",
    )

    payload = build_projection_policy_readiness(apex, core, bench_audit_path=bench)
    narrow = payload["bench_appearance_propensity"]
    assert narrow["recent_full_season_can_qualify_if_robust"] is True
    assert narrow["robustness_checks"] == checks
    assert narrow["eligible_for_production_ab"] is True
    assert narrow["production_ab_required_before_promotion"] is True
    assert narrow["promotion_allowed"] is False
