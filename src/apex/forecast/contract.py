from __future__ import annotations
import hashlib, json, math
from collections import Counter
from dataclasses import asdict
from apex.domain.models import CoverageStatus, OfficialSnapshot, ProjectionSurface, ProductionProjectionSurface

def projection_surface_hash(surface) -> str:
    payload = json.dumps(asdict(surface), sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()

def validate_projection_surface(surface: ProjectionSurface, official: OfficialSnapshot, *, required_horizons: tuple[int, ...] | None=None) -> tuple[str, ...]:
    errors = []
    seen = set()
    horizons = set(required_horizons or surface.supported_horizons)
    if not surface.provider_id.strip():
        errors.append('provider_id missing')
    if not surface.provider_version.strip():
        errors.append('provider_version missing')
    if surface.season != official.season:
        errors.append(f'season mismatch: {surface.season} != {official.season}')
    for row in surface.rows:
        key = (int(row.element_id), int(row.gameweek), int(row.horizon))
        if key in seen:
            errors.append(f'duplicate projection row {key}')
            continue
        seen.add(key)
        if row.element_id not in official.player_ids:
            errors.append(f'unknown Official FPL id {row.element_id}')
        if row.horizon <= 0:
            errors.append(f'invalid horizon {row.horizon} for {row.element_id}')
        if row.n_fixtures != len(row.fixture_ids):
            errors.append(f'fixture count mismatch for {key}')
        if row.coverage_status == CoverageStatus.FORECAST:
            if row.expected_points is None or not math.isfinite(float(row.expected_points)):
                errors.append(f'non-finite xP for {key}')
        else:
            if row.expected_points is not None:
                errors.append(f'NO_FORECAST row must have expected_points=None for {key}')
            if not row.coverage_reason:
                errors.append(f'NO_FORECAST row missing reason for {key}')
    missing = sorted((h for h in horizons if h not in set(surface.supported_horizons)))
    if missing:
        errors.append(f'required horizons unsupported: {missing}')
    return tuple(errors)

def coverage_errors(surface, decision_universe: frozenset[int], *, horizon: int) -> tuple[str, ...]:
    rows = [r for r in surface.rows if r.horizon == int(horizon)]
    by = Counter((r.element_id for r in rows if r.coverage_status == CoverageStatus.FORECAST))
    missing = sorted((pid for pid in decision_universe if by[pid] != 1))
    return () if not missing else (f'horizon {horizon} incomplete FORECAST coverage for Official ids {missing}',)

def production_view(surface: ProjectionSurface, *, horizon: int) -> ProductionProjectionSurface:
    rows = tuple((r for r in surface.rows if r.horizon <= int(horizon)))
    return ProductionProjectionSurface(surface.schema_version, surface.provider_id, surface.provider_version, surface.generated_at, surface.season, surface.source_snapshot, surface.scoring_rules_version, tuple((h for h in surface.supported_horizons if h <= horizon)), rows)
