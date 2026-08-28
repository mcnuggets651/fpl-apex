from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from apex.domain.models import (
    CoverageStatus,
    OfficialSnapshot,
    ProjectionRow,
    ProjectionSurface,
)


def _fixture_ids(official: OfficialSnapshot, element_id: int, gameweek: int) -> tuple[int, ...]:
    player = official.player_map()[int(element_id)]
    return tuple(
        sorted(
            f.fixture_id
            for f in official.fixtures
            if f.gameweek == int(gameweek)
            and player.team_id in {f.home_team_id, f.away_team_id}
        )
    )


def _first(frame: pd.DataFrame, *names: str, required: bool = False) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    if required:
        raise ValueError(f"missing required provider column; expected one of {names}")
    return None


def load_projection_csv(
    path: str | Path,
    *,
    provider_id: str,
    official: OfficialSnapshot,
    target_gameweek: int,
    provider_version: str | None = None,
    scoring_rules_version: str = "2026-2027",
    runtime_dependencies: tuple[str, ...] = (),
) -> ProjectionSurface:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"{provider_id} projection export is empty")
    id_col = _first(frame, "element_id", "player_id", required=True)
    gw_col = _first(frame, "gameweek", "gw", required=True)
    xp_col = _first(frame, "expected_points", "xp", "xpts", "predicted_points", required=True)
    generated_col = _first(frame, "generated_at", "forecast_timestamp")
    version_col = _first(frame, "provider_version", "source_version", "model_version")
    minutes_col = _first(frame, "expected_minutes", "xmins")
    p_any_col = _first(frame, "p_appearance", "p_any")
    p_start_col = _first(frame, "p_start")
    p60_col = _first(frame, "p_60", "p60")
    coverage_col = _first(frame, "coverage_status")
    reason_col = _first(frame, "coverage_reason")

    if generated_col:
        generated_values = frame[generated_col].dropna().astype(str).unique().tolist()
        if len(generated_values) != 1:
            raise ValueError(f"{provider_id} export must contain one generated_at value")
        generated_at = generated_values[0]
    else:
        generated_at = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    if provider_version is None:
        if version_col:
            versions = frame[version_col].dropna().astype(str).unique().tolist()
            if len(versions) != 1:
                raise ValueError(f"{provider_id} export must contain one provider version")
            provider_version = versions[0]
        else:
            raise ValueError(f"{provider_id} provider_version is required")

    rows: list[ProjectionRow] = []
    for row in frame.itertuples(index=False):
        raw = row._asdict()
        element_id = int(raw[id_col])
        gameweek = int(raw[gw_col])
        if gameweek < int(target_gameweek):
            continue
        horizon = gameweek - int(target_gameweek) + 1
        status_raw = str(raw.get(coverage_col) or "FORECAST") if coverage_col else "FORECAST"
        status = CoverageStatus(status_raw.upper())
        xp_value = raw[xp_col]
        expected_points = None if status == CoverageStatus.NO_FORECAST else float(xp_value)
        fixture_ids = _fixture_ids(official, element_id, gameweek) if element_id in official.player_ids else ()
        official_status = (
            official.player_map()[element_id].status if element_id in official.player_ids else None
        )
        rows.append(
            ProjectionRow(
                element_id=element_id,
                gameweek=gameweek,
                horizon=horizon,
                expected_points=expected_points,
                fixture_ids=fixture_ids,
                n_fixtures=len(fixture_ids),
                player_status_at_forecast=official_status,
                expected_minutes=(float(raw[minutes_col]) if minutes_col and pd.notna(raw[minutes_col]) else None),
                p_appearance=(float(raw[p_any_col]) if p_any_col and pd.notna(raw[p_any_col]) else None),
                p_start=(float(raw[p_start_col]) if p_start_col and pd.notna(raw[p_start_col]) else None),
                p_60=(float(raw[p60_col]) if p60_col and pd.notna(raw[p60_col]) else None),
                coverage_status=status,
                coverage_reason=(str(raw[reason_col]) if reason_col and pd.notna(raw[reason_col]) else None),
            )
        )
    horizons = tuple(sorted({row.horizon for row in rows}))
    return ProjectionSurface(
        schema_version=1,
        provider_id=provider_id,
        provider_version=str(provider_version),
        generated_at=generated_at,
        season=official.season,
        source_snapshot=official.source_hash,
        scoring_rules_version=scoring_rules_version,
        supported_horizons=horizons,
        runtime_dependencies=runtime_dependencies,
        rows=tuple(rows),
    )
