from __future__ import annotations

from pathlib import Path

from apex.domain.models import OfficialSnapshot, ProjectionSurface
from apex.forecast.adapters.csv import load_projection_csv


def load_dastan_export(
    path: str | Path,
    *,
    official: OfficialSnapshot,
    target_gameweek: int,
    provider_version: str,
) -> ProjectionSurface:
    """Load a current Dastan export only after upstream inference has produced it.

    Apex deliberately does not fabricate live Dastan predictions from historical
    training frames. Operational qualification must supply a genuine pre-deadline
    current-season export keyed to Official FPL IDs.
    """
    return load_projection_csv(
        path,
        provider_id="dastan",
        official=official,
        target_gameweek=target_gameweek,
        provider_version=provider_version,
        scoring_rules_version="2026-2027",
        runtime_dependencies=(),
    )
