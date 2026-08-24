"""Qualified external reference-solver worker contract for Apex V2 Slice 10."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum

from .canonical import canonical_sha256
from .ids import ReferenceSolverWorkerId


def _artifact_id(value: str, *, label: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def _aware_iso(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _point(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ReferenceSolverWorkerQualification(StrEnum):
    SHADOW = "SHADOW"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


@dataclass(frozen=True, slots=True)
class ReferenceSolverWorkerArtifact:
    worker_name: str
    worker_version: str
    solver_contract: str
    code_artifact_id: str
    qualification_state: ReferenceSolverWorkerQualification
    qualification_artifact_id: str | None
    valid_seasons: tuple[str, ...]
    first_available_at: str
    max_horizon_gameweeks: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ReferenceSolverWorkerArtifact schema_version")
        for label in ("worker_name", "worker_version", "solver_contract"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"reference solver {label} cannot be empty")
            object.__setattr__(self, label, value)
        code = _artifact_id(self.code_artifact_id, label="reference solver code artifact")
        qualification = self.qualification_artifact_id
        if qualification is not None:
            qualification = _artifact_id(
                qualification,
                label="reference solver qualification artifact",
            )
        if (
            self.qualification_state is ReferenceSolverWorkerQualification.QUALIFIED
            and qualification is None
        ):
            raise ValueError("qualified reference solver worker requires qualification artifact")
        seasons = tuple(sorted({str(item).strip() for item in self.valid_seasons if str(item).strip()}))
        if not seasons:
            raise ValueError("reference solver worker requires valid seasons")
        if (
            isinstance(self.max_horizon_gameweeks, bool)
            or not isinstance(self.max_horizon_gameweeks, int)
            or self.max_horizon_gameweeks <= 0
        ):
            raise ValueError("reference solver max_horizon_gameweeks must be positive integer")
        available = _aware_iso(
            self.first_available_at,
            label="reference solver first_available_at",
        )
        object.__setattr__(self, "code_artifact_id", code)
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "valid_seasons", seasons)
        object.__setattr__(self, "first_available_at", available)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-reference-solver-worker",
            "schema_version": self.schema_version,
            "worker_name": self.worker_name,
            "worker_version": self.worker_version,
            "solver_contract": self.solver_contract,
            "code_artifact_id": self.code_artifact_id,
            "qualification_state": self.qualification_state.value,
            "qualification_artifact_id": self.qualification_artifact_id,
            "valid_seasons": list(self.valid_seasons),
            "first_available_at": self.first_available_at,
            "max_horizon_gameweeks": self.max_horizon_gameweeks,
        }

    @property
    def worker_id(self) -> ReferenceSolverWorkerId:
        return ReferenceSolverWorkerId(canonical_sha256(self.semantic_payload()))

    @property
    def production_qualified(self) -> bool:
        return (
            self.qualification_state is ReferenceSolverWorkerQualification.QUALIFIED
            and self.qualification_artifact_id is not None
        )

    def require_available_for(
        self,
        *,
        season: str,
        cutoff: str,
        horizon_gameweeks: int,
        production: bool,
    ) -> None:
        point = _aware_iso(cutoff, label="reference solver cutoff")
        if season not in self.valid_seasons:
            raise ValueError(f"reference solver worker is not valid for season {season}")
        if (
            isinstance(horizon_gameweeks, bool)
            or not isinstance(horizon_gameweeks, int)
            or horizon_gameweeks <= 0
            or horizon_gameweeks > self.max_horizon_gameweeks
        ):
            raise ValueError("reference solver horizon lies outside worker validity scope")
        if _point(self.first_available_at) > _point(point):
            raise ValueError("reference solver worker was not available at decision cutoff")
        if self.qualification_state is ReferenceSolverWorkerQualification.SUSPENDED:
            raise ValueError("reference solver worker is suspended")
        if production and not self.production_qualified:
            raise ValueError("production solver parity requires qualified reference worker")
