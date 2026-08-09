from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("replay timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class SourceManifestEntry:
    name: str
    revision: str
    content_sha256: str
    published_at: datetime
    available_at: datetime
    retrieved_at: datetime
    reference: str = ""

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("source name is required")
        digest = self.content_sha256.casefold()
        if not _SHA256.fullmatch(digest):
            raise ValueError(f"invalid SHA-256 for source {self.name}")
        object.__setattr__(self, "content_sha256", digest)
        for field in ("published_at", "available_at", "retrieved_at"):
            object.__setattr__(self, field, _utc(getattr(self, field)))
        if self.available_at < self.published_at:
            raise ValueError(f"source {self.name} is available before publication")
        if self.retrieved_at < self.available_at:
            raise ValueError(f"source {self.name} is retrieved before availability")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "revision": self.revision,
            "content_sha256": self.content_sha256,
            "published_at": self.published_at.isoformat(),
            "available_at": self.available_at.isoformat(),
            "retrieved_at": self.retrieved_at.isoformat(),
            "reference": self.reference,
        }


@dataclass(frozen=True)
class AsOfContext:
    season: str
    gameweek: int
    deadline_utc: datetime
    cutoff_utc: datetime
    code_sha: str
    config_sha256: str
    random_seed: int
    sources: tuple[SourceManifestEntry, ...]
    previous_decision_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "deadline_utc", _utc(self.deadline_utc))
        object.__setattr__(self, "cutoff_utc", _utc(self.cutoff_utc))
        if not 1 <= int(self.gameweek) <= 38:
            raise ValueError("gameweek must be between 1 and 38")
        if self.cutoff_utc >= self.deadline_utc:
            raise ValueError("replay cutoff must be strictly before the deadline")
        if not _SHA256.fullmatch(self.config_sha256.casefold()):
            raise ValueError("config_sha256 must be a SHA-256 digest")
        names = [source.name for source in self.sources]
        if len(names) != len(set(names)):
            raise ValueError("replay source names must be unique")
        future = [
            source.name
            for source in self.sources
            if source.available_at > self.cutoff_utc
        ]
        if future:
            raise ValueError(
                "future information crossed replay cutoff: " + ", ".join(sorted(future))
            )
        if self.previous_decision_sha256 is not None and not _SHA256.fullmatch(
            self.previous_decision_sha256.casefold()
        ):
            raise ValueError("previous_decision_sha256 must be a SHA-256 digest")

    def to_dict(self) -> dict:
        return {
            "season": self.season,
            "gameweek": int(self.gameweek),
            "deadline_utc": self.deadline_utc.isoformat(),
            "cutoff_utc": self.cutoff_utc.isoformat(),
            "code_sha": self.code_sha,
            "config_sha256": self.config_sha256.casefold(),
            "random_seed": int(self.random_seed),
            "previous_decision_sha256": self.previous_decision_sha256,
            "sources": [
                source.to_dict()
                for source in sorted(self.sources, key=lambda row: row.name)
            ],
        }

    @property
    def manifest_sha256(self) -> str:
        payload = json.dumps(
            self.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
