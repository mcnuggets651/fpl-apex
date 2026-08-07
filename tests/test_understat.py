from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex_fpl.data.understat import (
    UNDERSTAT_API_URL,
    UnderstatDataError,
    _normalise_matches,
    decode_league_payload,
    fetch_understat_season,
    season_start_year,
)


def _payload() -> dict:
    return {
        "dates": [
            {
                "id": "1",
                "isResult": True,
                "h": {"id": "1", "title": "Man Utd"},
                "a": {"id": "2", "title": "Wolves"},
                "goals": {"h": "2", "a": "1"},
                "xG": {"h": "1.7", "a": "0.8"},
                "datetime": "2025-08-10 15:00:00",
            }
        ],
        "teams": {
            "1": {"id": "1", "title": "Man Utd", "history": []},
            "2": {"id": "2", "title": "Wolves", "history": []},
        },
    }


def test_understat_season_formats_and_payload_validation():
    assert season_start_year("2025-26") == 2025
    assert decode_league_payload(json.dumps(_payload()))["dates"][0]["id"] == "1"
    with pytest.raises(UnderstatDataError, match="valid JSON"):
        decode_league_payload("<html></html>")


def test_understat_normaliser_uses_canonical_team_names():
    frame = _normalise_matches(_payload(), 2025)
    assert frame.loc[0, "team_home"] == "Manchester United"
    assert frame.loc[0, "team_away"] == "Wolverhampton Wanderers"
    assert frame.loc[0, "xg_home"] == pytest.approx(1.7)


def test_understat_fetch_validates_then_reuses_atomic_cache(tmp_path: Path):
    calls: list[tuple[str, int]] = []

    def fetcher(url: str, timeout: int) -> str:
        calls.append((url, timeout))
        return json.dumps(_payload())

    first = fetch_understat_season(2025, cache_dir=tmp_path, fetcher=fetcher)
    second = fetch_understat_season(
        "2025-26",
        cache_dir=tmp_path,
        fetcher=lambda *_: pytest.fail("validated cache was not used"),
    )
    assert first == second
    assert calls == [(UNDERSTAT_API_URL.format(season=2025), 20)]
    assert not list(tmp_path.glob("*.tmp"))


def test_understat_fetch_exposes_root_failure(tmp_path: Path):
    def broken(*_):
        raise TimeoutError("source timed out")

    with pytest.raises(UnderstatDataError, match="TimeoutError: source timed out"):
        fetch_understat_season(
            2025,
            cache_dir=tmp_path,
            attempts=1,
            fetcher=broken,
        )
