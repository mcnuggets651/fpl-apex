"""Contextual evidence reliability without fabricated defaults.

Reliability is learned for a source x claim-type x horizon x recency context.  An
unqualified context remains explicitly UNKNOWN and has no numeric coefficient.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .canonical import canonical_sha256


class ReliabilityQualification(str, Enum):
    UNKNOWN = "UNKNOWN"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError("reliability qualification artifact must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError("reliability qualification artifact digest is invalid") from exc
    return text


@dataclass(frozen=True, slots=True)
class ReliabilityContext:
    source_id: str
    claim_type: str
    horizon_gameweeks: int
    recency_bucket: str
    qualification: ReliabilityQualification
    reliability_bps: int | None = None
    sample_count: int = 0
    qualification_artifact_id: str | None = None

    def __post_init__(self) -> None:
        source_id = str(self.source_id).strip()
        claim_type = str(self.claim_type).strip()
        recency_bucket = str(self.recency_bucket).strip()
        if not source_id or not claim_type or not recency_bucket:
            raise ValueError("reliability source, claim type and recency bucket cannot be empty")
        if (
            isinstance(self.horizon_gameweeks, bool)
            or not isinstance(self.horizon_gameweeks, int)
            or self.horizon_gameweeks <= 0
        ):
            raise ValueError("horizon_gameweeks must be a positive integer")
        if (
            isinstance(self.sample_count, bool)
            or not isinstance(self.sample_count, int)
            or self.sample_count < 0
        ):
            raise ValueError("sample_count must be a nonnegative integer")
        artifact = self.qualification_artifact_id
        if self.qualification is ReliabilityQualification.QUALIFIED:
            if (
                isinstance(self.reliability_bps, bool)
                or not isinstance(self.reliability_bps, int)
                or not 0 <= self.reliability_bps <= 10_000
            ):
                raise ValueError("qualified reliability requires integer basis points in [0, 10000]")
            if self.sample_count <= 0:
                raise ValueError("qualified reliability requires non-zero calibration sample")
            if artifact is None:
                raise ValueError("qualified reliability requires qualification artifact")
            artifact = _artifact_id(artifact)
        else:
            if self.reliability_bps is not None:
                raise ValueError("unqualified reliability cannot carry a numeric coefficient")
            if artifact is not None:
                artifact = _artifact_id(artifact)
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "claim_type", claim_type)
        object.__setattr__(self, "recency_bucket", recency_bucket)
        object.__setattr__(self, "qualification_artifact_id", artifact)

    @property
    def usable_for_weighting(self) -> bool:
        return self.qualification is ReliabilityQualification.QUALIFIED

    def semantic_payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "claim_type": self.claim_type,
            "horizon_gameweeks": self.horizon_gameweeks,
            "recency_bucket": self.recency_bucket,
            "qualification": self.qualification.value,
            "reliability_bps": self.reliability_bps,
            "sample_count": self.sample_count,
            "qualification_artifact_id": self.qualification_artifact_id,
        }

    @property
    def context_id(self) -> str:
        return canonical_sha256(
            {
                "schema_name": "apex-reliability-context",
                "schema_version": 1,
                **self.semantic_payload(),
            }
        )
