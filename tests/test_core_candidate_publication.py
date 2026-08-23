from pathlib import Path

import pandas as pd
import pytest

from apex_fpl.services.core_candidate import validate_core_candidate_frames


def _official(count: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": player_id,
                "web_name": f"Player {player_id}",
                "team": (player_id % 20) + 1,
                "position": "MID" if player_id % 2 else "FWD",
            }
            for player_id in range(1, count + 1)
        ]
    )


def _core(count: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": player_id, "gw": 0, "minutes": 0}
            for player_id in range(1, count + 1)
        ]
    )


def _previous(count: int = 2) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": player_id, "previous_minutes": 1500}
            for player_id in range(1, count + 1)
        ]
    )


def test_candidate_rejects_large_or_non_trailing_official_player_gap() -> None:
    official = _official(101)
    core = _core(100).query("player_id != 50").copy()
    previous = _previous(100).query("player_id != 50").copy()
    with pytest.raises(ValueError, match="outside the bounded trailing registration-lag policy"):
        validate_core_candidate_frames(official, core, previous)


def test_candidate_allows_one_bounded_trailing_registration_lag() -> None:
    official = _official(101)
    core = _core(100)
    previous = _previous(100)
    summary = validate_core_candidate_frames(official, core, previous)
    assert summary["bounded_registration_lag"] is True
    assert summary["bounded_registration_lag_missing_ids"] == [101]
    assert summary["official_player_coverage"] == pytest.approx(100 / 101)
    assert summary["previous_bridge_player_coverage"] == pytest.approx(100 / 101)


def test_candidate_rejects_missing_previous_bridge_for_core_covered_player() -> None:
    official = _official(101)
    core = _core(100)
    previous = _previous(100).query("player_id != 50").copy()
    with pytest.raises(ValueError, match="already covered by Core"):
        validate_core_candidate_frames(official, core, previous)


def test_candidate_reuses_longitudinal_reconciliation_fail_closed_semantics() -> None:
    core = pd.concat(
        [_core(), pd.DataFrame([{"player_id": 1, "gw": 0, "minutes": 10}])],
        ignore_index=True,
    )
    with pytest.raises(ValueError, match="ambiguous duplicate player/GW snapshots"):
        validate_core_candidate_frames(_official(), core, _previous())


def test_valid_candidate_passes_without_mutating_canonical_identity() -> None:
    summary = validate_core_candidate_frames(_official(), _core(), _previous())
    assert summary["official_player_coverage"] == 1.0
    assert summary["previous_bridge_player_coverage"] == 1.0
    assert summary["previous_minutes_coverage"] == 1.0
    assert summary["bounded_registration_lag"] is False


def test_refresh_workflow_validates_before_materialising_reviewed_pin_proposal() -> None:
    workflow = Path(".github/workflows/refresh-core-pin.yml").read_text(encoding="utf-8")
    validate_at = workflow.index("Validate candidate FPL Core semantics")
    propose_at = workflow.index("Materialize proposed immutable data pin")
    verify_at = workflow.index("Verify proposed pinned source contract")
    upload_at = workflow.index("Upload proposed pin evidence")
    assert validate_at < propose_at < verify_at < upload_at
    assert "scripts/validate_core_candidate.py" in workflow
    assert "contents: write" not in workflow
    assert "git push origin HEAD:main" not in workflow
    assert "reviewed dependency source change required" in workflow
