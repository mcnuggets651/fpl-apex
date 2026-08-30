from pathlib import Path

from apex.domain.models import OfficialSnapshot, ProjectionSurface
from apex.runtime.config import CURRENT_SCORING_RULES_VERSION

from .csv import load_projection_csv


def load_apex_proprietary(
    path: str | Path,
    *,
    official: OfficialSnapshot,
    target_gameweek: int,
) -> ProjectionSurface:
    """Load the isolated raw Apex xP export as a non-serving V2 surface."""
    return load_projection_csv(
        path,
        provider_id="apex_proprietary",
        official=official,
        target_gameweek=target_gameweek,
        scoring_rules_version=CURRENT_SCORING_RULES_VERSION,
        require_source_snapshot=True,
        runtime_dependencies=("isolated-legacy-apex-projection-worker",),
    )
