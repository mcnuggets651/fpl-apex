from pathlib import Path

from apex.domain.models import OfficialFixture, OfficialPlayer, OfficialSnapshot, Position
from apex.forecast.adapters.airsenal import load_airsenal
from apex.forecast.qualification import qualify_surface
from apex.domain.models import Qualification, ProviderHealth


def snapshot():
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T10:00:00+00:00",
        "snap",
        (
            OfficialPlayer(1, "A", 1, Position.MID, 50, "a", True),
            OfficialPlayer(2, "B", 2, Position.FWD, 60, "a", True),
        ),
        (
            OfficialFixture(10, 2, 1, 2, "2026-08-29T14:00:00Z"),
        ),
        {2: "2026-08-28T17:30:00Z"},
    )


def test_airsenal_csv_maps_absolute_gameweek_to_horizon(tmp_path: Path):
    path = tmp_path / "a.csv"
    path.write_text(
        "player_id,gw,xp,generated_at,source_version\n"
        "1,2,3.5,2026-08-28T10:00:00+00:00,abc\n"
        "2,2,4.0,2026-08-28T10:00:00+00:00,abc\n"
        "1,3,3.0,2026-08-28T10:00:00+00:00,abc\n"
        "2,3,4.5,2026-08-28T10:00:00+00:00,abc\n",
        encoding="utf-8",
    )
    out = load_airsenal(path, official=snapshot(), target_gameweek=2)
    assert out.supported_horizons == (1, 2)
    assert out.provider_version == "abc"
    assert out.rows_for_horizon(1)[0].fixture_ids == (10,)


def test_qualification_requires_complete_requested_horizon(tmp_path: Path):
    path = tmp_path / "a.csv"
    path.write_text(
        "player_id,gw,xp,generated_at,source_version\n"
        "1,2,3.5,2026-08-28T10:00:00+00:00,abc\n",
        encoding="utf-8",
    )
    official = snapshot()
    out = load_airsenal(path, official=official, target_gameweek=2)
    result = qualify_surface(
        out,
        official,
        decision_universe=official.decision_universe(),
        requested_horizons=(1,),
        max_age_hours=24,
    )
    assert result.operational == Qualification.UNQUALIFIED
    assert result.health == ProviderHealth.INCOMPLETE
