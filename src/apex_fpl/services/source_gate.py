from __future__ import annotations

from dataclasses import dataclass
from apex_fpl.services.provenance import SourceStatus


@dataclass(frozen=True)
class SafetyGate:
    safe_to_act: bool
    confidence: float
    blockers: list[str]
    warnings: list[str]


def evaluate_source_gate(
    sources: list[SourceStatus],
    integrity_warnings: int,
    require_airsenal: bool = True,
    require_core: bool = True,
) -> SafetyGate:
    status = {s.name: s for s in sources}
    blockers: list[str] = []
    warnings: list[str] = []
    official = status.get("official_fpl")
    if official is None or not official.ok:
        blockers.append("official FPL source is unavailable")
    core = status.get("fpl_core_playerstats")
    if require_core and (core is None or not core.ok):
        blockers.append("FPL Core Insights is unavailable in strict Apex mode")
    elif core is None or not core.ok:
        warnings.append("FPL Core Insights unavailable; projection depth reduced")
    air = status.get("airsenal")
    air_missing = air is None or not air.ok or "not configured" in (air.detail or "").lower()
    if require_airsenal and air_missing:
        blockers.append("genuine AIrsenal projections are not loaded")
    elif air_missing:
        warnings.append("AIrsenal projections missing; ensemble re-normalised")
    if integrity_warnings:
        warnings.append(f"{integrity_warnings} auxiliary identity conflicts retained as official FPL truth")
    optional_bad = [s.name for s in sources if not s.ok and s.name not in {"official_fpl", "fpl_core_playerstats", "airsenal"}]
    if optional_bad:
        warnings.append("optional sources unavailable: " + ", ".join(sorted(optional_bad)))
    confidence = 1.0 - min(0.22, 0.06 * len(warnings)) - min(0.70, 0.25 * len(blockers))
    return SafetyGate(not blockers, max(0.0, min(1.0, confidence)), blockers, warnings)
