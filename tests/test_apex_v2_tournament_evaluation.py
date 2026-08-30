from apex.runtime.evaluate import (
    _material_disagreement_count,
    _paired_vs_champion,
)


def test_paired_scoring_uses_same_decision_surface_rows():
    predictions = {
        "airsenal": {1: 5.0, 2: 4.0, 3: 9.0},
        "dastan": {1: 4.0, 2: 2.0},
    }
    actual = {1: 3.0, 2: 5.0, 3: 8.0}
    result = _paired_vs_champion(
        predictions,
        champion_provider_id="airsenal",
        decision_surface=frozenset({1, 2, 3}),
        actual=actual,
    )["dastan"]

    assert result["paired_rows"] == 2
    assert result["champion_absolute_error_sum"] == 3.0
    assert result["challenger_absolute_error_sum"] == 4.0
    assert result["challenger_coverage"] == 2 / 3
    assert result["relative_mae_improvement"] < 0


def test_material_disagreement_collapses_correlated_family():
    predictions = {
        "airsenal": {1: 7.0, 2: 4.0},
        "dastan": {1: 5.0, 2: 3.0},
        "openfpl": {1: 5.2, 2: 3.1},
        "pitchside": {1: 5.1, 2: 3.0},
    }
    count = _material_disagreement_count(
        predictions,
        champion_provider_id="airsenal",
        decision_surface=frozenset({1, 2}),
    )
    assert count == 2
