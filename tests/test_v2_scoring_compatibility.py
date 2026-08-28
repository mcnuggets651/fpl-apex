from __future__ import annotations

from pathlib import Path

import pytest

from apex.domain.models import (
    OfficialFixture,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    Qualification,
)
from apex.forecast.adapters.dastan import load_dastan
from apex.forecast.adapters.openfpl import load_openfpl
from apex.forecast.qualification import qualify_surface

CURRENT_RULES = "fpl-2026-27-v1"


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T10:00:00+00:00",
        "authority-seal",
        (
            OfficialPlayer(1, "A", 1, Position.MID, 50, "a", True),
            OfficialPlayer(2, "B", 2, Position.FWD, 60, "a", True),
        ),
        (OfficialFixture(10, 2, 1, 2, "2026-08-29T14:00:00Z"),),
        {2: "2026-08-29T10:00:00Z"},
    )


def _write(path: Path, *, scoring_rules_version: str | None) -> None:
    columns = [
        "player_id",
        "gameweek",
        "xp",
        "generated_at",
        "provider_version",
        "source_snapshot",
    ]
    if scoring_rules_version is not None:
        columns.append("scoring_rules_version")
    rows = []
    for player_id, xp in ((1, 3.0), (2, 4.0)):
        values = [
            str(player_id),
            "2",
            str(xp),
            "2026-08-28T10:00:00+00:00",
            "model-sha",
            "authority-seal",
        ]
        if scoring_rules_version is not None:
            values.append(scoring_rules_version)
        rows.append(",".join(values))
    path.write_text(
        ",".join(columns) + "\n" + "\n".join(rows) + "\n",
        encoding="utf-8",
    )


def test_external_challenger_must_declare_scoring_rules(tmp_path: Path):
    path = tmp_path / "dastan.csv"
    _write(path, scoring_rules_version=None)
    with pytest.raises(ValueError, match="missing scoring_rules_version provenance"):
        load_dastan(path, official=_official(), target_gameweek=2)


def test_legacy_openfpl_rules_cannot_qualify_for_current_apex(tmp_path: Path):
    path = tmp_path / "openfpl.csv"
    _write(path, scoring_rules_version="openfpl-2024-25-rules")
    official = _official()
    surface = load_openfpl(path, official=official, target_gameweek=2)
    result = qualify_surface(
        surface,
        official,
        decision_universe=official.decision_universe(),
        requested_horizons=(1,),
        max_age_hours=24,
        required_scoring_rules_version=CURRENT_RULES,
    )
    assert result.operational == Qualification.UNQUALIFIED
    assert any("scoring rules incompatible" in reason for reason in result.reasons)


def test_current_rules_challenger_can_pass_scoring_gate(tmp_path: Path):
    path = tmp_path / "dastan.csv"
    _write(path, scoring_rules_version=CURRENT_RULES)
    official = _official()
    surface = load_dastan(path, official=official, target_gameweek=2)
    result = qualify_surface(
        surface,
        official,
        decision_universe=official.decision_universe(),
        requested_horizons=(1,),
        max_age_hours=24,
        required_scoring_rules_version=CURRENT_RULES,
    )
    assert result.operational == Qualification.QUALIFIED
