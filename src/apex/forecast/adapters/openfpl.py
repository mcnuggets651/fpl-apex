from pathlib import Path

from apex.domain.models import OfficialSnapshot, ProjectionSurface

from .csv import load_projection_csv


def load_openfpl(
    path: str | Path,
    *,
    official: OfficialSnapshot,
    target_gameweek: int,
) -> ProjectionSurface:
    return load_projection_csv(
        path,
        provider_id="openfpl",
        official=official,
        target_gameweek=target_gameweek,
        scoring_rules_version=None,
        require_source_snapshot=True,
    )
