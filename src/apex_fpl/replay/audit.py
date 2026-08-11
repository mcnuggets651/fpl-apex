from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
import json


@dataclass(frozen=True)
class ReplayStoreAudit:
    season: str
    complete_gameweeks: tuple[int, ...]
    incomplete_gameweeks: tuple[int, ...]
    outcome_gameweeks: tuple[int, ...]
    apex_replay_eligible: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "complete_gameweeks": list(self.complete_gameweeks),
            "incomplete_gameweeks": list(self.incomplete_gameweeks),
            "outcome_gameweeks": list(self.outcome_gameweeks),
            "apex_replay_eligible": self.apex_replay_eligible,
            "blockers": list(self.blockers),
        }


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _valid_manifest(manifest: dict, *, season: str, gameweek: int, directory: Path) -> bool:
    if manifest.get("gameweek") != gameweek or manifest.get("season") != season:
        return False
    sources = manifest.get("sources")
    files = manifest.get("files")
    if not isinstance(sources, list) or not sources or not isinstance(files, dict):
        return False
    try:
        cutoff = datetime.fromisoformat(str(manifest["cutoff_utc"]).replace("Z", "+00:00"))
        deadline = datetime.fromisoformat(str(manifest["deadline_utc"]).replace("Z", "+00:00"))
        if cutoff.tzinfo is None or deadline.tzinfo is None or cutoff >= deadline:
            return False
        for source in sources:
            available = datetime.fromisoformat(str(source["available_at"]).replace("Z", "+00:00"))
            if available.tzinfo is None or available > cutoff:
                return False
        for filename in ("players.csv", "projections.csv"):
            declared = str(files[filename]["sha256"]).casefold()
            if _sha256(directory / filename) != declared:
                return False
    except (KeyError, TypeError, ValueError, OSError):
        return False
    return True


def audit_replay_store(root: Path, *, season: str = "2025-2026") -> ReplayStoreAudit:
    """Require explicit pre-deadline bundles; never infer them from result files."""
    complete: list[int] = []
    incomplete: list[int] = []
    outcomes: list[int] = []
    for gameweek in range(1, 39):
        directory = root / season / f"GW{gameweek}"
        mandatory = [directory / "manifest.json", directory / "players.csv", directory / "projections.csv"]
        if all(path.is_file() for path in mandatory):
            try:
                manifest = json.loads(mandatory[0].read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                incomplete.append(gameweek)
            else:
                if _valid_manifest(
                    manifest,
                    season=season,
                    gameweek=gameweek,
                    directory=directory,
                ):
                    complete.append(gameweek)
                else:
                    incomplete.append(gameweek)
        else:
            incomplete.append(gameweek)
        if (root / season / "outcomes" / f"GW{gameweek}.csv").is_file():
            outcomes.append(gameweek)

    blockers: list[str] = []
    if incomplete:
        blockers.append(f"missing or invalid pre-deadline Apex bundles for {len(incomplete)}/38 Gameweeks")
    if len(outcomes) != 38:
        blockers.append(f"missing isolated outcome files for {38 - len(outcomes)}/38 Gameweeks")
    return ReplayStoreAudit(
        season=season,
        complete_gameweeks=tuple(complete),
        incomplete_gameweeks=tuple(incomplete),
        outcome_gameweeks=tuple(outcomes),
        apex_replay_eligible=not blockers,
        blockers=tuple(blockers),
    )
