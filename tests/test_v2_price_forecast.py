from __future__ import annotations

import pytest

from apex.decision.price_forecast import (
    MonotonicPriceCalibrator,
    OfficialPricePredictorSignal,
    PredictorDirection,
    PriceCalibrationObservation,
)
from apex.decision.price_transitions import PriceStateError


CHANGE_AT = "2026-09-06T00:00:00+01:00"
CAPTURED_AT = "2026-09-05T22:45:00+01:00"
OBSERVED_AT = "2026-09-06T00:05:00+01:00"


def _signal(
    progress: float,
    direction: PredictorDirection,
    *,
    predicted: float | None = None,
    element_id: int = 1,
) -> OfficialPricePredictorSignal:
    return OfficialPricePredictorSignal(
        element_id=element_id,
        captured_at=CAPTURED_AT,
        next_change_at=CHANGE_AT,
        market_price_tenths=75,
        direction=direction,
        current_progress_pct=progress,
        predicted_progress_pct=predicted,
    )


def _observation(
    progress: float,
    direction: PredictorDirection,
    outcome: int,
    *,
    element_id: int,
) -> PriceCalibrationObservation:
    return PriceCalibrationObservation(
        _signal(progress, direction, element_id=element_id),
        outcome,
        OBSERVED_AT,
    )


def test_predicted_progress_is_feature_not_probability() -> None:
    observations = (
        _observation(110.0, PredictorDirection.RISE, 1, element_id=1),
        _observation(110.0, PredictorDirection.RISE, 0, element_id=2),
    )
    calibrator = MonotonicPriceCalibrator.fit(observations)

    distribution = calibrator.predict(_signal(110.0, PredictorDirection.RISE))

    # Official progress can exceed 100%; it is not interpreted as 110% chance.
    assert distribution.p_rise == pytest.approx(0.5)
    assert distribution.p_flat == pytest.approx(0.5)
    assert distribution.p_fall == pytest.approx(0.0)


def test_calibrator_is_monotonic_in_signed_predictor_progress() -> None:
    observations = (
        _observation(50.0, PredictorDirection.RISE, 0, element_id=1),
        _observation(120.0, PredictorDirection.RISE, 1, element_id=2),
        _observation(50.0, PredictorDirection.FALL, 0, element_id=3),
        _observation(120.0, PredictorDirection.FALL, -1, element_id=4),
    )
    calibrator = MonotonicPriceCalibrator.fit(observations)

    low_rise = calibrator.predict(_signal(50.0, PredictorDirection.RISE))
    high_rise = calibrator.predict(_signal(120.0, PredictorDirection.RISE))
    low_fall = calibrator.predict(_signal(50.0, PredictorDirection.FALL))
    high_fall = calibrator.predict(_signal(120.0, PredictorDirection.FALL))

    assert high_rise.p_rise >= low_rise.p_rise
    assert high_fall.p_fall >= low_fall.p_fall
    assert high_rise.p_rise == pytest.approx(1.0)
    assert high_fall.p_fall == pytest.approx(1.0)


def test_predicted_progress_supersedes_current_progress_for_calibration_feature() -> None:
    signal = _signal(
        60.0,
        PredictorDirection.RISE,
        predicted=105.0,
    )

    assert signal.progress_for_calibration_pct == pytest.approx(105.0)
    assert signal.signed_progress_pct == pytest.approx(105.0)


def test_fall_signal_has_negative_signed_progress() -> None:
    signal = _signal(90.0, PredictorDirection.FALL)

    assert signal.signed_progress_pct == pytest.approx(-90.0)


def test_predictor_signal_must_be_sealed_before_change_event() -> None:
    with pytest.raises(PriceStateError, match="sealed before"):
        OfficialPricePredictorSignal(
            element_id=1,
            captured_at=CHANGE_AT,
            next_change_at=CHANGE_AT,
            market_price_tenths=75,
            direction=PredictorDirection.RISE,
            current_progress_pct=100.0,
        )


def test_outcome_cannot_be_attached_before_change_event() -> None:
    with pytest.raises(PriceStateError, match="cannot be attached before"):
        PriceCalibrationObservation(
            _signal(100.0, PredictorDirection.RISE),
            1,
            "2026-09-05T23:59:00+01:00",
        )


def test_calibrator_requires_prospective_observations() -> None:
    with pytest.raises(PriceStateError, match="requires prospective observations"):
        MonotonicPriceCalibrator.fit(())
