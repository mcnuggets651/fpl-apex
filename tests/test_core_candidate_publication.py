from pathlib import Path

import pandas as pd
import pytest

from scripts.validate_core_candidate import validate_frames


def _official() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": 1, "web_name": "One", "team": 1, "position": "MID"},
            {"player_id": 2, "web_name": "Two", "team": 2, "position": "FWD"},
        ]
    )


def _core() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": 1, "gw": 0, "minutes": 0},
            {"player_id": 2, "gw": 0, "minutes": 0},
        ]
    )


def _previous() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": 1, "previous_minutes": 2000},
            {"player_id": 2, "previous_minutes": 1500},
        ]
    )


def test_candidate_requires_complete_official_player_coverage() -> None:
    core = _core().query("player_id == 1").copy()
    with pytest.raises(ValueError, match="lacks current Official FPL player coverage"):
        validate_frames(_official(), core, _previous())


def test_candidate_reuses_longitudinal_reconciliation_fail_closed_semantics() -> None:
    core = pd.concat(
        [_core(), pd.DataFrame([{"player_id": 1, "gw": 0, "minutes": 10}])],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="ambiguous duplicate player/GW snapshots"):
        validate_frames(_official(), core, _previous())


def test_candidate_requires_complete_current_to_previous_bridge() -> None:
    previous = _previous().query("player_id == 1").copy()
    with pytest.raises(ValueError, match="cannot bridge every current Official FPL player ID"):
        validate_frames(_official(), _core(), previous)


def test_valid_candidate_passes_without_mutating_canonical_identity() -> None:
    summary = validate_frames(_official(), _core(), _previous())
    assert summary["official_player_coverage"] == 1.0
    assert summary["previous_bridge_player_coverage"] == 1.0
    assert summary["previous_minutes_coverage"] == 1.0


def test_refresh_workflow_validates_before_writing_pin() -> None:
    workflow = Path(".github/workflows/refresh-core-pin.yml").read_text(encoding="utf-8")
    validate_at = workflow.index("Validate candidate FPL Core semantics before publication")
    publish_at = workflow.index("Update immutable data pin after validation")
    commit_at = workflow.index("Commit validated FPL Core revision")
    assert validate_at < publish_at < commit_at
    assert "scripts/validate_core_candidate.py" in workflow
