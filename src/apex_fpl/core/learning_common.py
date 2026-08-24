"""Exact dependency-free primitives for Apex V2 offline learning governance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from fractions import Fraction
from math import gcd


def artifact_id(value: str, *, label: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


def aware_iso(value: str, *, label: str) -> str:
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


def instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


@dataclass(frozen=True, slots=True)
class ExactMetricValue:
    """Reduced exact rational for all durable learning metrics and thresholds."""

    numerator: int
    denominator: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise ValueError("metric numerator must be integer")
        if (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, int)
            or self.denominator <= 0
        ):
            raise ValueError("metric denominator must be positive integer")
        divisor = gcd(abs(self.numerator), self.denominator)
        object.__setattr__(self, "numerator", self.numerator // divisor)
        object.__setattr__(self, "denominator", self.denominator // divisor)

    @classmethod
    def from_fraction(cls, value: Fraction) -> "ExactMetricValue":
        return cls(value.numerator, value.denominator)

    def as_fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def semantic_payload(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


class LearningPolicyQualification(StrEnum):
    SHADOW = "SHADOW"
    QUALIFIED = "QUALIFIED"
    SUSPENDED = "SUSPENDED"


class LearningEvaluationStatus(StrEnum):
    COMPLETE = "COMPLETE"
    INCONCLUSIVE = "INCONCLUSIVE"
    FAILED = "FAILED"


class ModelPromotionDecision(StrEnum):
    PROMOTE = "PROMOTE"
    RETAIN = "RETAIN"
    INCONCLUSIVE = "INCONCLUSIVE"


class MetricDirection(StrEnum):
    LOWER_IS_BETTER = "LOWER_IS_BETTER"
    HIGHER_IS_BETTER = "HIGHER_IS_BETTER"
    CLOSER_TO_ZERO = "CLOSER_TO_ZERO"


class EvaluationMetric(StrEnum):
    START_BRIER = "START_BRIER"
    MINUTES_MAE = "MINUTES_MAE"
    MINUTES_MSE = "MINUTES_MSE"
    POINTS_MAE = "POINTS_MAE"
    POINTS_MEAN_BIAS = "POINTS_MEAN_BIAS"
    INTERVAL_COVERAGE = "INTERVAL_COVERAGE"
    PREDICTION_COVERAGE = "PREDICTION_COVERAGE"
    DECISION_REALIZED_POINTS_DELTA = "DECISION_REALIZED_POINTS_DELTA"
