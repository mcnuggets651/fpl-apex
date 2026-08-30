from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from apex.domain.models import (
    CoverageStatus,
    OfficialSnapshot,
    ProjectionRow,
    ProjectionSurface,
)


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fixture_ids(
    official: OfficialSnapshot,
    element_id: int,
    gameweek: int,
) -> tuple[int, ...]:
    player = official.player_map()[int(element_id)]
    return tuple(
        sorted(
            fixture.fixture_id
            for fixture in official.fixtures
            if fixture.gameweek == int(gameweek)
            and player.team_id in {fixture.home_team_id, fixture.away_team_id}
        )
    )


def load_pitchside(
    path: str | Path,
    *,
    official: OfficialSnapshot,
    target_gameweek: int,
    scoring_rules_version: str,
    max_horizon: int = 8,
) -> ProjectionSurface:
    """Load a sealed public PITCHSIDE bundle as a non-serving shadow surface.

    PITCHSIDE's public ``meta.next_gw`` is descriptive and can remain on the
    gameweek currently being played after its deadline has locked. Apex does
    not use that field as an alignment gate. Instead, the exact Apex target GW
    must exist in ``xp.gws`` and the PITCHSIDE bundle must have been published
    before that target GW's Official FPL deadline. This preserves prospective
    evaluation without discarding valid future-GW forecasts.
    """

    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if int(payload.get("schema_version", 0)) != 1:
        raise ValueError("PITCHSIDE bundle schema_version must be 1")
    if str(payload.get("provider_id") or "") != "pitchside":
        raise ValueError("PITCHSIDE bundle provider_id mismatch")
    if str(payload.get("expected_official_hash") or "") != official.source_hash:
        raise ValueError("PITCHSIDE acquisition Official FPL hash mismatch")
    if int(payload.get("target_gameweek", -1)) != int(target_gameweek):
        raise ValueError("PITCHSIDE acquisition target gameweek mismatch")

    meta = payload.get("meta") or {}
    xp = payload.get("xp") or {}
    gws = [int(value) for value in xp.get("gws") or []]
    forecasts = xp.get("players") or {}
    if int(target_gameweek) not in gws:
        raise ValueError(
            f"PITCHSIDE has no forecast for target GW{int(target_gameweek)}"
        )

    generated_at = str(meta.get("generated_utc") or "")
    if not generated_at:
        raise ValueError("PITCHSIDE meta.generated_utc is missing")
    deadline_raw = official.deadlines.get(int(target_gameweek))
    if not deadline_raw:
        raise ValueError(f"Official FPL deadline missing for GW{target_gameweek}")
    if _parse_utc(generated_at) >= _parse_utc(deadline_raw):
        raise ValueError(
            "PITCHSIDE forecast was published at or after the target GW deadline"
        )

    source_season = int(meta.get("season", -1))
    official_start_year = int(str(official.season).split("-", 1)[0])
    if source_season != official_start_year:
        raise ValueError(
            f"PITCHSIDE season mismatch: {source_season} != {official_start_year}"
        )

    code_to_element: dict[int, int] = {}
    for player in official.players:
        if player.fpl_code is None:
            continue
        code = int(player.fpl_code)
        if code in code_to_element:
            raise ValueError(f"duplicate Official FPL player code {code}")
        code_to_element[code] = int(player.element_id)

    selected_gws = [
        gw
        for gw in gws
        if int(target_gameweek) <= gw < int(target_gameweek) + int(max_horizon)
    ]
    if not selected_gws:
        raise ValueError("PITCHSIDE exposes no gameweeks in the requested horizon")
    gw_index = {gw: gws.index(gw) for gw in selected_gws}

    rows: list[ProjectionRow] = []
    official_map = official.player_map()
    for raw_code, values in forecasts.items():
        code = int(raw_code)
        element_id = code_to_element.get(code)
        if element_id is None:
            continue
        if not isinstance(values, list) or len(values) != len(gws):
            raise ValueError(
                f"PITCHSIDE xP vector length mismatch for player code {code}"
            )
        for gameweek in selected_gws:
            raw_xp = values[gw_index[gameweek]]
            status = (
                CoverageStatus.NO_FORECAST
                if raw_xp is None
                else CoverageStatus.FORECAST
            )
            fixture_ids = _fixture_ids(official, element_id, gameweek)
            rows.append(
                ProjectionRow(
                    element_id=element_id,
                    gameweek=gameweek,
                    horizon=gameweek - int(target_gameweek) + 1,
                    expected_points=(None if raw_xp is None else float(raw_xp)),
                    fixture_ids=fixture_ids,
                    n_fixtures=len(fixture_ids),
                    player_status_at_forecast=official_map[element_id].status,
                    coverage_status=status,
                    coverage_reason=(
                        "PITCHSIDE_NO_FORECAST"
                        if status == CoverageStatus.NO_FORECAST
                        else None
                    ),
                    metadata={
                        "pitchside_player_code": code,
                        "pitchside_next_gw": meta.get("next_gw"),
                    },
                )
            )

    if not rows:
        raise ValueError("PITCHSIDE bundle mapped no current Official FPL players")

    bundle_sha = str(payload.get("bundle_sha256") or "")
    if not bundle_sha:
        raise ValueError("PITCHSIDE bundle_sha256 is missing")
    provider_version = str(meta.get("model_version") or bundle_sha)
    base_url = str(payload.get("source_base_url") or "")

    return ProjectionSurface(
        schema_version=1,
        provider_id="pitchside",
        provider_version=provider_version,
        generated_at=generated_at,
        season=official.season,
        source_snapshot=f"pitchside:{bundle_sha}",
        scoring_rules_version=str(scoring_rules_version),
        supported_horizons=tuple(
            sorted({row.horizon for row in rows})
        ),
        runtime_dependencies=((base_url,) if base_url else ()),
        rows=tuple(
            sorted(rows, key=lambda row: (row.horizon, row.element_id))
        ),
    )
