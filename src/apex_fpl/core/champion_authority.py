"""Immutable reviewed-admission and champion-generation contracts for Apex V2.

Empirical qualification proves that a candidate is eligible for consideration. It does
not itself authorize that candidate as the production champion. These contracts keep
that distinction explicit and content-addressed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .canonical import canonical_sha256


def _sha256_id(value: object, *, label: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def _text(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _aware_timestamp(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return text


class ChampionRole(StrEnum):
    DECISION_POLICY = "DECISION_POLICY"
    SCENARIO_GENERATOR = "SCENARIO_GENERATOR"
    SCENARIO_POLICY = "SCENARIO_POLICY"


@dataclass(frozen=True, slots=True)
class ChampionAdmissionCertificate:
    """Reviewed authority to admit one empirically-qualified non-model candidate.

    The candidate itself is a canonical semantic artifact whose SHA is ``candidate_id``.
    ``qualification_artifact_id`` proves empirical eligibility; ``review_artifact_id`` is
    distinct retained change-control evidence. No caller-authored ``approved`` boolean is
    accepted as authority.
    """

    role: ChampionRole
    season: str
    candidate_id: str
    qualification_artifact_id: str
    review_artifact_id: str
    reviewed_by: str
    reviewed_at: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ChampionAdmissionCertificate schema_version")
        if not isinstance(self.role, ChampionRole):
            raise ValueError("champion admission role must be typed")
        object.__setattr__(
            self,
            "season",
            _text(self.season, label="champion admission season"),
        )
        object.__setattr__(
            self,
            "candidate_id",
            _sha256_id(self.candidate_id, label="champion candidate"),
        )
        object.__setattr__(
            self,
            "qualification_artifact_id",
            _sha256_id(
                self.qualification_artifact_id,
                label="champion qualification artifact",
            ),
        )
        object.__setattr__(
            self,
            "review_artifact_id",
            _sha256_id(self.review_artifact_id, label="champion review artifact"),
        )
        object.__setattr__(
            self,
            "reviewed_by",
            _text(self.reviewed_by, label="champion reviewer"),
        )
        object.__setattr__(
            self,
            "reviewed_at",
            _aware_timestamp(self.reviewed_at, label="champion reviewed_at"),
        )
        object.__setattr__(
            self,
            "reason",
            _text(self.reason, label="champion admission reason"),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-champion-admission-certificate",
            "schema_version": self.schema_version,
            "role": self.role.value,
            "season": self.season,
            "candidate_id": self.candidate_id,
            "qualification_artifact_id": self.qualification_artifact_id,
            "review_artifact_id": self.review_artifact_id,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "reason": self.reason,
        }

    @property
    def admission_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ProductionChampionGeneration:
    """One immutable, parent-linked production champion selection generation."""

    season: str
    generation: int
    parent_generation_artifact_id: str | None
    forecast_registry_generation_artifact_id: str
    forecast_model_id: str
    decision_policy_admission_artifact_id: str
    decision_policy_id: str
    scenario_generator_admission_artifact_id: str
    scenario_generator_id: str
    scenario_policy_admission_artifact_id: str
    scenario_policy_id: str
    change_control_artifact_id: str
    authorized_by: str
    authorized_at: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProductionChampionGeneration schema_version")
        season = _text(self.season, label="champion generation season")
        if (
            isinstance(self.generation, bool)
            or not isinstance(self.generation, int)
            or self.generation <= 0
        ):
            raise ValueError("champion generation must be positive integer")
        parent = self.parent_generation_artifact_id
        if self.generation == 1 and parent is not None:
            raise ValueError("first champion generation cannot have a parent")
        if self.generation > 1 and parent is None:
            raise ValueError("later champion generation requires parent artifact")
        if parent is not None:
            parent = _sha256_id(parent, label="champion parent generation artifact")
        artifact_fields = (
            "forecast_registry_generation_artifact_id",
            "decision_policy_admission_artifact_id",
            "scenario_generator_admission_artifact_id",
            "scenario_policy_admission_artifact_id",
            "change_control_artifact_id",
        )
        id_fields = (
            "forecast_model_id",
            "decision_policy_id",
            "scenario_generator_id",
            "scenario_policy_id",
        )
        for field in artifact_fields:
            object.__setattr__(
                self,
                field,
                _sha256_id(
                    getattr(self, field),
                    label=f"champion generation {field}",
                ),
            )
        for field in id_fields:
            object.__setattr__(
                self,
                field,
                _sha256_id(
                    getattr(self, field),
                    label=f"champion generation {field}",
                ),
            )
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "parent_generation_artifact_id", parent)
        object.__setattr__(
            self,
            "authorized_by",
            _text(self.authorized_by, label="champion generation authorizer"),
        )
        object.__setattr__(
            self,
            "authorized_at",
            _aware_timestamp(
                self.authorized_at,
                label="champion generation authorized_at",
            ),
        )
        object.__setattr__(
            self,
            "reason",
            _text(self.reason, label="champion generation reason"),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-champion-generation",
            "schema_version": self.schema_version,
            "season": self.season,
            "generation": self.generation,
            "parent_generation_artifact_id": self.parent_generation_artifact_id,
            "forecast_registry_generation_artifact_id": (
                self.forecast_registry_generation_artifact_id
            ),
            "forecast_model_id": self.forecast_model_id,
            "decision_policy_admission_artifact_id": (
                self.decision_policy_admission_artifact_id
            ),
            "decision_policy_id": self.decision_policy_id,
            "scenario_generator_admission_artifact_id": (
                self.scenario_generator_admission_artifact_id
            ),
            "scenario_generator_id": self.scenario_generator_id,
            "scenario_policy_admission_artifact_id": (
                self.scenario_policy_admission_artifact_id
            ),
            "scenario_policy_id": self.scenario_policy_id,
            "change_control_artifact_id": self.change_control_artifact_id,
            "authorized_by": self.authorized_by,
            "authorized_at": self.authorized_at,
            "reason": self.reason,
        }

    @property
    def generation_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
