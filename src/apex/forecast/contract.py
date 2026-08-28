from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict

from apex.domain.models import CoverageStatus, OfficialSnapshot, ProjectionSurface


def projection_surface_hash(surface: ProjectionSurface) -> str:
    payload = json.dumps(asdict(surface), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_projection_surface(
    surface: ProjectionSurface,
    official: OfficialSnapshot,
    *,
    required_horizons: tuple[int, ...] | None = None,
) -> tuple[str, ...]:
    errors: list[str] = []
    official_ids = official.player_ids
    seen: set[tuple[int, int, int]] = set()
    horizons = set(required_horizons or surface.supported_horizons)
    if not surface.provider_id.strip():
        errors.append("provider_id missing")
    if not surface.provider_version.strip():
        errors.append("provider_version missing")
    if not surface.generated_at:
        errors.append("generated_at missing")
    if surface.season != official.season:
        errors.append(f"season mismatch: {surface.season} != {official.season}")
    for row in surface.rows:
        key = (int(row.element_id), int(row.gameweek), int(row.horizon))
        if key in seen:
            errors.append(f"duplicate projection row {key}")
            continue
        seen.add(key)
        if row.element_id not in official_ids:
            errors.append(f"unknown Official FPL id {row.element_id}")
        if row.horizon <= 0:
            errors.append(f"invalid horizon {row.horizon} for {row.element_id}")
        if row.n_fixtures != len(row.fixture_ids):
            errors.append(f"fixture count mismatch for {key}")
        if row.coverage_status == CoverageStatus.FORECAST:
            if row.expected_points is None or not math.isfinite(float(row.expected_points)):
                errors.append(f"non-finite xP for {key}")
        else:
            if row.expected_points is not None:
                errors.append(f"NO_FORECAST row must have expected_points=None for {key}")
            if not row.coverage_reason:
                errors.append(f"NO_FORECAST row missing reason for {key}")
    missing_horizons = sorted(h for h in horizons if h not in set(surface.supported_horizons))
    if missing_horizons:
        errors.append(f"required horizons unsupported: {missing_horizons}")
    return tuple(errors)


def coverage_errors(
    surface: ProjectionSurface,
    decision_universe: frozenset[int],
    *,
    horizon: int,
) -> tuple[str, ...]:
    rows = [row for row in surface.rows if row.horizon == int(horizon)]
    by_player = Counter(row.element_id for row in rows if row.coverage_status == CoverageStatus.FORECAST)
    missing = sorted(pid for pid in decision_universe if by_player[pid] != 1)
    if not missing:
        return ()
    return (f"horizon {horizon} incomplete FORECAST coverage for Official ids {missing}",)
