"""Season-level immutable trust root for Apex V2 production authority.

The root does not replace component governance. It binds the exact retained artifacts
whose own loaders independently re-prove champion selection, FPL rules, learning policy,
outcome truth and build provenance. Release-specific solver authorization remains in the
release manifest/proof surface. Roots are parent-linked; a dedicated CAS registry selects
the unique current root for a season.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .canonical import canonical_sha256


def _text(value: object, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _sha256_id(value: object, *, label: str) -> str:
    text = _text(value, label=label)
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def _aware_datetime(value: object, *, label: str) -> datetime:
    text = _text(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed


def _aware_timestamp(value: object, *, label: str) -> str:
    _aware_datetime(value, label=label)
    return _text(value, label=label)


@dataclass(frozen=True, slots=True)
class ProductionAuthorityRoot:
    """Parent-linked, review-bound season authority selected by a dedicated CAS pointer."""

    season: str
    generation: int
    parent_root_artifact_id: str | None
    champion_generation_artifact_id: str
    ruleset_artifact_id: str
    ruleset_id: str
    learning_policy_registry_artifact_id: str
    learning_policy_id: str
    outcome_truth_registry_artifact_id: str
    outcome_truth_registry_id: str
    build_manifest_artifact_id: str
    build_manifest_id: str
    change_control_artifact_id: str
    authorized_by: str
    authorized_at: str
    valid_from: str
    valid_until: str
    reason: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ProductionAuthorityRoot schema_version")
        object.__setattr__(self, "season", _text(self.season, label="authority root season"))
        if isinstance(self.generation, bool) or not isinstance(self.generation, int) or self.generation <= 0:
            raise ValueError("authority root generation must be positive integer")
        parent = self.parent_root_artifact_id
        if self.generation == 1 and parent is not None:
            raise ValueError("first authority root cannot have parent")
        if self.generation > 1 and parent is None:
            raise ValueError("later authority root requires parent")
        if parent is not None:
            object.__setattr__(
                self,
                "parent_root_artifact_id",
                _sha256_id(parent, label="authority root parent"),
            )
        for field in (
            "champion_generation_artifact_id",
            "ruleset_artifact_id",
            "ruleset_id",
            "learning_policy_registry_artifact_id",
            "learning_policy_id",
            "outcome_truth_registry_artifact_id",
            "outcome_truth_registry_id",
            "build_manifest_artifact_id",
            "build_manifest_id",
            "change_control_artifact_id",
        ):
            object.__setattr__(
                self,
                field,
                _sha256_id(getattr(self, field), label=f"authority root {field}"),
            )
        object.__setattr__(
            self,
            "authorized_by",
            _text(self.authorized_by, label="authority root authorizer"),
        )
        authorized_at = _aware_datetime(self.authorized_at, label="authority root authorized_at")
        valid_from = _aware_datetime(self.valid_from, label="authority root valid_from")
        valid_until = _aware_datetime(self.valid_until, label="authority root valid_until")
        if authorized_at > valid_from:
            raise ValueError("authority root cannot become valid before authorization")
        if valid_until <= valid_from:
            raise ValueError("authority root valid_until must be after valid_from")
        object.__setattr__(
            self,
            "authorized_at",
            _aware_timestamp(self.authorized_at, label="authority root authorized_at"),
        )
        object.__setattr__(
            self,
            "valid_from",
            _aware_timestamp(self.valid_from, label="authority root valid_from"),
        )
        object.__setattr__(
            self,
            "valid_until",
            _aware_timestamp(self.valid_until, label="authority root valid_until"),
        )
        object.__setattr__(self, "reason", _text(self.reason, label="authority root reason"))

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-production-authority-root",
            "schema_version": self.schema_version,
            "season": self.season,
            "generation": self.generation,
            "parent_root_artifact_id": self.parent_root_artifact_id,
            "champion_generation_artifact_id": self.champion_generation_artifact_id,
            "ruleset_artifact_id": self.ruleset_artifact_id,
            "ruleset_id": self.ruleset_id,
            "learning_policy_registry_artifact_id": self.learning_policy_registry_artifact_id,
            "learning_policy_id": self.learning_policy_id,
            "outcome_truth_registry_artifact_id": self.outcome_truth_registry_artifact_id,
            "outcome_truth_registry_id": self.outcome_truth_registry_id,
            "build_manifest_artifact_id": self.build_manifest_artifact_id,
            "build_manifest_id": self.build_manifest_id,
            "change_control_artifact_id": self.change_control_artifact_id,
            "authorized_by": self.authorized_by,
            "authorized_at": self.authorized_at,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "reason": self.reason,
        }

    @property
    def root_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    def require_valid_at(self, as_of: str) -> None:
        """Fail closed outside the half-open authority window ``[valid_from, valid_until)``."""

        instant = _aware_datetime(as_of, label="authority root as_of")
        if instant < _aware_datetime(self.valid_from, label="authority root valid_from"):
            raise ValueError("production authority root is not yet valid")
        if instant >= _aware_datetime(self.valid_until, label="authority root valid_until"):
            raise ValueError("production authority root has expired")
