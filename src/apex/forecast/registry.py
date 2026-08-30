from __future__ import annotations
from dataclasses import replace
from apex.domain.models import ProviderHealth, ProviderRole, ProviderStatus
from apex.forecast.contract import coverage_errors

class NoServingProvider(RuntimeError):
    pass

def assess_live_health(provider: ProviderStatus, *, horizon: int, decision_universe: frozenset[int]) -> ProviderStatus:
    if provider.surface is None:
        return replace(provider, health=ProviderHealth.ERROR, reasons=provider.reasons + ('surface missing',))
    errors = coverage_errors(provider.surface, decision_universe, horizon=horizon)
    if errors:
        return replace(provider, health=ProviderHealth.INCOMPLETE, reasons=provider.reasons + errors)
    return provider

def serving_provider(providers, *, horizon: int, decision_universe: frozenset[int]) -> ProviderStatus:
    eligible = []
    for p in providers:
        if p.role == ProviderRole.SHADOW or not p.serve_authorized or (not p.qualified(horizon)):
            continue
        a = assess_live_health(p, horizon=horizon, decision_universe=decision_universe)
        if a.health == ProviderHealth.HEALTHY:
            eligible.append(a)
    if not eligible:
        raise NoServingProvider(f'no healthy authorized qualified complete provider for H{horizon}')
    role_order = {ProviderRole.CHAMPION: 0, ProviderRole.STANDBY: 1}
    return min(eligible, key=lambda p: (role_order[p.role], p.priority, p.provider_id))

def serving_policy(providers, *, max_horizon: int, decision_universe: frozenset[int]) -> dict[int, ProviderStatus]:
    out = {}
    for h in range(1, int(max_horizon) + 1):
        try:
            out[h] = serving_provider(providers, horizon=h, decision_universe=decision_universe)
        except NoServingProvider:
            break
    return out

def max_contiguous_qualified_horizon(policy):
    h = 0
    while h + 1 in policy:
        h += 1
    return h
