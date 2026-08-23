"""Manager-neutral sealed world identity for Apex V2.

The constitutional core contains only semantic values. Retrieval timestamps, run IDs,
HTTP clients and storage locations are deliberately excluded from ``GlobalWorldId``.
A world is identified by the immutable bytes of its source artifacts plus the governed
world schema and season.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .canonical import canonical_sha256
from .ids import GlobalWorldId


GLOBAL_WORLD_SCHEMA_VERSION = 1


def _validate_sha256_id(value: str, *, field: str) -> str:
    algorithm, separator, digest = str(value).partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{field} must be a sha256 artifact id")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{field} has an invalid sha256 digest") from exc
    return digest


@dataclass(frozen=True, slots=True)
class WorldSource:
    """One immutable source object that participates in global-world identity."""

    source_name: str
    artifact_id: str
    content_sha256: str
    schema_name: str
    schema_version: str

    def __post_init__(self) -> None:
        name = self.source_name.strip()
        if not name:
            raise ValueError("world source_name cannot be empty")
        digest = _validate_sha256_id(self.artifact_id, field="artifact_id")
        if self.content_sha256 != digest:
            raise ValueError("content_sha256 must match artifact_id")
        if not self.schema_name.strip() or not self.schema_version.strip():
            raise ValueError("world source schema identity cannot be empty")
        object.__setattr__(self, "source_name", name)

    def as_dict(self) -> dict[str, str]:
        return {
            "source_name": self.source_name,
            "artifact_id": self.artifact_id,
            "content_sha256": self.content_sha256,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorldSource":
        return cls(
            source_name=str(payload["source_name"]),
            artifact_id=str(payload["artifact_id"]),
            content_sha256=str(payload["content_sha256"]),
            schema_name=str(payload["schema_name"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class GlobalWorld:
    """Immutable semantic description of one manager-neutral football world."""

    season: str
    sources: tuple[WorldSource, ...]
    player_count: int
    team_count: int
    fixture_count: int
    event_count: int
    schema_version: int = GLOBAL_WORLD_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GLOBAL_WORLD_SCHEMA_VERSION:
            raise ValueError("unsupported GlobalWorld schema_version")
        season = self.season.strip()
        if not season:
            raise ValueError("GlobalWorld season cannot be empty")
        ordered = tuple(sorted(self.sources, key=lambda item: item.source_name))
        names = [item.source_name for item in ordered]
        if not ordered or len(names) != len(set(names)):
            raise ValueError("GlobalWorld sources must be non-empty and uniquely named")
        for field_name in ("player_count", "team_count", "fixture_count", "event_count"):
            if int(getattr(self, field_name)) < 0:
                raise ValueError(f"{field_name} cannot be negative")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "sources", ordered)

    @classmethod
    def build(
        cls,
        *,
        season: str,
        sources: Iterable[WorldSource],
        player_count: int,
        team_count: int,
        fixture_count: int,
        event_count: int,
    ) -> "GlobalWorld":
        return cls(
            season=season,
            sources=tuple(sources),
            player_count=int(player_count),
            team_count=int(team_count),
            fixture_count=int(fixture_count),
            event_count=int(event_count),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-global-world",
            "schema_version": self.schema_version,
            "season": self.season,
            "sources": [source.as_dict() for source in self.sources],
            "counts": {
                "players": self.player_count,
                "teams": self.team_count,
                "fixtures": self.fixture_count,
                "events": self.event_count,
            },
        }

    @property
    def world_id(self) -> GlobalWorldId:
        return GlobalWorldId(canonical_sha256(self.semantic_payload()))

    def as_dict(self) -> dict[str, object]:
        payload = self.semantic_payload()
        payload["global_world_id"] = str(self.world_id)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "GlobalWorld":
        if payload.get("schema_name") != "apex-global-world":
            raise ValueError("not an Apex GlobalWorld manifest")
        counts = payload.get("counts")
        if not isinstance(counts, dict):
            raise ValueError("GlobalWorld counts are missing")
        source_rows = payload.get("sources")
        if not isinstance(source_rows, list):
            raise ValueError("GlobalWorld sources are missing")
        world = cls(
            season=str(payload["season"]),
            sources=tuple(WorldSource.from_dict(dict(row)) for row in source_rows),
            player_count=int(counts["players"]),
            team_count=int(counts["teams"]),
            fixture_count=int(counts["fixtures"]),
            event_count=int(counts["events"]),
            schema_version=int(payload["schema_version"]),
        )
        declared = payload.get("global_world_id")
        if declared is not None and str(declared) != str(world.world_id):
            raise ValueError("GlobalWorld semantic identity mismatch")
        return world
