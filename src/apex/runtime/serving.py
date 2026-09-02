from __future__ import annotations

from apex.domain.models import (
    OfficialSnapshot,
    ProductionProjectionSurface,
    ProviderHealth,
    ProviderRole,
    ProviderStatus,
    Qualification,
    TeamState,
)
from apex.forecast.registry import (
    max_contiguous_qualified_horizon,
    serving_policy,
)

from .serde import projection_from_dict


def _strict_bool(value, *, field: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field} must be an explicit boolean")
    return value


def status_from_row(row, surface):
    return ProviderStatus(
        row["provider_id"],
        ProviderRole(row["role"]),
        int(row["priority"]),
        ProviderHealth(row["health"]),
        {
            int(key): Qualification(value)
            for key, value in row["qualification_by_horizon"].items()
        },
        surface,
        tuple(row.get("reasons", [])),
        _strict_bool(
            row.get("serve_authorized", False),
            field=f"provider {row.get('provider_id', '<unknown>')} serve_authorized",
        ),
        Qualification(row.get("predictive_status", "INSUFFICIENT_HISTORY")),
    )


def statuses_from_snapshot(snapshot, matrix) -> tuple[ProviderStatus, ...]:
    statuses = []
    for row in matrix:
        try:
            surface = projection_from_dict(
                snapshot.read_json(f"providers/{row['provider_id']}.json")
            )
        except (KeyError, FileNotFoundError):
            surface = None
        statuses.append(status_from_row(row, surface))
    return tuple(statuses)


def canonical_surface(policy, max_horizon: int) -> ProductionProjectionSurface:
    rows = []
    provider_ids = []
    versions = []
    first_surface = None
    for horizon in range(1, int(max_horizon) + 1):
        provider = policy[horizon]
        if provider.surface is None:
            raise RuntimeError(
                f"serving provider {provider.provider_id} has no frozen surface"
            )
        first_surface = first_surface or provider.surface
        provider_ids.append(provider.provider_id)
        versions.append(f"{provider.provider_id}:{provider.surface.provider_version}")
        rows.extend(
            row for row in provider.surface.rows if row.horizon == horizon
        )
    if first_surface is None:
        raise RuntimeError("cannot build canonical projection without serving horizon")
    return ProductionProjectionSurface(
        1,
        "|".join(provider_ids),
        "|".join(versions),
        max(provider.surface.generated_at for provider in policy.values() if provider.surface),
        first_surface.season,
        first_surface.source_snapshot,
        first_surface.scoring_rules_version,
        tuple(range(1, int(max_horizon) + 1)),
        tuple(rows),
    )


def reconstruct_frozen_serving(
    snapshot,
    official: OfficialSnapshot,
    team: TeamState | None,
    run: dict,
    matrix,
):
    statuses = statuses_from_snapshot(snapshot, matrix)
    universe = official.decision_universe(
        set(team.squad_ids) if team else frozenset()
    )
    policy = serving_policy(
        statuses,
        max_horizon=int(run["max_horizon"]),
        decision_universe=universe,
    )
    max_horizon = max_contiguous_qualified_horizon(policy)
    canonical = canonical_surface(policy, max_horizon) if max_horizon >= 1 else None
    return statuses, universe, policy, max_horizon, canonical
