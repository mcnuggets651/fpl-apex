"""Content-bound authorization of one external reference-solver certificate."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from .canonical import canonical_sha256
from .ids import ReferenceSolverCertificateId, ReferenceSolverWorkerId


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


@dataclass(frozen=True, slots=True)
class ReferenceSolverAuthorization:
    """Proof that one solver certificate used the retained qualified champion registry."""

    solver_certificate_id: ReferenceSolverCertificateId
    worker_id: ReferenceSolverWorkerId
    worker_code_artifact_id: str
    qualification_artifact_id: str
    registry_artifact_id: str
    season: str
    decision_cutoff: str
    horizon_gameweeks: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ReferenceSolverAuthorization schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("reference solver authorization requires season")
        cutoff = _aware_iso(
            self.decision_cutoff,
            label="reference solver authorization decision_cutoff",
        )
        if (
            isinstance(self.horizon_gameweeks, bool)
            or not isinstance(self.horizon_gameweeks, int)
            or self.horizon_gameweeks <= 0
        ):
            raise ValueError("reference solver authorization horizon must be positive integer")
        code = _artifact_id(
            self.worker_code_artifact_id,
            label="reference solver authorization worker code artifact",
        )
        qualification = _artifact_id(
            self.qualification_artifact_id,
            label="reference solver authorization qualification artifact",
        )
        registry = _artifact_id(
            self.registry_artifact_id,
            label="reference solver authorization registry artifact",
        )
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "decision_cutoff", cutoff)
        object.__setattr__(self, "worker_code_artifact_id", code)
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "registry_artifact_id", registry)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-reference-solver-authorization",
            "schema_version": self.schema_version,
            "solver_certificate_id": str(self.solver_certificate_id),
            "worker_id": str(self.worker_id),
            "worker_code_artifact_id": self.worker_code_artifact_id,
            "qualification_artifact_id": self.qualification_artifact_id,
            "registry_artifact_id": self.registry_artifact_id,
            "season": self.season,
            "decision_cutoff": self.decision_cutoff,
            "horizon_gameweeks": self.horizon_gameweeks,
        }

    @property
    def authorization_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
