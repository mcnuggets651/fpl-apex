from pathlib import Path

from apex.domain.models import OfficialSnapshot, ProjectionSurface

from .csv import load_projection_csv

CURRENT_SCORING_RULES_VERSION = "fpl-2026-27-v1"


def load_airsenal(
    path: str | Path,
    *,
    official: OfficialSnapshot,
    target_gameweek: int,
    require_source_snapshot: bool = False,
    trusted_source_snapshot: str | None = None,
) -> ProjectionSurface:
    return load_projection_csv(
        path,
        provider_id="airsenal",
        official=official,
        target_gameweek=target_gameweek,
        scoring_rules_version=CURRENT_SCORING_RULES_VERSION,
        require_source_snapshot=require_source_snapshot,
        trusted_source_snapshot=trusted_source_snapshot,
    )
