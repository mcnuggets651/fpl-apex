import pytest

from apex_fpl.config import Settings, _validated_weights


def test_default_production_weights_are_qualified_airsenal_authority():
    weights = Settings().weights
    assert weights == {"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0}
    assert sum(weights.values()) == pytest.approx(1.0)


def test_weight_contract_rejects_non_unit_or_unknown_configuration():
    with pytest.raises(ValueError, match="sum to 1.0"):
        _validated_weights({"official_ep": 0.24, "apex_model": 0.46, "airsenal": 0.20, "market": 0.0})
    with pytest.raises(ValueError, match="unknown ensemble weight keys"):
        _validated_weights({"official_ep": 0.0, "apex_model": 0.0, "airsenal": 1.0, "market": 0.0, "phantom": 0.0})
