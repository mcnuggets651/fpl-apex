from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isclose, isfinite

from apex.domain.models import parse_utc

from .price_transitions import PriceStateError


class PredictorDirection(StrEnum):
    RISE = "RISE"
    FALL = "FALL"
    NEUTRAL = "NEUTRAL"


@dataclass(frozen=True)
class OfficialPricePredictorSignal:
    """One sealed Official FPL price-predictor observation.

    Progress percentages are evidence features, not probabilities. `next_change_at`
    is the price-change event this observation was available before.
    """

    element_id: int
    captured_at: str
    next_change_at: str
    market_price_tenths: int
    direction: PredictorDirection
    current_progress_pct: float
    predicted_progress_pct: float | None = None

    def __post_init__(self) -> None:
        if int(self.element_id) < 1:
            raise PriceStateError("price predictor element ID must be positive")
        if int(self.market_price_tenths) < 0:
            raise PriceStateError("price predictor market price must be non-negative")
        current = float(self.current_progress_pct)
        if not isfinite(current) or current < 0.0:
            raise PriceStateError("current predictor progress must be finite and non-negative")
        if self.predicted_progress_pct is not None:
            predicted = float(self.predicted_progress_pct)
            if not isfinite(predicted) or predicted < 0.0:
                raise PriceStateError(
                    "predicted predictor progress must be finite and non-negative"
                )
        if parse_utc(self.captured_at) >= parse_utc(self.next_change_at):
            raise PriceStateError(
                "price predictor observation must be sealed before its change event"
            )

    @property
    def progress_for_calibration_pct(self) -> float:
        if self.predicted_progress_pct is not None:
            return float(self.predicted_progress_pct)
        return float(self.current_progress_pct)

    @property
    def signed_progress_pct(self) -> float:
        progress = self.progress_for_calibration_pct
        if self.direction == PredictorDirection.RISE:
            return progress
        if self.direction == PredictorDirection.FALL:
            return -progress
        return 0.0


@dataclass(frozen=True)
class PriceCalibrationObservation:
    signal: OfficialPricePredictorSignal
    outcome_delta_tenths: int
    outcome_observed_at: str

    def __post_init__(self) -> None:
        if int(self.outcome_delta_tenths) not in (-1, 0, 1):
            raise PriceStateError("calibration outcome must be -1, 0 or +1 tenth")
        if parse_utc(self.outcome_observed_at) < parse_utc(self.signal.next_change_at):
            raise PriceStateError(
                "price outcome cannot be attached before the sealed change event"
            )


@dataclass(frozen=True)
class PriceChangeDistribution:
    p_fall: float
    p_flat: float
    p_rise: float

    def __post_init__(self) -> None:
        values = (float(self.p_fall), float(self.p_flat), float(self.p_rise))
        if any(not isfinite(value) or not 0.0 <= value <= 1.0 for value in values):
            raise PriceStateError("price probabilities must be finite values in [0, 1]")
        if not isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=1e-9):
            raise PriceStateError("price probabilities must sum to 1")


@dataclass(frozen=True)
class IsotonicProbabilityKnot:
    max_score: float
    probability: float


@dataclass(frozen=True)
class MonotonicPriceCalibrator:
    """Deterministic empirical calibration from signed predictor progress.

    The rise model is non-decreasing in signed progress. The fall model is
    non-decreasing in negative signed progress. No hidden FPL threshold is
    reverse-engineered and no predictor percentage is treated as a probability.
    """

    observation_count: int
    rise_knots: tuple[IsotonicProbabilityKnot, ...]
    fall_knots: tuple[IsotonicProbabilityKnot, ...]

    @classmethod
    def fit(
        cls,
        observations: tuple[PriceCalibrationObservation, ...],
    ) -> MonotonicPriceCalibrator:
        if not observations:
            raise PriceStateError("price calibration requires prospective observations")
        rise_samples = [
            (
                float(observation.signal.signed_progress_pct),
                1.0 if int(observation.outcome_delta_tenths) == 1 else 0.0,
            )
            for observation in observations
        ]
        fall_samples = [
            (
                -float(observation.signal.signed_progress_pct),
                1.0 if int(observation.outcome_delta_tenths) == -1 else 0.0,
            )
            for observation in observations
        ]
        return cls(
            observation_count=len(observations),
            rise_knots=_fit_isotonic(rise_samples),
            fall_knots=_fit_isotonic(fall_samples),
        )

    def predict(self, signal: OfficialPricePredictorSignal) -> PriceChangeDistribution:
        signed = float(signal.signed_progress_pct)
        p_rise = _predict_isotonic(self.rise_knots, signed)
        p_fall = _predict_isotonic(self.fall_knots, -signed)
        directional_sum = p_rise + p_fall
        if directional_sum > 1.0:
            # Separately monotonic one-vs-rest calibrators can overlap around an
            # uncertain neutral region. Renormalise only enough to retain a legal
            # three-way distribution; no bank/value term is introduced.
            p_rise /= directional_sum
            p_fall /= directional_sum
            p_flat = 0.0
        else:
            p_flat = 1.0 - directional_sum
        return PriceChangeDistribution(p_fall, p_flat, p_rise)


def _fit_isotonic(
    samples: list[tuple[float, float]],
) -> tuple[IsotonicProbabilityKnot, ...]:
    grouped: dict[float, tuple[float, int]] = {}
    for raw_score, raw_outcome in samples:
        score = float(raw_score)
        outcome = float(raw_outcome)
        if not isfinite(score):
            raise PriceStateError("calibration score must be finite")
        if outcome not in (0.0, 1.0):
            raise PriceStateError("isotonic calibration outcome must be binary")
        successes, count = grouped.get(score, (0.0, 0))
        grouped[score] = (successes + outcome, count + 1)

    blocks: list[dict[str, float | int]] = []
    for score in sorted(grouped):
        successes, count = grouped[score]
        blocks.append(
            {
                "max_score": score,
                "successes": successes,
                "count": count,
            }
        )
        while len(blocks) >= 2:
            previous = blocks[-2]
            current = blocks[-1]
            previous_mean = float(previous["successes"]) / int(previous["count"])
            current_mean = float(current["successes"]) / int(current["count"])
            if previous_mean <= current_mean + 1e-15:
                break
            merged = {
                "max_score": float(current["max_score"]),
                "successes": float(previous["successes"]) + float(current["successes"]),
                "count": int(previous["count"]) + int(current["count"]),
            }
            blocks[-2:] = [merged]

    return tuple(
        IsotonicProbabilityKnot(
            max_score=float(block["max_score"]),
            probability=float(block["successes"]) / int(block["count"]),
        )
        for block in blocks
    )


def _predict_isotonic(
    knots: tuple[IsotonicProbabilityKnot, ...],
    score: float,
) -> float:
    if not knots:
        raise PriceStateError("isotonic calibrator has no knots")
    value = float(score)
    for knot in knots:
        if value <= float(knot.max_score):
            return float(knot.probability)
    return float(knots[-1].probability)
