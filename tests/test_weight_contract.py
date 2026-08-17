import pytest

from apex_fpl.config import Settings, _validated_weights


def test_default_production_weights_use_only_real_experts_and_sum_to_one():
    weights = Settings().weights
    assert weights["market"] == 0.0
    assert sum(weights.values()) == pytest.approx(1.0)
    # Preserve the pre-existing 24:46:20 relative prior after removing the dormant
    # 10% market slot; this is a source-contract correction, not squad-driven tuning.
    assert weights["official_ep"] / weights["apex_model"] == pytest.approx(24 / 46)
    assert weights["airsenal"] / weights["apex_model"] == pytest.approx(20 / 46)


def test_weight_contract_rejects_non_unit_or_unknown_configuration():
    with pytest.raises(ValueError, match="sum to 1.0"):
        _validated_weights(
            {"official_ep": 0.24, "apex_model": 0.46, "airsenal": 0.20, "market": 0.0}
        )
    with pytest.raises(ValueError, match="unknown ensemble weight keys"):
        _validated_weights(
            {
                "official_ep": 0.25,
                "apex_model": 0.50,
                "airsenal": 0.25,
                "market": 0.0,
                "phantom": 0.0,
            }
        )
