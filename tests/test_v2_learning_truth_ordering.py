from __future__ import annotations

import pytest

from apex_fpl.core.ids import EvaluationDatasetId, EvaluationTruthSetId
from apex_fpl.core.learning_common import ExactMetricValue
from apex_fpl.core.learning_observations import EvaluationObservation, EvaluationObservationSet
from apex_fpl.core.outcome_truth import OutcomeTarget


def _row(*, case_id: str, truth_case_id: str, actual: int) -> EvaluationObservation:
    return EvaluationObservation(
        case_id=case_id,
        truth_case_id=truth_case_id,
        target=OutcomeTarget.MINUTES,
        predicted_value=ExactMetricValue(actual),
        actual_value=ExactMetricValue(actual),
    )


def test_realized_truth_identity_is_independent_of_model_specific_case_order() -> None:
    truth_set = EvaluationTruthSetId("shared-truth")
    first = EvaluationObservationSet(
        evaluation_dataset_id=EvaluationDatasetId("candidate-dataset"),
        evaluation_truth_set_id=truth_set,
        observations=(
            _row(case_id="a-case", truth_case_id="z-truth", actual=10),
            _row(case_id="b-case", truth_case_id="a-truth", actual=20),
        ),
    )
    second = EvaluationObservationSet(
        evaluation_dataset_id=EvaluationDatasetId("incumbent-dataset"),
        evaluation_truth_set_id=truth_set,
        observations=(
            _row(case_id="c-case", truth_case_id="a-truth", actual=20),
            _row(case_id="d-case", truth_case_id="z-truth", actual=10),
        ),
    )
    assert first.observation_set_id != second.observation_set_id
    assert first.realized_truth_set_id == second.realized_truth_set_id


def test_observation_rejects_non_exact_actual_and_prediction_values() -> None:
    with pytest.raises(ValueError, match="predicted value"):
        EvaluationObservation(
            case_id="case",
            truth_case_id="truth",
            target=OutcomeTarget.MINUTES,
            predicted_value=60,  # type: ignore[arg-type]
            actual_value=ExactMetricValue(60),
        )
    with pytest.raises(ValueError, match="actual value"):
        EvaluationObservation(
            case_id="case",
            truth_case_id="truth",
            target=OutcomeTarget.MINUTES,
            predicted_value=ExactMetricValue(60),
            actual_value=60,  # type: ignore[arg-type]
        )
