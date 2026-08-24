"""Deadline-relative source freshness contracts.

The policy contains no wall-clock reads. Callers provide source age and distance to the
relevant deadline explicitly, which keeps production and replay semantics identical.
"""

from __future__ import annotations

from dataclasses import dataclass

from .canonical import canonical_sha256


@dataclass(frozen=True, slots=True)
class FreshnessBand:
    max_seconds_to_deadline: int | None
    max_source_age_seconds: int
    rationale: str

    def __post_init__(self) -> None:
        if self.max_seconds_to_deadline is not None and (
            isinstance(self.max_seconds_to_deadline, bool)
            or not isinstance(self.max_seconds_to_deadline, int)
            or self.max_seconds_to_deadline < 0
        ):
            raise ValueError("max_seconds_to_deadline must be nonnegative integer or None")
        if (
            isinstance(self.max_source_age_seconds, bool)
            or not isinstance(self.max_source_age_seconds, int)
            or self.max_source_age_seconds < 0
        ):
            raise ValueError("max_source_age_seconds must be a nonnegative integer")
        rationale = str(self.rationale).strip()
        if not rationale:
            raise ValueError("freshness band requires an operational or empirical rationale")
        object.__setattr__(self, "rationale", rationale)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "max_seconds_to_deadline": self.max_seconds_to_deadline,
            "max_source_age_seconds": self.max_source_age_seconds,
            "rationale": self.rationale,
        }


@dataclass(frozen=True, slots=True)
class DeadlineFreshnessPolicy:
    policy_id: str
    capability: str
    bands: tuple[FreshnessBand, ...]
    qualification_artifact_id: str | None = None

    def __post_init__(self) -> None:
        policy_id = str(self.policy_id).strip()
        capability = str(self.capability).strip()
        if not policy_id or not capability:
            raise ValueError("freshness policy_id and capability cannot be empty")
        bands = tuple(self.bands)
        if not bands:
            raise ValueError("freshness policy requires at least one band")
        bounded = [band.max_seconds_to_deadline for band in bands if band.max_seconds_to_deadline is not None]
        if bounded != sorted(bounded):
            raise ValueError("freshness bands must be ordered from nearest to farthest deadline")
        if len(bounded) != len(set(bounded)):
            raise ValueError("freshness deadline bands cannot duplicate boundaries")
        if sum(band.max_seconds_to_deadline is None for band in bands) != 1:
            raise ValueError("freshness policy requires exactly one far-from-deadline catch-all band")
        if bands[-1].max_seconds_to_deadline is not None:
            raise ValueError("freshness catch-all band must be last")
        if self.qualification_artifact_id is not None:
            algorithm, separator, digest = self.qualification_artifact_id.partition(":")
            if algorithm != "sha256" or not separator or len(digest) != 64:
                raise ValueError("freshness qualification artifact must be sha256 content identity")
            try:
                int(digest, 16)
            except ValueError as exc:
                raise ValueError("freshness qualification artifact digest is invalid") from exc
        object.__setattr__(self, "policy_id", policy_id)
        object.__setattr__(self, "capability", capability)
        object.__setattr__(self, "bands", bands)

    @property
    def semantic_id(self) -> str:
        return canonical_sha256(
            {
                "schema_name": "apex-deadline-freshness-policy",
                "schema_version": 1,
                "policy_id": self.policy_id,
                "capability": self.capability,
                "bands": [band.semantic_payload() for band in self.bands],
                "qualification_artifact_id": self.qualification_artifact_id,
            }
        )

    def allowed_age_seconds(self, *, seconds_to_deadline: int) -> int:
        if (
            isinstance(seconds_to_deadline, bool)
            or not isinstance(seconds_to_deadline, int)
            or seconds_to_deadline < 0
        ):
            raise ValueError("seconds_to_deadline must be a nonnegative integer")
        for band in self.bands:
            boundary = band.max_seconds_to_deadline
            if boundary is None or seconds_to_deadline <= boundary:
                return band.max_source_age_seconds
        raise AssertionError("freshness policy missing catch-all band")

    def is_fresh(self, *, source_age_seconds: int, seconds_to_deadline: int) -> bool:
        if (
            isinstance(source_age_seconds, bool)
            or not isinstance(source_age_seconds, int)
            or source_age_seconds < 0
        ):
            raise ValueError("source_age_seconds must be a nonnegative integer")
        return source_age_seconds <= self.allowed_age_seconds(
            seconds_to_deadline=seconds_to_deadline
        )
