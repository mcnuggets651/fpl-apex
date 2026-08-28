from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from dataclasses import asdict

from apex.domain.models import (
    CoverageStatus,
    OfficialSnapshot,
    ProductionProjectionSurface,
    ProjectionSurface,
)

PROBABILITY_TOLERANCE = 1e-6
MINUTES_TOLERANCE = 1e-6


def projection_surface_hash(surface) -> str:
    payload = json.dumps(
        asdict(surface),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _validate_optional_probability(
    errors: list[str],
    *,
    label: str,
    value: float | None,
    key: tuple[int, int, int],
) -> None:
    if value is None:
        return
    numeric = float(value)
    if not math.isfinite(numeric):
        errors.append(f"non-finite {label} for {key}")
    elif numeric < -PROBABILITY_TOLERANCE or numeric > 1.0 + PROBABILITY_TOLERANCE:
        errors.append(f"{label} outside [0,1] for {key}: {numeric}")


def validate_projection_surface(
    surface: ProjectionSurface,
    official: OfficialSnapshot,
    *,
    required_horizons: tuple[int, ...] | None = None,
) -> tuple[str, ...]:
    errors = []
    seen = set()
    horizons = set(required_horizons or surface.supported_horizons)
    if not surface.provider_id.strip():
        errors.append("provider_id missing")
    if not surface.provider_version.strip():
        errors.append("provider_version missing")
    if surface.season != official.season:
        errors.append(f"season mismatch: {surface.season} != {official.season}")
    for row in surface.rows:
        key = (int(row.element_id), int(row.gameweek), int(row.horizon))
        if key in seen:
            errors.append(f"duplicate projection row {key}")
            continue
        seen.add(key)
        if row.element_id not in official.player_ids:
            errors.append(f"unknown Official FPL id {row.element_id}")
        if row.horizon <= 0:
            errors.append(f"invalid horizon {row.horizon} for {row.element_id}")
        if row.n_fixtures != len(row.fixture_ids):
            errors.append(f"fixture count mismatch for {key}")
        if row.coverage_status == CoverageStatus.FORECAST:
            if row.expected_points is None or not math.isfinite(
                float(row.expected_points)
            ):
                errors.append(f"non-finite xP for {key}")
        else:
            if row.expected_points is not None:
                errors.append(f"NO_FORECAST row must have expected_points=None for {key}")
            if not row.coverage_reason:
                errors.append(f"NO_FORECAST row missing reason for {key}")

        if row.expected_minutes is not None:
            minutes = float(row.expected_minutes)
            maximum_minutes = 90.0 * max(1, int(row.n_fixtures))
            if not math.isfinite(minutes):
                errors.append(f"non-finite expected_minutes for {key}")
            elif minutes < -MINUTES_TOLERANCE or minutes > maximum_minutes + MINUTES_TOLERANCE:
                errors.append(
                    f"expected_minutes outside feasible range for {key}: "
                    f"{minutes} not in [0,{maximum_minutes}]"
                )

        _validate_optional_probability(
            errors,
            label="p_appearance",
            value=row.p_appearance,
            key=key,
        )
        _validate_optional_probability(
            errors,
            label="p_start",
            value=row.p_start,
            key=key,
        )
        _validate_optional_probability(
            errors,
            label="p60",
            value=row.p60,
            key=key,
        )
        if row.p_appearance is not None:
            appearance = float(row.p_appearance)
            if row.p_start is not None and float(row.p_start) > appearance + PROBABILITY_TOLERANCE:
                errors.append(
                    f"p_start exceeds p_appearance for {key}: "
                    f"{row.p_start} > {row.p_appearance}"
                )
            if row.p60 is not None and float(row.p60) > appearance + PROBABILITY_TOLERANCE:
                errors.append(
                    f"p60 exceeds p_appearance for {key}: "
                    f"{row.p60} > {row.p_appearance}"
                )
    missing = sorted(
        horizon
        for horizon in horizons
        if horizon not in set(surface.supported_horizons)
    )
    if missing:
        errors.append(f"required horizons unsupported: {missing}")
    return tuple(errors)


def coverage_errors(
    surface,
    decision_universe: frozenset[int],
    *,
    horizon: int,
) -> tuple[str, ...]:
    rows = [row for row in surface.rows if row.horizon == int(horizon)]
    by_player = Counter(
        row.element_id
        for row in rows
        if row.coverage_status == CoverageStatus.FORECAST
    )
    missing = sorted(pid for pid in decision_universe if by_player[pid] != 1)
    if not missing:
        return ()
    return (
        f"horizon {horizon} incomplete FORECAST coverage for Official ids {missing}",
    )


def production_view(
    surface: ProjectionSurface,
    *,
    horizon: int,
) -> ProductionProjectionSurface:
    rows = tuple(row for row in surface.rows if row.horizon <= int(horizon))
    return ProductionProjectionSurface(
        surface.schema_version,
        surface.provider_id,
        surface.provider_version,
        surface.generated_at,
        surface.season,
        surface.source_snapshot,
        surface.scoring_rules_version,
        tuple(value for value in surface.supported_horizons if value <= horizon),
        rows,
    )
