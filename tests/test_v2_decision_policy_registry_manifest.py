from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.decision_policy_registry import load_decision_policy_registry
from apex_fpl.core.numeric_policy import DECISION_NUMERIC_POLICY_ID


BASE_ROW = """
  - policy_name: tactical-reference
    policy_version: \"1\"
    season: \"2026-2027\"
    qualification_state: SHADOW
    qualification_artifact_id: null
    first_available_at: \"2026-08-24T00:00:00Z\"
    evaluation_mode: TACTICAL_CURRENT_GAMEWEEK
    objective_policy: MAX_EXPECTED_FPL_POINTS_OVER_TIME
    horizon_gameweeks: 1
    continuation_value_artifact_id: null
    chip_option_value_artifact_id: null
    price_policy_artifact_id: null
    candidate_policy_artifact_id: null
    tie_break_policy: lexicographic-official-id-v1
"""


def _write(path: Path, *, numeric_line: str = "") -> Path:
    path.write_text(
        "schema_version: 1\nseason: \"2026-2027\"\npolicies:\n"
        + BASE_ROW
        + numeric_line
        + "champion_policy_id: null\n",
        encoding="utf-8",
    )
    return path


def test_registry_manifest_cannot_silently_default_missing_numeric_policy(tmp_path: Path) -> None:
    path = _write(tmp_path / "missing-numeric.yaml")
    with pytest.raises(KeyError, match="numeric_policy_id"):
        load_decision_policy_registry(path)


def test_registry_manifest_loads_only_explicit_supported_numeric_policy(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "explicit-numeric.yaml",
        numeric_line=f"    numeric_policy_id: {DECISION_NUMERIC_POLICY_ID}\n",
    )
    registry = load_decision_policy_registry(path)
    assert registry.policies[0].numeric_policy_id == DECISION_NUMERIC_POLICY_ID
