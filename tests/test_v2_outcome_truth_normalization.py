from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.outcome_truth_normalization import normalize_verified_outcome
from apex_fpl.control.outcome_truth_registry import load_outcome_truth_registry_bytes
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import FeatureSnapshotId, ForecastId, ModelArtifactId
from apex_fpl.core.learning_common import ExactMetricValue
from apex_fpl.core.learning_dataset import EvaluationCase
from apex_fpl.core.outcome_truth import OutcomeTarget

ROOT = Path(__file__).resolve().parents[1]


def _json_artifact(store: FileSystemArtifactStore, payload: object) -> str:
    return store.put_bytes(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).artifact_id


def _case(*, target: OutcomeTarget, artifact_id: str, player_id: int = 7) -> EvaluationCase:
    return EvaluationCase(
        forecast_id=ForecastId("truth-normalization-forecast"),
        feature_snapshot_id=FeatureSnapshotId("truth-normalization-features"),
        model_artifact_id=ModelArtifactId("truth-normalization-model"),
        target=target,
        player_id=OfficialPlayerId(player_id),
        gameweek=1,
        prediction_sealed_at="2026-08-10T08:00:00Z",
        outcome_first_available_at="2026-08-11T08:00:00Z",
        prediction_artifact_id="sha256:" + "1" * 64,
        outcome_artifact_id=artifact_id,
    )


def _registry():
    return load_outcome_truth_registry_bytes((ROOT / "config" / "outcome_truth_v2.yaml").read_bytes())


def test_verified_event_live_targets_recompute_exact_official_values(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    payload = {
        "elements": [
            {
                "id": 7,
                "stats": {
                    "minutes": 83,
                    "total_points": 11,
                    "goals_scored": 2,
                    "assists": 1,
                },
            }
        ]
    }
    artifact = _json_artifact(store, payload)
    expected = {
        OutcomeTarget.MINUTES: 83,
        OutcomeTarget.FPL_POINTS: 11,
        OutcomeTarget.GOAL: 2,
        OutcomeTarget.ASSIST: 1,
    }
    for target, value in expected.items():
        assert normalize_verified_outcome(
            case=_case(target=target, artifact_id=artifact),
            truth_registry=_registry(),
            store=store,
        ) == ExactMetricValue(value)


def test_verified_price_recomputes_exact_official_bootstrap_now_cost(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _json_artifact(store, {"elements": [{"id": 7, "now_cost": 55}]})
    assert normalize_verified_outcome(
        case=_case(target=OutcomeTarget.PRICE, artifact_id=artifact),
        truth_registry=_registry(),
        store=store,
    ) == ExactMetricValue(55)


def test_unresolved_truth_cannot_be_normalized_as_verified(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    artifact = _json_artifact(store, {"elements": [{"id": 7, "stats": {}}]})
    with pytest.raises(ValueError, match="not VERIFIED"):
        normalize_verified_outcome(
            case=_case(target=OutcomeTarget.START, artifact_id=artifact),
            truth_registry=_registry(),
            store=store,
        )


def test_official_truth_normalizer_rejects_duplicate_player_and_bool_value(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    duplicate = _json_artifact(
        store,
        {
            "elements": [
                {"id": 7, "stats": {"minutes": 80}},
                {"id": 7, "stats": {"minutes": 81}},
            ]
        },
    )
    with pytest.raises(ValueError, match="exactly one element"):
        normalize_verified_outcome(
            case=_case(target=OutcomeTarget.MINUTES, artifact_id=duplicate),
            truth_registry=_registry(),
            store=store,
        )

    bool_value = _json_artifact(
        store,
        {"elements": [{"id": 7, "stats": {"minutes": True}}]},
    )
    with pytest.raises(ValueError, match="must be an integer"):
        normalize_verified_outcome(
            case=_case(target=OutcomeTarget.MINUTES, artifact_id=bool_value),
            truth_registry=_registry(),
            store=store,
        )
