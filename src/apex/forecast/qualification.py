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
    required_scoring_rules_version: str | None = None,
    now: datetime | None = None,
) -> QualificationResult:
    reasons = list(validate_projection_surface(surface, official))
    if (
        required_scoring_rules_version
        and surface.scoring_rules_version != required_scoring_rules_version
    ):
        reasons.append(
            "provider scoring rules incompatible: "
            f"{surface.scoring_rules_version} != {required_scoring_rules_version}"
        )

    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    try:
        generated = datetime.fromisoformat(surface.generated_at.replace("Z", "+00:00"))
        generated = (
            generated
            if generated.tzinfo
            else generated.replace(tzinfo=timezone.utc)
        )
        age = (
            now - generated.astimezone(timezone.utc)
        ).total_seconds() / 3600
        if age < -0.1:
            reasons.append(f"provider timestamp is in the future by {-age:.2f}h")
        if age > max_age_hours:
            reasons.append(f"provider stale: {age:.2f}h > {max_age_hours:.2f}h")
    except Exception as exc:
        reasons.append(f"provider generated_at invalid: {exc}")

    qualified = []
    for horizon in requested_horizons:
        errors = coverage_errors(surface, decision_universe, horizon=horizon)
        if not errors and horizon in surface.supported_horizons:
            qualified.append(horizon)
        else:
            reasons.extend(errors)

    if reasons:
        health = (
            ProviderHealth.STALE
            if any("stale" in reason for reason in reasons)
            else ProviderHealth.INCOMPLETE
        )
        return QualificationResult(
            Qualification.UNQUALIFIED,
            health,
            tuple(qualified),
            tuple(dict.fromkeys(reasons)),
        )
    return QualificationResult(
        Qualification.QUALIFIED,
        ProviderHealth.HEALTHY,
        tuple(qualified),
        (),
    )
