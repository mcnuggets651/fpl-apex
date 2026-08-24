"""Content-addressed persistence for Slice 9 scenario and robustness evidence."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import RationalValue
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    DecisionId,
    ForecastId,
    ScenarioGeneratorId,
    ScenarioPolicyId,
    ScenarioSetId,
)
from apex_fpl.core.scenarios import (
    ActionRobustnessMetrics,
    JointPlayerGameweekOutcome,
    JointScenario,
    RobustnessReport,
    ScenarioConvergenceCheckpoint,
    ScenarioConvergenceStatus,
    ScenarioSet,
)


@dataclass(frozen=True, slots=True)
class StoredScenarioSet:
    scenario_set: ScenarioSet
    artifact_id: str


@dataclass(frozen=True, slots=True)
class StoredRobustnessReport:
    report: RobustnessReport
    artifact_id: str


def _object(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    return dict(value)


def _array(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be array")
    return list(value)


def _int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string")
    return value.strip()


def _json_object(content: bytes, *, label: str) -> dict[str, object]:
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    return _object(value, label=label)


def _rv(value: object, *, label: str) -> RationalValue:
    raw = _object(value, label=label)
    return RationalValue(
        _int(raw.get("numerator"), label=f"{label} numerator"),
        _int(raw.get("denominator"), label=f"{label} denominator"),
    )


def _scenario_storage_payload(scenario_set: ScenarioSet) -> dict[str, object]:
    return {
        "season": scenario_set.season,
        "forecast_id": str(scenario_set.forecast_id),
        "scenario_generator_id": str(scenario_set.scenario_generator_id),
        "rng_algorithm": scenario_set.rng_algorithm,
        "seed": scenario_set.seed,
        "gameweeks": list(scenario_set.gameweeks),
        "player_ids": [int(item) for item in scenario_set.player_ids],
        "source_artifact_ids": list(scenario_set.source_artifact_ids),
        "scenarios": [scenario.semantic_payload() for scenario in scenario_set.scenarios],
    }


def store_scenario_set(
    scenario_set: ScenarioSet,
    *,
    store: ArtifactStore,
) -> StoredScenarioSet:
    for artifact_id in scenario_set.source_artifact_ids:
        store.read_bytes(artifact_id)
    envelope = {
        "schema_name": "apex-stored-scenario-set",
        "schema_version": 1,
        "scenario_set_id": str(scenario_set.scenario_set_id),
        "scenario_set": _scenario_storage_payload(scenario_set),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-scenario-set",
        schema_version="1",
    )
    return StoredScenarioSet(scenario_set=scenario_set, artifact_id=ref.artifact_id)


def load_scenario_set(artifact_id: str, *, store: ArtifactStore) -> StoredScenarioSet:
    envelope = _json_object(store.read_bytes(artifact_id), label="stored scenario set")
    if envelope.get("schema_name") != "apex-stored-scenario-set":
        raise ValueError("not an Apex stored scenario set")
    if _int(envelope.get("schema_version"), label="scenario store schema_version") != 1:
        raise ValueError("unsupported stored scenario set schema")
    raw = _object(envelope.get("scenario_set"), label="scenario set payload")
    scenario_rows = _array(raw.get("scenarios"), label="scenarios")
    scenarios: list[JointScenario] = []
    for scenario_value in scenario_rows:
        scenario_raw = _object(scenario_value, label="scenario")
        outcome_rows = _array(scenario_raw.get("outcomes"), label="scenario outcomes")
        outcomes = tuple(
            JointPlayerGameweekOutcome(
                player_id=OfficialPlayerId(
                    _int(
                        _object(row, label="scenario outcome").get("player_id"),
                        label="outcome player_id",
                    )
                ),
                gameweek=_int(
                    _object(row, label="scenario outcome").get("gameweek"),
                    label="outcome gameweek",
                ),
                appeared=_bool(
                    _object(row, label="scenario outcome").get("appeared"),
                    label="outcome appeared",
                ),
                points=_int(
                    _object(row, label="scenario outcome").get("points"),
                    label="outcome points",
                ),
            )
            for row in outcome_rows
        )
        scenarios.append(
            JointScenario(
                ordinal=_int(scenario_raw.get("ordinal"), label="scenario ordinal"),
                weight=_int(scenario_raw.get("weight"), label="scenario weight"),
                outcomes=outcomes,
            )
        )
    scenario_set = ScenarioSet(
        season=_text(raw.get("season"), label="scenario season"),
        forecast_id=ForecastId(_text(raw.get("forecast_id"), label="scenario forecast_id")),
        scenario_generator_id=ScenarioGeneratorId(
            _text(raw.get("scenario_generator_id"), label="scenario generator_id")
        ),
        rng_algorithm=_text(raw.get("rng_algorithm"), label="scenario rng_algorithm"),
        seed=_int(raw.get("seed"), label="scenario seed"),
        gameweeks=tuple(
            _int(item, label="scenario gameweek")
            for item in _array(raw.get("gameweeks"), label="scenario gameweeks")
        ),
        player_ids=tuple(
            OfficialPlayerId(_int(item, label="scenario player_id"))
            for item in _array(raw.get("player_ids"), label="scenario player_ids")
        ),
        scenarios=tuple(scenarios),
        source_artifact_ids=tuple(
            _text(item, label="scenario source artifact")
            for item in _array(raw.get("source_artifact_ids"), label="scenario source artifacts")
        ),
    )
    declared = _text(envelope.get("scenario_set_id"), label="declared scenario_set_id")
    if str(scenario_set.scenario_set_id) != declared:
        raise ValueError("stored ScenarioSet semantic identity mismatch")
    for source_id in scenario_set.source_artifact_ids:
        store.read_bytes(source_id)
    return StoredScenarioSet(scenario_set=scenario_set, artifact_id=artifact_id)


def _report_storage_payload(report: RobustnessReport) -> dict[str, object]:
    return report.semantic_payload()


def store_robustness_report(
    report: RobustnessReport,
    *,
    store: ArtifactStore,
) -> StoredRobustnessReport:
    envelope = {
        "schema_name": "apex-stored-robustness-report",
        "schema_version": 1,
        "robustness_report_id": str(report.robustness_report_id),
        "robustness_report": _report_storage_payload(report),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-robustness-report",
        schema_version="1",
    )
    return StoredRobustnessReport(report=report, artifact_id=ref.artifact_id)


def load_robustness_report(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredRobustnessReport:
    envelope = _json_object(store.read_bytes(artifact_id), label="stored robustness report")
    if envelope.get("schema_name") != "apex-stored-robustness-report":
        raise ValueError("not an Apex stored robustness report")
    if _int(envelope.get("schema_version"), label="robustness store schema_version") != 1:
        raise ValueError("unsupported stored robustness report schema")
    raw = _object(envelope.get("robustness_report"), label="robustness report payload")
    checkpoints: list[ScenarioConvergenceCheckpoint] = []
    for checkpoint_value in _array(raw.get("checkpoints"), label="robustness checkpoints"):
        checkpoint_raw = _object(checkpoint_value, label="robustness checkpoint")
        metrics = tuple(
            ActionRobustnessMetrics(
                action_id=_text(
                    _object(value, label="robustness metric").get("action_id"),
                    label="metric action_id",
                ),
                sample_count=_int(
                    _object(value, label="robustness metric").get("sample_count"),
                    label="metric sample_count",
                ),
                mean_points=_rv(
                    _object(value, label="robustness metric").get("mean_points"),
                    label="metric mean_points",
                ),
                lower_cvar_points=_rv(
                    _object(value, label="robustness metric").get("lower_cvar_points"),
                    label="metric lower_cvar_points",
                ),
                lower_quantile_points=_int(
                    _object(value, label="robustness metric").get("lower_quantile_points"),
                    label="metric lower_quantile_points",
                ),
            )
            for value in _array(checkpoint_raw.get("metrics"), label="checkpoint metrics")
        )
        checkpoints.append(
            ScenarioConvergenceCheckpoint(
                sample_count=_int(
                    checkpoint_raw.get("sample_count"), label="checkpoint sample_count"
                ),
                metrics=metrics,
                mean_ranking=tuple(
                    _text(item, label="mean ranking action")
                    for item in _array(checkpoint_raw.get("mean_ranking"), label="mean ranking")
                ),
                cvar_ranking=tuple(
                    _text(item, label="CVaR ranking action")
                    for item in _array(checkpoint_raw.get("cvar_ranking"), label="CVaR ranking")
                ),
                tail_ranking=tuple(
                    _text(item, label="tail ranking action")
                    for item in _array(checkpoint_raw.get("tail_ranking"), label="tail ranking")
                ),
            )
        )
    preferred_raw = raw.get("robust_preferred_action_id")
    regret_raw = raw.get("robust_preferred_ev_regret")
    report = RobustnessReport(
        decision_id=DecisionId(_text(raw.get("decision_id"), label="robustness decision_id")),
        forecast_id=ForecastId(_text(raw.get("forecast_id"), label="robustness forecast_id")),
        scenario_set_id=ScenarioSetId(
            _text(raw.get("scenario_set_id"), label="robustness scenario_set_id")
        ),
        scenario_policy_id=ScenarioPolicyId(
            _text(raw.get("scenario_policy_id"), label="robustness scenario_policy_id")
        ),
        ev_anchor_action_id=_text(
            raw.get("ev_anchor_action_id"), label="robustness EV anchor"
        ),
        robust_preferred_action_id=(
            None
            if preferred_raw is None
            else _text(preferred_raw, label="robust preferred action")
        ),
        robust_preferred_ev_regret=(
            None
            if regret_raw is None
            else _rv(regret_raw, label="robust preferred EV regret")
        ),
        status=ScenarioConvergenceStatus(
            _text(raw.get("status"), label="robustness status")
        ),
        xp_reconciled=_bool(raw.get("xp_reconciled"), label="robustness xp_reconciled"),
        checkpoints=tuple(checkpoints),
        blockers=tuple(
            _text(item, label="robustness blocker")
            for item in _array(raw.get("blockers"), label="robustness blockers")
        ),
    )
    declared = _text(
        envelope.get("robustness_report_id"),
        label="declared robustness_report_id",
    )
    if str(report.robustness_report_id) != declared:
        raise ValueError("stored RobustnessReport semantic identity mismatch")
    return StoredRobustnessReport(report=report, artifact_id=artifact_id)
