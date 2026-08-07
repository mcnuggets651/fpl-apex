from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import pandas as pd

from apex_fpl.data.official import OfficialSnapshot
from apex_fpl.services.provenance import SourceStatus


@dataclass
class SafetyAssessment:
    safe_to_act: bool
    full_apex_ready: bool
    blockers: list[str]
    warnings: list[str]

    def to_dict(self):
        return asdict(self)


def assess_safety(
    official: OfficialSnapshot,
    sources: list[SourceStatus],
    integrity: pd.DataFrame,
    projections: pd.DataFrame,
    scenarios: dict,
    required_sources: list[str],
    max_official_age_hours: float = 26.0,
) -> SafetyAssessment:
    blockers: list[str] = []
    warnings: list[str] = []

    if official.retrieved_at:
        created = datetime.fromisoformat(official.retrieved_at)
        age = (datetime.now(timezone.utc) - created).total_seconds() / 3600
        if age > max_official_age_hours:
            blockers.append(f"official FPL snapshot is stale ({age:.1f}h old)")
    if official.players["player_id"].duplicated().any():
        blockers.append("duplicate official player IDs")
    if official.players["position"].isna().any():
        blockers.append("unknown official FPL position exists")

    by_name = {s.name: s for s in sources}
    for name in required_sources:
        s = by_name.get(name)
        if s is None:
            blockers.append(f"required source missing: {name}")
        elif not s.configured:
            blockers.append(f"required source not configured: {name}")
        elif not s.ok:
            blockers.append(f"required source unhealthy: {name}: {s.detail}")

    if not integrity.empty:
        warnings.append(f"{len(integrity)} auxiliary identity mismatches; official identity retained")
    if projections.empty:
        blockers.append("projection table is empty")
    else:
        if "projection_confidence" in projections:
            low = float((pd.to_numeric(projections["projection_confidence"], errors="coerce") < 0.35).mean())
            if low > 0.25:
                warnings.append(f"{low:.0%} of projection rows have confidence below 0.35")
    if not scenarios:
        blockers.append("no squad scenario produced")
    else:
        bad = [name for name, sol in scenarios.items() if getattr(sol, "status", "") != "Optimal"]
        if bad:
            blockers.append("non-optimal squad scenarios: " + ", ".join(bad))

    # full_apex_ready is deliberately strict: all requested production sources must
    # be configured and healthy. safe_to_act additionally requires no other blockers.
    full_apex_ready = not any("required source" in b for b in blockers)
    return SafetyAssessment(not blockers, full_apex_ready and not blockers, blockers, warnings)
