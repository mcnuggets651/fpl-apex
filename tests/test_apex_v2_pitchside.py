from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position
from apex.forecast.adapters.pitchside import load_pitchside
from apex.sources import pitchside as pitchside_source


def _official() -> OfficialSnapshot:
    return OfficialSnapshot(
        schema_version=1,
        season="2026-2027",
        acquired_at="2026-08-30T10:00:00+00:00",
        source_hash="official-hash",
        players=(
            OfficialPlayer(1, "One", 10, Position.MID, 75, "a", True, 1001),
            OfficialPlayer(2, "Two", 20, Position.FWD, 80, "a", True, 1002),
        ),
        fixtures=(),
        deadlines={
            2: "2026-08-28T17:30:00+00:00",
            3: "2026-09-04T17:30:00+00:00",
            4: "2026-09-11T17:30:00+00:00",
        },
    )


def _payload(generated_at="2026-08-29T20:04:56Z") -> dict:
    return {
        "schema_version": 1,
        "provider_id": "pitchside",
        "acquired_at": "2026-08-30T10:00:00+00:00",
        "expected_official_hash": "official-hash",
        "target_gameweek": 3,
        "target_deadline": "2026-09-04T17:30:00+00:00",
        "source_base_url": "https://example.test/data",
        "source_file_sha256": {},
        "bundle_sha256": "abc123",
        "meta": {
            "generated_utc": generated_at,
            "model_version": "model-v1",
            "next_gw": 2,
            "season": 2026,
        },
        "xp": {
            "gws": [2, 3, 4],
            "players": {
                "1001": [9.0, 5.0, 4.0],
                "1002": [8.0, 6.0, 3.0],
            },
        },
        "players": [],
    }


def test_pitchside_uses_exact_target_gw_not_descriptive_next_gw(tmp_path):
    path = tmp_path / "pitchside.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    surface = load_pitchside(
        path,
        official=_official(),
        target_gameweek=3,
        scoring_rules_version="fpl-2026-27-v1",
        max_horizon=2,
    )

    assert surface.provider_id == "pitchside"
    assert surface.supported_horizons == (1, 2)
    h1 = {row.element_id: row.expected_points for row in surface.rows_for_horizon(1)}
    assert h1 == {1: 5.0, 2: 6.0}
    assert all(row.metadata["pitchside_next_gw"] == 2 for row in surface.rows)


def test_pitchside_rejects_target_gw_forecast_published_after_deadline(tmp_path):
    path = tmp_path / "pitchside.json"
    path.write_text(
        json.dumps(_payload(generated_at="2026-09-04T18:00:00Z")),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="at or after the target GW deadline"):
        load_pitchside(
            path,
            official=_official(),
            target_gameweek=3,
            scoring_rules_version="fpl-2026-27-v1",
        )


class _Response:
    def __init__(self, payload):
        self._payload = payload
        self.content = json.dumps(payload, sort_keys=True).encode("utf-8")

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _Http:
    def __init__(self, mapping):
        self.mapping = mapping

    def get(self, url, timeout=30):
        del timeout
        return _Response(self.mapping[url.rsplit("/", 1)[-1]])


def test_pitchside_acquisition_targets_next_actionable_deadline(monkeypatch, tmp_path):
    official = _official()
    monkeypatch.setattr(
        pitchside_source,
        "fetch_official_snapshot",
        lambda season: (official, {"season": season}),
    )
    payload = _payload()
    http = _Http(
        {
            "meta.json": payload["meta"],
            "xp.json": payload["xp"],
            "players.json": payload["players"],
        }
    )
    output = tmp_path / "pitchside.json"

    report = pitchside_source.acquire_pitchside_shadow(
        output,
        season="2026-2027",
        expected_official_hash="official-hash",
        source_base_url="https://example.test/data",
        http=http,
        now=datetime(2026, 8, 30, 10, 0, tzinfo=timezone.utc),
    )

    sealed = json.loads(output.read_text(encoding="utf-8"))
    assert report["source_next_gw"] == 2
    assert report["target_gameweek"] == 3
    assert sealed["target_gameweek"] == 3
    assert 3 in sealed["xp"]["gws"]
