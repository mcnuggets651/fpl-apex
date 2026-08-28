from __future__ import annotations

from dataclasses import replace

from apex.domain.models import ProviderHealth, ProviderRole, ProviderStatus
from apex.forecast.contract import coverage_errors


class NoServingProvider(RuntimeError):
    pass


def assess_live_health(
    provider: ProviderStatus,
    *,
    horizon: int,
    decision_universe: frozenset[int],
) -> ProviderStatus:
    if provider.surface is None:
        return replace(
            provider,
            health=ProviderHealth.ERROR,
            reasons=provider.reasons + ("surface missing",),
        )
    errors = coverage_errors(provider.surface, decision_universe, horizon=horizon)
    if errors:
        return replace(
            provider,
            health=ProviderHealth.INCOMPLETE,
            reasons=provider.reasons + errors,
        )
    return provider


def serving_provider(
    providers: tuple[ProviderStatus, ...] | list[ProviderStatus],
    *,
    horizon: int,
    decision_universe: frozenset[int],
) -> ProviderStatus:
    eligible: list[ProviderStatus] = []
    for provider in providers:
        if provider.role == ProviderRole.SHADOW:
            continue
        if not provider.qualified(horizon):
            continue
        assessed = assess_live_health(
            provider,
            horizon=horizon,
            decision_universe=decision_universe,
        )
        if assessed.health == ProviderHealth.HEALTHY:
            eligible.append(assessed)
    if not eligible:
        raise NoServingProvider(f"no healthy qualified complete provider for H{horizon}")
    role_order = {ProviderRole.CHAMPION: 0, ProviderRole.STANDBY: 1}
    return min(eligible, key=lambda p: (role_order[p.role], p.priority, p.provider_id))


def serving_policy(
    providers: tuple[ProviderStatus, ...] | list[ProviderStatus],
    *,
    max_horizon: int,
    decision_universe: frozenset[int],
) -> dict[int, ProviderStatus]:
    result: dict[int, ProviderStatus] = {}
    for horizon in range(1, int(max_horizon) + 1):
        try:
            result[horizon] = serving_provider(
                providers,
                horizon=horizon,
                decision_universe=decision_universe,
            )
        except NoServingProvider:
            break
    return result


def max_contiguous_qualified_horizon(policy: dict[int, ProviderStatus]) -> int:
    horizon = 0
    while horizon + 1 in policy:
        horizon += 1
    return horizon
