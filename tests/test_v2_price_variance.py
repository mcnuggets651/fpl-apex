from __future__ import annotations

import pytest

from apex.decision.price_forecast import PriceChangeDistribution
from apex.decision.price_transitions import PriceStateError


def test_price_distribution_exposes_expected_delta_and_variance() -> None:
    distribution = PriceChangeDistribution(p_fall=0.2, p_flat=0.5, p_rise=0.3)

    assert distribution.expected_delta_tenths == pytest.approx(0.1)
    expected_variance = 0.2 * (-1.1) ** 2 + 0.5 * (-0.1) ** 2 + 0.3 * (0.9) ** 2
    assert distribution.variance_delta_tenths2 == pytest.approx(expected_variance)


def test_price_distribution_reports_discrete_price_quantiles() -> None:
    distribution = PriceChangeDistribution(p_fall=0.15, p_flat=0.65, p_rise=0.20)

    assert distribution.price_quantile_tenths(75, 0.10) == 74
    assert distribution.price_quantile_tenths(75, 0.50) == 75
    assert distribution.price_quantile_tenths(75, 0.90) == 76


def test_price_distribution_rejects_invalid_probability_mass() -> None:
    with pytest.raises(PriceStateError, match="sum to 1"):
        PriceChangeDistribution(p_fall=0.2, p_flat=0.5, p_rise=0.4)


def test_price_quantile_rejects_invalid_quantile() -> None:
    distribution = PriceChangeDistribution(p_fall=0.2, p_flat=0.5, p_rise=0.3)

    with pytest.raises(PriceStateError, match="between 0 and 1"):
        distribution.price_quantile_tenths(75, 1.1)
