from __future__ import annotations

import pytest

from apex_fpl.core.decision import RationalValue
from apex_fpl.core.ids import DecisionId, ForecastId, ScenarioPolicyId, ScenarioSetId
from apex_fpl.core.scenarios import (
    ActionRobustnessMetrics,
    RobustnessReport,
    ScenarioConvergenceCheckpoint,
    ScenarioConvergenceStatus,
)


def _metric(action_id: str, sample_count: int) -> ActionRobustnessMetrics:
    return ActionRobustnessMetrics(
        action_id=action_id,
        sample_count=sample_count,
        mean_points=RationalValue(60, 1),
        lower_cvar_points=RationalValue(50, 1),
        lower_quantile_points=45,
    )


def _checkpoint(sample_count: int, action_ids: tuple[str, ...] = ("anchor", "alt")):
    metrics = tuple(_metric(action_id, sample_count) for action_id in action_ids)
    return ScenarioConvergenceCheckpoint(
        sample_count=sample_count,
        metrics=metrics,
        mean_ranking=action_ids,
        cvar_ranking=action_ids,
        tail_ranking=action_ids,
    )


def _base() -> dict[str, object]:
    return {
        "decision_id": DecisionId("decision"),
        "forecast_id": ForecastId("forecast"),
        "scenario_set_id": ScenarioSetId("scenario-set"),
        "scenario_policy_id": ScenarioPolicyId("scenario-policy"),
        "ev_anchor_action_id": "anchor",
        "robust_preferred_action_id": "anchor",
        "robust_preferred_ev_regret": RationalValue.zero(),
        "status": ScenarioConvergenceStatus.CONVERGED,
        "xp_reconciled": True,
        "checkpoints": (_checkpoint(256), _checkpoint(512)),
        "blockers": (),
    }


def test_inconclusive_report_cannot_expose_preferred_action_or_regret() -> None:
    payload = _base()
    payload.update(
        status=ScenarioConvergenceStatus.INCONCLUSIVE,
        xp_reconciled=False,
        blockers=("not converged",),
    )
    with pytest.raises(ValueError, match="INCONCLUSIVE robustness cannot expose"):
        RobustnessReport(**payload)


def test_converged_report_requires_bounded_preferred_diagnostic() -> None:
    payload = _base()
    payload.update(
        robust_preferred_action_id=None,
        robust_preferred_ev_regret=None,
    )
    with pytest.raises(ValueError, match="CONVERGED robustness requires"):
        RobustnessReport(**payload)


def test_report_rejects_checkpoint_action_set_drift_and_unknown_anchor() -> None:
    payload = _base()
    payload["checkpoints"] = (_checkpoint(256), _checkpoint(512, ("anchor", "other")))
    with pytest.raises(ValueError, match="checkpoint action sets must be identical"):
        RobustnessReport(**payload)

    payload = _base()
    payload["ev_anchor_action_id"] = "not-in-checkpoints"
    with pytest.raises(ValueError, match="EV anchor must be present"):
        RobustnessReport(**payload)


def test_report_rejects_boolean_laundering_and_unknown_preferred_action() -> None:
    payload = _base()
    payload["xp_reconciled"] = 1
    with pytest.raises(ValueError, match="xp_reconciled must be boolean"):
        RobustnessReport(**payload)

    payload = _base()
    payload["robust_preferred_action_id"] = "not-in-checkpoints"
    with pytest.raises(ValueError, match="preferred action must be present"):
        RobustnessReport(**payload)
