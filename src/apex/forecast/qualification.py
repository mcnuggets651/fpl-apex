from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from apex.domain.models import OfficialSnapshot, ProjectionSurface, ProviderHealth, Qualification
from apex.forecast.contract import coverage_errors, validate_projection_surface

@dataclass(frozen=True)
class QualificationResult:
    operational: Qualification
    health: ProviderHealth
    qualified_horizons: tuple[int, ...]
    reasons: tuple[str, ...]

def qualify_surface(surface: ProjectionSurface, official: OfficialSnapshot, *, decision_universe: frozenset[int], requested_horizons: tuple[int, ...], max_age_hours: float, now: datetime | None=None) -> QualificationResult:
    reasons = list(validate_projection_surface(surface, official))
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        g = datetime.fromisoformat(surface.generated_at.replace('Z', '+00:00'))
        g = g if g.tzinfo else g.replace(tzinfo=timezone.utc)
        age = (now - g.astimezone(timezone.utc)).total_seconds() / 3600
        if age < -0.1:
            reasons.append(f'provider timestamp is in the future by {-age:.2f}h')
        if age > max_age_hours:
            reasons.append(f'provider stale: {age:.2f}h > {max_age_hours:.2f}h')
    except Exception as e:
        reasons.append(f'provider generated_at invalid: {e}')
    q = []
    for h in requested_horizons:
        es = coverage_errors(surface, decision_universe, horizon=h)
        if not es and h in surface.supported_horizons:
            q.append(h)
        else:
            reasons.extend(es)
    if reasons:
        health = ProviderHealth.STALE if any(('stale' in r for r in reasons)) else ProviderHealth.INCOMPLETE
        return QualificationResult(Qualification.UNQUALIFIED, health, tuple(q), tuple(dict.fromkeys(reasons)))
    return QualificationResult(Qualification.QUALIFIED, ProviderHealth.HEALTHY, tuple(q), ())
