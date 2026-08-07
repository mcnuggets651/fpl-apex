from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


REQUIRED_SCENARIOS = ("unrestricted", "haaland", "no-haaland")
REQUIRED_SOURCES = (
    "official_fpl",
    "fpl_core_playerstats",
    "fixture_model",
    "airsenal",
    "news_feeds",
)


@dataclass(frozen=True)
class ReadinessResult:
    ready: bool
    blockers: tuple[str, ...]


def evaluate_report(payload: dict[str, Any]) -> ReadinessResult:
    """Validate that a generated report is a full Apex decision artifact.

    This is intentionally stricter than merely checking that optimisation returned
    a squad. A report is production-ready only when the core source gate passed,
    official snapshot hashes exist, and every required comparison scenario solved.
    """
    blockers: list[str] = []

    if payload.get("safe_to_act") is not True:
        blockers.append("report safe_to_act is not true")
    if payload.get("full_apex_ready") is not True:
        blockers.append("report full_apex_ready is not true")

    quality = payload.get("data_quality")
    if not isinstance(quality, dict):
        blockers.append("field-level data-quality report is missing")
    elif quality.get("ready") is not True:
        blockers.append("field-level data-quality gate is not ready")

    snapshot = payload.get("official_snapshot") or {}
    for field in ("snapshot_id", "retrieved_at", "bootstrap_sha256", "fixtures_sha256"):
        if not snapshot.get(field):
            blockers.append(f"official snapshot missing {field}")
    for field in ("bootstrap_sha256", "fixtures_sha256"):
        digest = str(snapshot.get(field, ""))
        if digest and len(digest) != 64:
            blockers.append(f"official snapshot {field} is not a SHA256 digest")

    source_rows = payload.get("sources") or []
    sources = {str(row.get("name")): row for row in source_rows if isinstance(row, dict)}
    for name in REQUIRED_SOURCES:
        row = sources.get(name)
        if row is None:
            blockers.append(f"required source absent from report: {name}")
            continue
        if row.get("configured") is not True:
            blockers.append(f"required source not configured: {name}")
        if row.get("ok") is not True:
            blockers.append(f"required source unhealthy: {name}")

    scenarios = payload.get("scenarios") or {}
    for name in REQUIRED_SCENARIOS:
        row = scenarios.get(name)
        if not isinstance(row, dict):
            blockers.append(f"required scenario missing: {name}")
            continue
        if row.get("status") != "Optimal":
            blockers.append(f"required scenario not Optimal: {name}")
        if len(row.get("squad") or []) != 15:
            blockers.append(f"required scenario does not contain 15-player squad: {name}")
        if len(row.get("xi") or []) != 11:
            blockers.append(f"required scenario does not contain legal XI size: {name}")
        if len(row.get("captain") or []) != 1:
            blockers.append(f"required scenario captain missing/ambiguous: {name}")
        if len(row.get("vice_captain") or []) != 1:
            blockers.append(f"required scenario vice-captain missing/ambiguous: {name}")

    return ReadinessResult(ready=not blockers, blockers=tuple(blockers))


def load_and_evaluate(path: str | Path) -> ReadinessResult:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return ReadinessResult(False, ("report root is not a JSON object",))
    return evaluate_report(payload)
