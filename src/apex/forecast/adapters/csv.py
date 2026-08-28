from __future__ import annotations
from pathlib import Path
import pandas as pd
from apex.domain.models import CoverageStatus, OfficialSnapshot, ProjectionRow, ProjectionSurface

def _fixture_ids(official: OfficialSnapshot, element_id: int, gameweek: int) -> tuple[int, ...]:
    p = official.player_map()[int(element_id)]
    return tuple(sorted((f.fixture_id for f in official.fixtures if f.gameweek == int(gameweek) and p.team_id in {f.home_team_id, f.away_team_id})))

def _first(frame, *names, required=False):
    for n in names:
        if n in frame.columns:
            return n
    if required:
        raise ValueError(f'missing required provider column; expected one of {names}')
    return None

def load_projection_csv(path, *, provider_id: str, official: OfficialSnapshot, target_gameweek: int, provider_version: str | None=None, scoring_rules_version='2026-2027', runtime_dependencies: tuple[str, ...]=(), require_source_snapshot: bool=False, trusted_source_snapshot: str | None=None) -> ProjectionSurface:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    frame = pd.read_csv(path)
    if frame.empty:
        raise ValueError(f'{provider_id} projection export is empty')
    id_col = _first(frame, 'element_id', 'player_id', required=True)
    gw_col = _first(frame, 'gameweek', 'gw', required=True)
    xp_col = _first(frame, 'expected_points', 'xp', 'xpts', 'predicted_points', required=True)
    generated_col = _first(frame, 'generated_at', 'forecast_timestamp', required=True)
    version_col = _first(frame, 'provider_version', 'source_version', 'model_version')
    snapshot_col = _first(frame, 'source_snapshot', 'official_snapshot_hash')
    minutes_col = _first(frame, 'expected_minutes', 'xmins')
    p_any_col = _first(frame, 'p_appearance', 'p_any')
    p_start_col = _first(frame, 'p_start')
    p60_col = _first(frame, 'p_60', 'p60')
    coverage_col = _first(frame, 'coverage_status')
    reason_col = _first(frame, 'coverage_reason')
    generated = frame[generated_col].dropna().astype(str).unique().tolist()
    if len(generated) != 1:
        raise ValueError(f'{provider_id} export must contain one generated_at value')
    generated_at = generated[0]
    if provider_version is None:
        if not version_col:
            raise ValueError(f'{provider_id} provider_version is required')
        versions = frame[version_col].dropna().astype(str).unique().tolist()
        if len(versions) != 1:
            raise ValueError(f'{provider_id} export must contain one provider version')
        provider_version = versions[0]
    if snapshot_col:
        snapshots = frame[snapshot_col].dropna().astype(str).unique().tolist()
        if len(snapshots) != 1:
            raise ValueError(f'{provider_id} export must contain one source_snapshot value')
        source_snapshot = snapshots[0]
    elif trusted_source_snapshot:
        source_snapshot = str(trusted_source_snapshot)
    elif require_source_snapshot:
        raise ValueError(f'{provider_id} export missing source_snapshot provenance')
    else:
        source_snapshot = official.source_hash
    if source_snapshot != official.source_hash:
        raise ValueError(f'{provider_id} snapshot mismatch: {source_snapshot} != {official.source_hash}')
    rows = []
    for r in frame.itertuples(index=False):
        raw = r._asdict()
        eid = int(raw[id_col])
        gw = int(raw[gw_col])
        if gw < int(target_gameweek):
            continue
        horizon = gw - int(target_gameweek) + 1
        status = CoverageStatus(str(raw.get(coverage_col) or 'FORECAST').upper()) if coverage_col else CoverageStatus.FORECAST
        xp = None if status == CoverageStatus.NO_FORECAST else float(raw[xp_col])
        fixtures = _fixture_ids(official, eid, gw) if eid in official.player_ids else ()
        official_status = official.player_map()[eid].status if eid in official.player_ids else None
        rows.append(ProjectionRow(eid, gw, horizon, xp, fixtures, len(fixtures), official_status, float(raw[minutes_col]) if minutes_col and pd.notna(raw[minutes_col]) else None, float(raw[p_any_col]) if p_any_col and pd.notna(raw[p_any_col]) else None, float(raw[p_start_col]) if p_start_col and pd.notna(raw[p_start_col]) else None, float(raw[p60_col]) if p60_col and pd.notna(raw[p60_col]) else None, status, str(raw[reason_col]) if reason_col and pd.notna(raw[reason_col]) else None))
    return ProjectionSurface(1, provider_id, str(provider_version), generated_at, official.season, source_snapshot, scoring_rules_version, tuple(sorted({r.horizon for r in rows})), runtime_dependencies, tuple(rows))
