from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from apex.domain.models import (
    OfficialSnapshot,
    ProjectionSurface,
    ProviderHealth,
    Qualification,
)
from apex.forecast.contract import coverage_errors, validate_projection_surface


@dataclass(frozen=True)
class QualificationResult:
    operational: Qualification
    health: ProviderHealth
    qualified_horizons: tuple[int, ...]
    reasons: tuple[str, ...]


def qualify_surface(
    surface: ProjectionSurface,
    official: OfficialSnapshot,
    *,
    decision_universe: frozenset[int],
    requested_horizons: tuple[int, ...],
    max_age_hours: float,
    now: datetime | None = None,
) -> QualificationResult:
    reasons = list(validate_projection_surface(surface, official))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        generated = datetime.fromisoformat(surface.generated_at.replace("Z", "+00:00"))
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        age_hours = (now - generated.astimezone(timezone.utc)).total_seconds() / 3600.0
        if age_hours < -0.1:
            reasons.append(f"provider timestamp is in the future by {-age_hours:.2f}h")
        if age_hours > float(max_age_hours):
            reasons.append(f"provider stale: {age_hours:.2f}h > {max_age_hours:.2f}h")
    except Exception as exc:
        reasons.append(f"provider generated_at invalid: {exc}")
    qualified: list[int] = []
    for horizon in requested_horizons:
        horizon_errors = coverage_errors(surface, decision_universe, horizon=horizon)
        if not horizon_errors and horizon in surface.supported_horizons:
            qualified.append(int(horizon))
        else:
            reasons.extend(horizon_errors)
    if reasons:
        health = ProviderHealth.STALE if any("stale" in reason for reason in reasons) else ProviderHealth.INCOMPLETE
        return QualificationResult(Qualification.UNQUALIFIED, health, tuple(qualified), tuple(dict.fromkeys(reasons)))
    return QualificationResult(
        Qualification.QUALIFIED,
        ProviderHealth.HEALTHY,
        tuple(qualified),
        (),
    )
