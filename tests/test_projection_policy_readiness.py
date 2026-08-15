from __future__ import annotations

from pathlib import Path

from apex_fpl.evaluation.projection_policy_readiness import (
    build_projection_policy_readiness,
)


def test_readiness_blocks_decay_and_behavioral_promotion_without_historical_archives(tmp_path: Path):
    apex = tmp_path / "apex"
    core = tmp_path / "core"
    payload = build_projection_policy_readiness(apex, core)
    assert payload["fixture_decay"]["candidates"] == [1.0, 0.97, 0.95, 0.9]
    assert payload["fixture_decay"]["incumbent"] == 0.9
    assert payload["fixture_decay"]["promotion_allowed"] is False
    assert payload["fixture_decay"]["result"] == "blocked_missing_predeadline_apex_bundles"
    assert payload["preseason_return_fallback"]["promotion_allowed"] is False
    assert payload["minutes_decomposition"]["promotion_allowed"] is False


def test_historical_preseason_readiness_requires_both_calibration_seasons(tmp_path: Path):
    apex = tmp_path / "apex"
    core = tmp_path / "core"
    for season in ("2024-2025", "2025-2026"):
        (core / "data" / season / "By Tournament" / "Friendlies").mkdir(parents=True)
    payload = build_projection_policy_readiness(apex, core)
    assert payload["preseason_return_fallback"]["historical_validation_ready"] is True
    assert payload["minutes_decomposition"]["historical_validation_ready"] is True
    # Historical readiness alone never auto-promotes a behavioural challenger.
    assert payload["preseason_return_fallback"]["promotion_allowed"] is False
    assert payload["minutes_decomposition"]["promotion_allowed"] is False
