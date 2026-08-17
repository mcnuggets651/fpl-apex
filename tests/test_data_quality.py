from __future__ import annotations

import pandas as pd

from apex_fpl.data.official import OfficialSnapshot
from apex_fpl.services.data_quality import (
    assess_data_quality,
    official_strength_is_usable,
)


def _official(strength: float = 1000.0) -> OfficialSnapshot:
    teams = pd.DataFrame(
        [
            {
                "id": 1,
                "name": "A",
                "strength_attack_home": strength,
                "strength_defence_home": strength,
                "strength_attack_away": strength,
                "strength_defence_away": strength,
            },
            {
                "id": 2,
                "name": "B",
                "strength_attack_home": strength + (10 if strength else 0),
                "strength_defence_home": strength + (20 if strength else 0),
                "strength_attack_away": strength + (30 if strength else 0),
                "strength_defence_away": strength + (40 if strength else 0),
            },
        ]
    )
    players = pd.DataFrame(
        [
            {"player_id": 1, "position": "MID", "price": 7.0},
            {"player_id": 2, "position": "DEF", "price": 5.0},
        ]
    )
    fixtures = pd.DataFrame([{"event": 1, "team_h": 1, "team_a": 2}])
    return OfficialSnapshot(players, teams, fixtures, pd.DataFrame(), {})


def _official_many(count: int = 101) -> OfficialSnapshot:
    base = _official(1000.0)
    players = pd.DataFrame(
        [
            {"player_id": player_id, "position": "MID", "price": 5.0}
            for player_id in range(1, count + 1)
        ]
    )
    return OfficialSnapshot(players, base.teams, base.fixtures, pd.DataFrame(), {})


def _fixture_surface() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "gw": 1,
                "team": 1,
                "opponent": 2,
                "expected_team_goals": 1.5,
                "clean_sheet_prob": 0.3,
            },
            {
                "gw": 1,
                "team": 2,
                "opponent": 1,
                "expected_team_goals": 1.1,
                "clean_sheet_prob": 0.2,
            },
        ]
    )


def _projections(player_ids: list[int] | None = None) -> pd.DataFrame:
    ids = player_ids or [1, 2]
    return pd.DataFrame(
        [
            {
                "player_id": player_id,
                "gw": 1,
                "xp": 3.0,
                "projection_confidence": 0.8,
            }
            for player_id in ids
        ]
    )


def test_all_zero_official_strength_is_not_accepted_as_real_evidence():
    ok, detail = official_strength_is_usable(_official(0.0).teams)
    assert not ok
    assert "zero/non-positive" in detail


def test_invalid_official_strength_requires_a_validated_fallback():
    official = _official(0.0)
    quality = assess_data_quality(
        official,
        pd.DataFrame({"player_id": [1, 2]}),
        pd.DataFrame(),
        _fixture_surface(),
        _projections(),
        [1],
        fixture_fallback_ok=False,
    )
    assert not quality.ready
    assert any("official_team_strength" in blocker for blocker in quality.blockers)


def test_invalid_official_strength_is_disclosed_when_fallback_is_complete():
    official = _official(0.0)
    quality = assess_data_quality(
        official,
        pd.DataFrame({"player_id": [1, 2]}),
        pd.DataFrame(),
        _fixture_surface(),
        _projections(),
        [1],
        fixture_fallback_ok=True,
    )
    assert quality.ready
    strength = next(check for check in quality.checks if check.name == "official_team_strength")
    assert strength.status == "fallback"
    assert quality.warnings


def test_required_fpl_core_player_id_coverage_is_100_percent():
    official = _official(1000.0)
    quality = assess_data_quality(
        official,
        pd.DataFrame({"player_id": [1]}),
        pd.DataFrame(),
        _fixture_surface(),
        _projections(),
        [1],
        fixture_fallback_ok=True,
    )

    assert quality.ready is False
    core = next(check for check in quality.checks if check.name == "fpl_core_playerstats")
    assert core.minimum_coverage == 1.0
    assert core.coverage == 0.5
    assert core.status == "fail"


def test_small_append_only_core_registration_lag_uses_explicit_fallback():
    official = _official_many(101)
    core = pd.DataFrame({"player_id": range(1, 101)})
    quality = assess_data_quality(
        official,
        core,
        pd.DataFrame(),
        _fixture_surface(),
        _projections(list(range(1, 102))),
        [1],
        fixture_fallback_ok=True,
    )

    assert quality.ready is True
    check = next(row for row in quality.checks if row.name == "fpl_core_playerstats")
    assert check.status == "fallback"
    assert check.minimum_coverage == 1.0
    assert check.coverage >= 0.99
    assert "missing_ids=[101]" in check.detail
    assert "not fabricated" in check.detail
    assert any("registration lag" in warning for warning in quality.warnings)


def test_internal_core_hole_never_qualifies_as_registration_lag():
    official = _official_many(101)
    # Same 100/101 coverage, but the missing player is inside Core's established ID
    # universe rather than a newly appended Official registration.
    core = pd.DataFrame({"player_id": [*range(1, 100), 101]})
    quality = assess_data_quality(
        official,
        core,
        pd.DataFrame(),
        _fixture_surface(),
        _projections(list(range(1, 102))),
        [1],
        fixture_fallback_ok=True,
    )

    assert quality.ready is False
    check = next(row for row in quality.checks if row.name == "fpl_core_playerstats")
    assert check.status == "fail"
    assert "not an append-only trailing registration block" in check.detail


def test_registration_lag_requires_complete_canonical_projection_surface():
    official = _official_many(101)
    core = pd.DataFrame({"player_id": range(1, 101)})
    quality = assess_data_quality(
        official,
        core,
        pd.DataFrame(),
        _fixture_surface(),
        _projections(list(range(1, 101))),
        [1],
        fixture_fallback_ok=True,
    )

    assert quality.ready is False
    check = next(row for row in quality.checks if row.name == "fpl_core_playerstats")
    assert check.status == "fail"
    assert "lack complete canonical projections" in check.detail
    assert any("player_projection_surface" in blocker for blocker in quality.blockers)
