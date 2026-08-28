from __future__ import annotations

from pathlib import Path

from apex.domain.models import OfficialSnapshot, ProjectionSurface
from apex.forecast.adapters.csv import load_projection_csv


def load_openfpl_export(
    path: str | Path,
    *,
    official: OfficialSnapshot,
    target_gameweek: int,
    provider_version: str,
) -> ProjectionSurface:
    """Load an OpenFPL export after current-rule requalification.

    Historical OpenFPL artefacts do not automatically satisfy 2026/27 scoring
    compatibility. This adapter is intentionally strict and does not reinterpret
    older predictions as current production forecasts.
    """
    return load_projection_csv(
        path,
        provider_id="openfpl",
        official=official,
        target_gameweek=target_gameweek,
        provider_version=provider_version,
        scoring_rules_version="2026-2027",
        runtime_dependencies=(),
    )
