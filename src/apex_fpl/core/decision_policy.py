"""Versioned DecisionPolicy for Apex V2 optimisation.

A tactical one-Gameweek EV solve is useful for reference/shadow analysis, but it cannot
become the production policy for persistent transfers or long-lived chips. Production
policy must explicitly account for horizon/continuation, chip option value, price policy
and candidate-universe policy, and must be empirically qualified before use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .canonical import canonical_sha256
from .ids import DecisionPolicyId


TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID = "lexicographic-official-id-v1"


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


def _artifact_id(value: str | None, *, label: str, required: bool = False) -> str | None:
    if value is None:
        if required:
            raise ValueError(f"{label} is required")
        return None
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


class DecisionPolicyQualificationState(str, Enum):
    SHADOW = "SHADOW"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


class DecisionEvaluationMode(str, Enum):
    TACTICAL_CURRENT_GAMEWEEK = "TACTICAL_CURRENT_GAMEWEEK"
    RECEDING_HORIZON_WITH_CONTINUATION = "RECEDING_HORIZON_WITH_CONTINUATION"


class DecisionObjectivePolicy(str, Enum):
    MAX_EXPECTED_FPL_POINTS_OVER_TIME = "MAX_EXPECTED_FPL_POINTS_OVER_TIME"


@dataclass(frozen=True, slots=True)
class DecisionPolicy:
    policy_name: str
    policy_version: str
    season: str
    qualification_state: DecisionPolicyQualificationState
    qualification_artifact_id: str | None
    first_available_at: str
    evaluation_mode: DecisionEvaluationMode
    objective_policy: DecisionObjectivePolicy
    horizon_gameweeks: int
    continuation_value_artifact_id: str | None
    chip_option_value_artifact_id: str | None
    price_policy_artifact_id: str | None
    candidate_policy_artifact_id: str | None
    tie_break_policy: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported DecisionPolicy schema_version")
        for label in ("policy_name", "policy_version", "season", "tie_break_policy"):
            value = str(getattr(self, label)).strip()
            if not value:
                raise ValueError(f"DecisionPolicy {label} cannot be empty")
            object.__setattr__(self, label, value)
        if (
            isinstance(self.horizon_gameweeks, bool)
            or not isinstance(self.horizon_gameweeks, int)
            or self.horizon_gameweeks <= 0
        ):
            raise ValueError("DecisionPolicy horizon_gameweeks must be positive integer")
        if self.evaluation_mode is DecisionEvaluationMode.TACTICAL_CURRENT_GAMEWEEK:
            if self.horizon_gameweeks != 1:
                raise ValueError("tactical DecisionPolicy requires horizon_gameweeks == 1")
            if self.tie_break_policy != TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID:
                raise ValueError(
                    "tactical DecisionPolicy requests unimplemented tie-break semantics: "
                    f"{self.tie_break_policy!r}"
                )
            unused = {
                "continuation-value": self.continuation_value_artifact_id,
                "chip-option-value": self.chip_option_value_artifact_id,
                "price-policy": self.price_policy_artifact_id,
                "candidate-policy": self.candidate_policy_artifact_id,
            }
            present = sorted(label for label, value in unused.items() if value is not None)
            if present:
                raise ValueError(
                    "tactical DecisionPolicy cannot declare unused policy artifacts: "
                    + ", ".join(present)
                )
        available = _aware_iso(self.first_available_at, label="DecisionPolicy first_available_at")
        qualification = _artifact_id(
            self.qualification_artifact_id,
            label="DecisionPolicy qualification artifact",
            required=self.qualification_state is DecisionPolicyQualificationState.QUALIFIED,
        )
        continuation = _artifact_id(
            self.continuation_value_artifact_id,
            label="DecisionPolicy continuation-value artifact",
        )
        chip_option = _artifact_id(
            self.chip_option_value_artifact_id,
            label="DecisionPolicy chip-option artifact",
        )
        price = _artifact_id(
            self.price_policy_artifact_id,
            label="DecisionPolicy price-policy artifact",
        )
        candidate = _artifact_id(
            self.candidate_policy_artifact_id,
            label="DecisionPolicy candidate-policy artifact",
        )
        if self.evaluation_mode is DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION:
            if self.horizon_gameweeks < 2:
                raise ValueError("receding-horizon DecisionPolicy requires horizon >= 2")
            if continuation is None:
                raise ValueError("receding-horizon DecisionPolicy requires continuation-value artifact")
            if chip_option is None:
                raise ValueError("receding-horizon DecisionPolicy requires chip-option-value artifact")
        object.__setattr__(self, "qualification_artifact_id", qualification)
        object.__setattr__(self, "continuation_value_artifact_id", continuation)
        object.__setattr__(self, "chip_option_value_artifact_id", chip_option)
        object.__setattr__(self, "price_policy_artifact_id", price)
        object.__setattr__(self, "candidate_policy_artifact_id", candidate)
        object.__setattr__(self, "first_available_at", available)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-policy",
            "schema_version": self.schema_version,
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "season": self.season,
            "qualification_state": self.qualification_state.value,
            "qualification_artifact_id": self.qualification_artifact_id,
            "first_available_at": self.first_available_at,
            "evaluation_mode": self.evaluation_mode.value,
            "objective_policy": self.objective_policy.value,
            "horizon_gameweeks": self.horizon_gameweeks,
            "continuation_value_artifact_id": self.continuation_value_artifact_id,
            "chip_option_value_artifact_id": self.chip_option_value_artifact_id,
            "price_policy_artifact_id": self.price_policy_artifact_id,
            "candidate_policy_artifact_id": self.candidate_policy_artifact_id,
            "tie_break_policy": self.tie_break_policy,
        }

    @property
    def decision_policy_id(self) -> DecisionPolicyId:
        return DecisionPolicyId(canonical_sha256(self.semantic_payload()))

    @property
    def production_qualified(self) -> bool:
        return (
            self.qualification_state is DecisionPolicyQualificationState.QUALIFIED
            and self.evaluation_mode is DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION
            and self.continuation_value_artifact_id is not None
            and self.chip_option_value_artifact_id is not None
            and self.price_policy_artifact_id is not None
            and self.candidate_policy_artifact_id is not None
        )

    def require_available_for(self, *, season: str, decision_cutoff: str) -> None:
        cutoff = _aware_iso(decision_cutoff, label="DecisionPolicy decision_cutoff")
        if season != self.season:
            raise ValueError(f"DecisionPolicy is not valid for season {season}")
        available = datetime.fromisoformat(self.first_available_at.replace("Z", "+00:00"))
        point = datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
        if available > point:
            raise ValueError("DecisionPolicy was not available at the decision cutoff")
        if self.qualification_state is DecisionPolicyQualificationState.SUSPENDED:
            raise ValueError("DecisionPolicy is suspended")
