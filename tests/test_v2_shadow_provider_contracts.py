from __future__ import annotations

from pathlib import Path

from apex.domain.models import (
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    ProjectionRow,
    ProjectionSurface,
    ProviderRole,
)
from apex.forecast.contract import validate_projection_surface
from apex.runtime.config import ApexConfig


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T10:00:00+00:00",
        "snap",
        (OfficialPlayer(1, "A", 1, Position.MID, 50, "a", True),),
        (),
        {2: "2026-08-28T17:30:00Z"},
    )


def _surface(row: ProjectionRow) -> ProjectionSurface:
    official = _official()
    return ProjectionSurface(
        1,
        "dastan",
        "pin",
        "2026-08-28T10:00:00+00:00",
        official.season,
        official.source_hash,
        "fpl-2026-27-v1",
        (1,),
        (),
        (row,),
    )


def test_current_challengers_are_structurally_shadow_only():
    config = ApexConfig.load(Path("config/apex_v2.yaml"))
    by_id = {provider.provider_id: provider for provider in config.providers}
    for provider_id in ("dastan", "openfpl"):
        provider = by_id[provider_id]
        assert provider.role == ProviderRole.SHADOW
        assert provider.serve_authorized is False


def test_projection_contract_tolerates_only_floating_probability_noise():
    official = _official()
    tiny_noise = ProjectionRow(
        1,
        2,
        1,
        3.0,
        expected_minutes=0.1,
        p_appearance=0.001,
        p_60=0.00100002,
    )
    assert validate_projection_surface(_surface(tiny_noise), official) == ()

    material = ProjectionRow(
        1,
        2,
        1,
        3.0,
        expected_minutes=60.0,
        p_appearance=0.20,
        p_60=0.30,
    )
    errors = validate_projection_surface(_surface(material), official)
    assert any("p60 exceeds p_appearance" in error for error in errors)


def test_projection_contract_rejects_impossible_probability_and_minutes_ranges():
    official = _official()
    invalid = ProjectionRow(
        1,
        2,
        1,
        3.0,
        expected_minutes=91.0,
        p_appearance=1.2,
        p_start=-0.2,
        p_60=0.8,
    )
    errors = validate_projection_surface(_surface(invalid), official)
    assert any("expected_minutes outside feasible range" in error for error in errors)
    assert any("p_appearance outside [0,1]" in error for error in errors)
    assert any("p_start outside [0,1]" in error for error in errors)
