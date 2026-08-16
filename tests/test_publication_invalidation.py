from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from apex_fpl.services.publication import invalidate_published_decision


def test_required_source_refresh_immediately_invalidates_old_decision(tmp_path: Path):
    (tmp_path / "apex_recommendation_latest.json").write_text(
        json.dumps(
            {
                "ready_to_act": True,
                "strategy_stage": "final_validated",
                "blockers": [],
                "recommendation": {"selector": "adaptive_gw1_launch_with_transfer_option_value"},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "apex_answer_context.json").write_text(
        json.dumps(
            {
                "safe_to_act": True,
                "blockers": [],
                "recommendation": {"selector": "adaptive_gw1_launch_with_transfer_option_value"},
                "production_result": {"squad": [1, 2, 3]},
            }
        ),
        encoding="utf-8",
    )

    invalidate_published_decision(
        tmp_path,
        source_name="airsenal",
        reason="validated forecast changed",
        now=datetime(2026, 8, 16, 5, 50, tzinfo=timezone.utc),
    )

    recommendation = json.loads(
        (tmp_path / "apex_recommendation_latest.json").read_text(encoding="utf-8")
    )
    context = json.loads(
        (tmp_path / "apex_answer_context.json").read_text(encoding="utf-8")
    )

    assert recommendation["ready_to_act"] is False
    assert recommendation["recommendation"] is None
    assert recommendation["strategy_stage"] == "invalidated_pending_rebuild"
    assert recommendation["invalidated_source"] == "airsenal"
    assert context["safe_to_act"] is False
    assert context["recommendation"] is None
    assert context["production_result"] is None
    assert context["invalidated_source"] == "airsenal"
    assert any("required source changed after canonical build" in row for row in context["blockers"])
    assert "A fresh Apex Unified rebuild is required" in (
        tmp_path / "apex_recommendation_latest.md"
    ).read_text(encoding="utf-8")
