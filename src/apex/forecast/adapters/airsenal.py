from __future__ import annotations

from pathlib import Path

from apex.domain.models import OfficialSnapshot, ProjectionSurface
from apex.forecast.adapters.csv import load_projection_csv


def load_airsenal(
    path: str | Path,
    *,
    official: OfficialSnapshot,
    target_gameweek: int,
) -> ProjectionSurface:
    return load_projection_csv(
        path,
        provider_id="airsenal",
        official=official,
        target_gameweek=target_gameweek,
        scoring_rules_version="2026-2027",
        runtime_dependencies=(),
    )
