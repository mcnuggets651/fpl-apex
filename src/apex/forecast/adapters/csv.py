from __future__ import annotations

from pathlib import Path

import pandas as pd

from apex.domain.models import (
    CoverageStatus,
    OfficialSnapshot,
    ProjectionRow,
    ProjectionSurface,
)


def _fixture_ids(
    official: OfficialSnapshot, element_id: int, gameweek: int
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


def _first(frame, *names, required=False):
    for name in names:
        if name in frame.columns:
            return name
    if required:
        raise ValueError(f"missing required provider column; expected one of {names}")
    return None


def _single_value(frame, column: str, label: str) -> str:
    values = frame[column].dropna().astype(str).unique().tolist()
    if len(values) != 1:
        raise ValueError(f"{label} must contain exactly one value")
    return values[0]


def load_projection_csv(
    path,
    *,
    provider_id: str,
    official: OfficialSnapshot,
    target_gameweek: int,
    provider_version: str | None = None,
    scoring_rules_version: str | None = None,
    runtime_dependencies: tuple[str, ...] = (),
    require_source_snapshot: bool = False,
    trusted_source_snapshot: str | None = None,
) -> ProjectionSurface:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f"{provider_id} projection export is empty")

    id_col = _first(frame, "element_id", "player_id", required=True)
    gw_col = _first(frame, "gameweek", "gw", required=True)
    xp_col = _first(
        frame,
        "expected_points",
        "xp",
        "xpts",
        "predicted_points",
        required=True,
    )
    generated_col = _first(frame, "generated_at", "forecast_timestamp", required=True)
    version_col = _first(frame, "provider_version", "source_version", "model_version")
    scoring_col = _first(frame, "scoring_rules_version")
    snapshot_col = _first(frame, "source_snapshot", "official_snapshot_hash")
    minutes_col = _first(frame, "expected_minutes", "xmins")
    p_any_col = _first(frame, "p_appearance", "p_any")
    p_start_col = _first(frame, "p_start")
    p60_col = _first(frame, "p_60", "p60")
    coverage_col = _first(frame, "coverage_status")
    reason_col = _first(frame, "coverage_reason")

    generated_at = _single_value(frame, generated_col, f"{provider_id} generated_at")
    if provider_version is None:
        if not version_col:
            raise ValueError(f"{provider_id} provider_version is required")
        provider_version = _single_value(
            frame, version_col, f"{provider_id} provider version"
        )

    if scoring_col:
        declared_scoring = _single_value(
            frame, scoring_col, f"{provider_id} scoring_rules_version"
        )
        if scoring_rules_version and declared_scoring != scoring_rules_version:
            raise ValueError(
                f"{provider_id} scoring rules mismatch: "
                f"{declared_scoring} != {scoring_rules_version}"
            )
        scoring_rules_version = declared_scoring
    elif scoring_rules_version is None:
        raise ValueError(
            f"{provider_id} export missing scoring_rules_version provenance"
        )

    if snapshot_col:
        source_snapshot = _single_value(
            frame, snapshot_col, f"{provider_id} source_snapshot"
        )
    elif trusted_source_snapshot:
        source_snapshot = str(trusted_source_snapshot)
    elif require_source_snapshot:
        raise ValueError(f"{provider_id} export missing source_snapshot provenance")
    else:
        source_snapshot = official.source_hash
    if source_snapshot != official.source_hash:
        raise ValueError(
            f"{provider_id} snapshot mismatch: {source_snapshot} != {official.source_hash}"
        )

    rows = []
    for row in frame.itertuples(index=False):
        raw = row._asdict()
        element_id = int(raw[id_col])
        gameweek = int(raw[gw_col])
        if gameweek < int(target_gameweek):
            continue
        horizon = gameweek - int(target_gameweek) + 1
        status = (
            CoverageStatus(str(raw.get(coverage_col) or "FORECAST").upper())
            if coverage_col
            else CoverageStatus.FORECAST
        )
        expected_points = (
            None if status == CoverageStatus.NO_FORECAST else float(raw[xp_col])
        )
        fixtures = (
            _fixture_ids(official, element_id, gameweek)
            if element_id in official.player_ids
            else ()
        )
        official_status = (
            official.player_map()[element_id].status
            if element_id in official.player_ids
            else None
        )
        rows.append(
            ProjectionRow(
                element_id,
                gameweek,
                horizon,
                expected_points,
                fixtures,
                len(fixtures),
                official_status,
                float(raw[minutes_col])
                if minutes_col and pd.notna(raw[minutes_col])
                else None,
                float(raw[p_any_col])
                if p_any_col and pd.notna(raw[p_any_col])
                else None,
                float(raw[p_start_col])
                if p_start_col and pd.notna(raw[p_start_col])
                else None,
                float(raw[p60_col])
                if p60_col and pd.notna(raw[p60_col])
                else None,
                status,
                str(raw[reason_col])
                if reason_col and pd.notna(raw[reason_col])
                else None,
            )
        )
    return ProjectionSurface(
        1,
        provider_id,
        str(provider_version),
        generated_at,
        official.season,
        source_snapshot,
        str(scoring_rules_version),
        tuple(sorted({row.horizon for row in rows})),
        runtime_dependencies,
        tuple(rows),
    )
