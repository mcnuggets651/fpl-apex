"""Dependency-free typed support contracts for V2 receding-horizon DecisionPolicy.

Opaque artifact bytes are not policy semantics. These contracts make continuation,
chip-option, price and candidate policy inputs immutable, content-addressed and
replayable before empirical qualification can authorize a production DecisionPolicy.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from math import gcd

from .canonical import canonical_sha256


class ContinuationValueMode(StrEnum):
    EXACT_GAMEWEEK_WEIGHTS_ZERO_TERMINAL = "EXACT_GAMEWEEK_WEIGHTS_ZERO_TERMINAL"


class ChipOptionValueMode(StrEnum):
    EXACT_TERMINAL_RESERVE = "EXACT_TERMINAL_RESERVE"


class PricePolicyMode(StrEnum):
    OFFICIAL_CURRENT_ONLY = "OFFICIAL_CURRENT_ONLY"


class CandidatePolicyMode(StrEnum):
    FULL_OFFICIAL = "FULL_OFFICIAL"


def _nonempty(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _aware_iso(value: str, *, label: str) -> str:
    text = _nonempty(value, label=label)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


@dataclass(frozen=True, slots=True)
class ExactPolicyValue:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise ValueError("policy value numerator must be integer")
        if (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, int)
            or self.denominator <= 0
        ):
            raise ValueError("policy value denominator must be positive integer")
        divisor = gcd(abs(self.numerator), self.denominator)
        object.__setattr__(self, "numerator", self.numerator // divisor)
        object.__setattr__(self, "denominator", self.denominator // divisor)

    @classmethod
    def zero(cls) -> "ExactPolicyValue":
        return cls(0, 1)

    @classmethod
    def one(cls) -> "ExactPolicyValue":
        return cls(1, 1)

    @property
    def nonnegative(self) -> bool:
        return self.numerator >= 0

    @property
    def positive(self) -> bool:
        return self.numerator > 0

    def semantic_payload(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


@dataclass(frozen=True, slots=True)
class ContinuationValuePolicy:
    season: str
    horizon_gameweeks: int
    first_available_at: str
    gameweek_weights: tuple[ExactPolicyValue, ...]
    terminal_value: ExactPolicyValue = ExactPolicyValue.zero()
    mode: ContinuationValueMode = ContinuationValueMode.EXACT_GAMEWEEK_WEIGHTS_ZERO_TERMINAL
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported continuation-value policy schema_version")
        season = _nonempty(self.season, label="continuation-value season")
        horizon = _positive_int(self.horizon_gameweeks, label="continuation-value horizon")
        if horizon < 2:
            raise ValueError("continuation-value horizon must be at least two Gameweeks")
        if self.mode is not ContinuationValueMode.EXACT_GAMEWEEK_WEIGHTS_ZERO_TERMINAL:
            raise ValueError("unsupported continuation-value mode")
        weights = tuple(self.gameweek_weights)
        if len(weights) != horizon or any(not isinstance(row, ExactPolicyValue) for row in weights):
            raise ValueError("continuation-value weights must exactly cover the declared horizon")
        if weights[0] != ExactPolicyValue.one():
            raise ValueError("continuation-value current-Gameweek weight must equal exactly one")
        if any(not row.nonnegative for row in weights):
            raise ValueError("continuation-value weights cannot be negative")
        if not any(row.positive for row in weights[1:]):
            raise ValueError("receding-horizon continuation must assign positive future value")
        if self.terminal_value != ExactPolicyValue.zero():
            raise ValueError("continuation-value v1 requires an exact zero terminal value")
        object.__setattr__(self, "season", season)
        object.__setattr__(
            self,
            "first_available_at",
            _aware_iso(self.first_available_at, label="continuation-value first_available_at"),
        )
        object.__setattr__(self, "gameweek_weights", weights)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-continuation-value-policy",
            "schema_version": self.schema_version,
            "season": self.season,
            "horizon_gameweeks": self.horizon_gameweeks,
            "first_available_at": self.first_available_at,
            "mode": self.mode.value,
            "gameweek_weights": [row.semantic_payload() for row in self.gameweek_weights],
            "terminal_value": self.terminal_value.semantic_payload(),
        }

    @property
    def policy_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


_CHIPS = ("BENCH_BOOST", "FREE_HIT", "TRIPLE_CAPTAIN", "WILDCARD")


@dataclass(frozen=True, slots=True)
class ChipOptionValuePolicy:
    season: str
    horizon_gameweeks: int
    first_available_at: str
    option_values: tuple[tuple[str, ExactPolicyValue], ...]
    mode: ChipOptionValueMode = ChipOptionValueMode.EXACT_TERMINAL_RESERVE
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported chip-option policy schema_version")
        season = _nonempty(self.season, label="chip-option season")
        horizon = _positive_int(self.horizon_gameweeks, label="chip-option horizon")
        if horizon < 2:
            raise ValueError("chip-option horizon must be at least two Gameweeks")
        if self.mode is not ChipOptionValueMode.EXACT_TERMINAL_RESERVE:
            raise ValueError("unsupported chip-option mode")
        rows = tuple(sorted(self.option_values, key=lambda item: item[0]))
        if tuple(name for name, _ in rows) != _CHIPS:
            raise ValueError("chip-option policy must explicitly value all four FPL chips once")
        if any(not isinstance(value, ExactPolicyValue) for _, value in rows):
            raise ValueError("chip-option values must be exact rationals")
        if any(not value.nonnegative for _, value in rows):
            raise ValueError("chip-option values cannot be negative")
        object.__setattr__(self, "season", season)
        object.__setattr__(
            self,
            "first_available_at",
            _aware_iso(self.first_available_at, label="chip-option first_available_at"),
        )
        object.__setattr__(self, "option_values", rows)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-chip-option-value-policy",
            "schema_version": self.schema_version,
            "season": self.season,
            "horizon_gameweeks": self.horizon_gameweeks,
            "first_available_at": self.first_available_at,
            "mode": self.mode.value,
            "option_values": [
                {"chip": name, "value": value.semantic_payload()}
                for name, value in self.option_values
            ],
        }

    @property
    def policy_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class PricePolicy:
    season: str
    first_available_at: str
    mode: PricePolicyMode = PricePolicyMode.OFFICIAL_CURRENT_ONLY
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported price policy schema_version")
        if self.mode is not PricePolicyMode.OFFICIAL_CURRENT_ONLY:
            raise ValueError("unsupported production price policy mode")
        object.__setattr__(self, "season", _nonempty(self.season, label="price-policy season"))
        object.__setattr__(
            self,
            "first_available_at",
            _aware_iso(self.first_available_at, label="price-policy first_available_at"),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-price-policy",
            "schema_version": self.schema_version,
            "season": self.season,
            "first_available_at": self.first_available_at,
            "mode": self.mode.value,
        }

    @property
    def policy_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class CandidatePolicy:
    season: str
    first_available_at: str
    mode: CandidatePolicyMode = CandidatePolicyMode.FULL_OFFICIAL
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported candidate policy schema_version")
        if self.mode is not CandidatePolicyMode.FULL_OFFICIAL:
            raise ValueError("unsupported production candidate policy mode")
        object.__setattr__(self, "season", _nonempty(self.season, label="candidate-policy season"))
        object.__setattr__(
            self,
            "first_available_at",
            _aware_iso(self.first_available_at, label="candidate-policy first_available_at"),
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-candidate-policy",
            "schema_version": self.schema_version,
            "season": self.season,
            "first_available_at": self.first_available_at,
            "mode": self.mode.value,
        }

    @property
    def policy_id(self) -> str:
        return canonical_sha256(self.semantic_payload())
