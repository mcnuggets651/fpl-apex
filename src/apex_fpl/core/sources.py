"""Dependency-free source governance contracts for Apex V2.

Source health is intentionally multidimensional. A source can be reachable but stale,
well formed but semantically invalid, or healthy for one capability while irrelevant to
another. No single boolean is allowed to erase those distinctions.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from .canonical import canonical_sha256


class SourceCriticality(str, Enum):
    HARD_REQUIRED = "HARD_REQUIRED"
    MODEL_REQUIRED = "MODEL_REQUIRED"
    QUALITY_REQUIRED = "QUALITY_REQUIRED"
    OPTIONAL = "OPTIONAL"
    ADVISORY = "ADVISORY"


class SourceAdmissionState(str, Enum):
    SHADOW = "SHADOW"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"
    RETIRED = "RETIRED"


class HealthState(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True, slots=True)
class SourceHealth:
    availability: HealthState
    freshness: HealthState
    coverage: HealthState
    integrity: HealthState
    schema_validity: HealthState
    semantic_validity: HealthState
    identity_validity: HealthState
    reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        reasons = tuple(sorted({str(item).strip() for item in self.reasons if str(item).strip()}))
        object.__setattr__(self, "reasons", reasons)

    def dimensions(self) -> Mapping[str, HealthState]:
        return {
            "availability": self.availability,
            "freshness": self.freshness,
            "coverage": self.coverage,
            "integrity": self.integrity,
            "schema_validity": self.schema_validity,
            "semantic_validity": self.semantic_validity,
            "identity_validity": self.identity_validity,
        }

    def failed_dimensions(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, state in self.dimensions().items()
            if state is HealthState.FAIL
        )

    def unknown_dimensions(self) -> tuple[str, ...]:
        return tuple(
            name
            for name, state in self.dimensions().items()
            if state is HealthState.UNKNOWN
        )

    def all_required_dimensions_pass(self) -> bool:
        return all(
            state in {HealthState.PASS, HealthState.NOT_APPLICABLE}
            for state in self.dimensions().values()
        )


@dataclass(frozen=True, slots=True)
class SourceCapability:
    source_id: str
    capability: str
    criticality: SourceCriticality
    admission_state: SourceAdmissionState
    adapter_schema: str
    adapter_version: str
    retention_understood: bool
    licensing_understood: bool
    failure_semantics: str
    reliability_rationale: str

    def __post_init__(self) -> None:
        for label in (
            "source_id",
            "capability",
            "adapter_schema",
            "adapter_version",
            "failure_semantics",
            "reliability_rationale",
        ):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"{label} cannot be empty")
            object.__setattr__(self, label, value)
        if self.admission_state is SourceAdmissionState.QUALIFIED:
            if not self.retention_understood or not self.licensing_understood:
                raise ValueError(
                    "qualified source capability requires understood retention and licensing"
                )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "capability": self.capability,
            "criticality": self.criticality.value,
            "admission_state": self.admission_state.value,
            "adapter_schema": self.adapter_schema,
            "adapter_version": self.adapter_version,
            "retention_understood": self.retention_understood,
            "licensing_understood": self.licensing_understood,
            "failure_semantics": self.failure_semantics,
            "reliability_rationale": self.reliability_rationale,
        }

    @property
    def capability_id(self) -> str:
        return canonical_sha256(
            {
                "schema_name": "apex-source-capability",
                "schema_version": 1,
                **self.semantic_payload(),
            }
        )


class DegradationDecision(str, Enum):
    NORMAL = "NORMAL"
    QUALIFIED_DEGRADED = "QUALIFIED_DEGRADED"
    BLOCKED = "BLOCKED"
    OBSERVE_ONLY = "OBSERVE_ONLY"


@dataclass(frozen=True, slots=True)
class DegradationProfile:
    profile_id: str
    capability: str
    qualified: bool
    registered: bool
    validation_artifact_id: str

    def __post_init__(self) -> None:
        for label in ("profile_id", "capability", "validation_artifact_id"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"{label} cannot be empty")
            object.__setattr__(self, label, value)
        algorithm, separator, digest = self.validation_artifact_id.partition(":")
        if algorithm != "sha256" or not separator or len(digest) != 64:
            raise ValueError("degradation validation artifact must be sha256 content identity")
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError("degradation validation artifact digest is invalid") from exc

    @property
    def usable(self) -> bool:
        return self.qualified and self.registered


def evaluate_source_runtime(
    capability: SourceCapability,
    health: SourceHealth,
    *,
    degradation: DegradationProfile | None = None,
) -> DegradationDecision:
    """Apply fail-closed source criticality without collapsing health to one boolean."""

    if capability.admission_state in {
        SourceAdmissionState.SUSPENDED,
        SourceAdmissionState.RETIRED,
    }:
        return DegradationDecision.BLOCKED
    if capability.admission_state is SourceAdmissionState.SHADOW:
        return DegradationDecision.OBSERVE_ONLY
    if health.all_required_dimensions_pass():
        return DegradationDecision.NORMAL
    if capability.criticality is SourceCriticality.HARD_REQUIRED:
        return DegradationDecision.BLOCKED
    if capability.criticality is SourceCriticality.MODEL_REQUIRED:
        if degradation is not None and degradation.capability == capability.capability and degradation.usable:
            return DegradationDecision.QUALIFIED_DEGRADED
        return DegradationDecision.BLOCKED
    if capability.criticality is SourceCriticality.QUALITY_REQUIRED:
        if degradation is not None and degradation.capability == capability.capability and degradation.usable:
            return DegradationDecision.QUALIFIED_DEGRADED
        return DegradationDecision.BLOCKED
    return DegradationDecision.OBSERVE_ONLY
