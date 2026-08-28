from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class ProjectionProviderSpec:
    key: str
    display_name: str
    xp_column: str
    source_status_name: str
    full_gameweek: bool = True
    eligible_for_production: bool = True


PROJECTION_PROVIDERS: dict[str, ProjectionProviderSpec] = {
    "airsenal": ProjectionProviderSpec(
        key="airsenal",
        display_name="AIrsenal",
        xp_column="airsenal_xp",
        source_status_name="airsenal",
    ),
    "dastan": ProjectionProviderSpec(
        key="dastan",
        display_name="Dastan",
        xp_column="dastan_xp",
        source_status_name="dastan",
    ),
    "openfpl": ProjectionProviderSpec(
        key="openfpl",
        display_name="OpenFPL",
        xp_column="openfpl_xp",
        source_status_name="openfpl",
    ),
    # Apex remains a challenger until a reviewed promotion changes that status.
    # Its native surface is fixture-level rather than a pre-aggregated full-GW export.
    "apex": ProjectionProviderSpec(
        key="apex",
        display_name="Apex proprietary",
        xp_column="apex_xp",
        source_status_name="apex_shadow",
        full_gameweek=False,
        eligible_for_production=False,
    ),
}

PRODUCTION_ELIGIBLE_PROVIDERS = frozenset(
    key for key, spec in PROJECTION_PROVIDERS.items() if spec.eligible_for_production
)


def normalise_provider_key(value: str) -> str:
    key = str(value or "").strip().casefold().replace("-", "").replace("_", "")
    aliases = {
        "airsenal": "airsenal",
        "dastan": "dastan",
        "openfpl": "openfpl",
        "apex": "apex",
        "apexproprietary": "apex",
    }
    if key not in aliases:
        raise ValueError(
            f"unknown projection provider {value!r}; expected one of "
            f"{sorted(PROJECTION_PROVIDERS)}"
        )
    return aliases[key]


def provider_spec(value: str) -> ProjectionProviderSpec:
    return PROJECTION_PROVIDERS[normalise_provider_key(value)]


def production_required_sources(
    configured_sources: Iterable[str],
    champion_provider: str,
) -> list[str]:
    """Return hard source dependencies for the selected forecast champion.

    Projection providers are mutually exclusive production authorities. Old provider
    names are removed before the champion source is added so switching champions is a
    configuration/promotion operation rather than an architecture rewrite.
    """
    provider_source_names = {
        spec.source_status_name for spec in PROJECTION_PROVIDERS.values()
    }
    required = [
        str(name)
        for name in configured_sources
        if str(name) and str(name) not in provider_source_names
    ]
    source = provider_spec(champion_provider).source_status_name
    if source not in required:
        required.append(source)
    return list(dict.fromkeys(required))


def provider_columns_present(columns: Iterable[str]) -> dict[str, str]:
    available = set(columns)
    return {
        key: spec.xp_column
        for key, spec in PROJECTION_PROVIDERS.items()
        if spec.xp_column in available
    }
