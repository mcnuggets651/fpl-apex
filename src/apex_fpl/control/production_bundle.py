"""Store and independently replay the exact V2 production decision lineage."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.control.decision_policy_store import load_decision_policy
from apex_fpl.control.decision_policy_support import (
    load_candidate_policy,
    load_chip_option_value_policy,
    load_continuation_value_policy,
    load_price_policy,
)
from apex_fpl.control.forecast_model_store import load_forecast_model
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import CandidateUniverse, DecisionResult, DecisionUseMode
from apex_fpl.core.decision_policy import DecisionPolicy
from apex_fpl.core.forecast import Forecast, ForecastModelArtifact
from apex_fpl.core.ids import (
    BundleId,
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    DecisionPolicyId,
    ForecastId,
    GlobalWorldId,
    ModelArtifactId,
    RobustnessReportId,
    ScenarioSetId,
)
from apex_fpl.core.production_bundle import ProductionDecisionBundle
from apex_fpl.core.scenarios import (
    RobustnessReport,
    ScenarioConvergenceStatus,
    ScenarioSet,
)
from apex_fpl.decision.scenario_store import load_robustness_report, load_scenario_set
from apex_fpl.decision.store import load_candidate_universe, load_decision_result
from apex_fpl.forecast.forecast_store import load_forecast


@dataclass(frozen=True, slots=True)
class VerifiedProductionDecisionBundle:
    bundle: ProductionDecisionBundle
    decision: DecisionResult
    decision_policy: DecisionPolicy
    candidate_universe: CandidateUniverse
    forecast: Forecast
    forecast_model: ForecastModelArtifact
    scenario_set: ScenarioSet
    robustness_report: RobustnessReport


def _int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string")
    return value.strip()


def _read_json_object(
    artifact_id: str,
    *,
    store: ArtifactStore,
    label: str,
) -> dict[str, object]:
    try:
        content = store.read_bytes(artifact_id)
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError(f"{label} artifact failed integrity/replay") from exc
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} artifact is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} artifact must be JSON object")
    return dict(value)


def _load_bundle_contract(bundle_id: BundleId | str, *, store: ArtifactStore) -> ProductionDecisionBundle:
    expected = BundleId(str(bundle_id))
    raw = _read_json_object(str(expected), store=store, label="production decision bundle")
    if raw.get("schema_name") != "apex-production-decision-bundle":
        raise ValueError("not an Apex production decision bundle")
    bundle = ProductionDecisionBundle(
        season=_text(raw.get("season"), label="production bundle season"),
        entry=_int(raw.get("entry"), label="production bundle entry"),
        gameweek=_int(raw.get("gameweek"), label="production bundle gameweek"),
        world_id=GlobalWorldId(_text(raw.get("world_id"), label="production bundle world_id")),
        forecast_id=ForecastId(
            _text(raw.get("forecast_id"), label="production bundle forecast_id")
        ),
        forecast_artifact_id=_text(
            raw.get("forecast_artifact_id"), label="production bundle forecast_artifact_id"
        ),
        forecast_model_id=ModelArtifactId(
            _text(raw.get("forecast_model_id"), label="production bundle forecast_model_id")
        ),
        decision_policy_id=DecisionPolicyId(
            _text(raw.get("decision_policy_id"), label="production bundle decision_policy_id")
        ),
        candidate_universe_id=CandidateUniverseId(
            _text(
                raw.get("candidate_universe_id"),
                label="production bundle candidate_universe_id",
            )
        ),
        candidate_universe_artifact_id=_text(
            raw.get("candidate_universe_artifact_id"),
            label="production bundle candidate_universe_artifact_id",
        ),
        decision_input_id=DecisionInputId(
            _text(raw.get("decision_input_id"), label="production bundle decision_input_id")
        ),
        decision_id=DecisionId(
            _text(raw.get("decision_id"), label="production bundle decision_id")
        ),
        decision_result_artifact_id=_text(
            raw.get("decision_result_artifact_id"),
            label="production bundle decision_result_artifact_id",
        ),
        scenario_set_id=ScenarioSetId(
            _text(raw.get("scenario_set_id"), label="production bundle scenario_set_id")
        ),
        scenario_set_artifact_id=_text(
            raw.get("scenario_set_artifact_id"),
            label="production bundle scenario_set_artifact_id",
        ),
        robustness_report_id=RobustnessReportId(
            _text(
                raw.get("robustness_report_id"),
                label="production bundle robustness_report_id",
            )
        ),
        robustness_report_artifact_id=_text(
            raw.get("robustness_report_artifact_id"),
            label="production bundle robustness_report_artifact_id",
        ),
        schema_version=_int(raw.get("schema_version"), label="production bundle schema_version"),
    )
    if bundle.bundle_id != expected:
        raise ValueError("production decision bundle semantic identity mismatch")
    return bundle


def _verify_policy_supports(policy: DecisionPolicy, *, store: ArtifactStore) -> None:
    support_ids = (
        policy.continuation_value_artifact_id,
        policy.chip_option_value_artifact_id,
        policy.price_policy_artifact_id,
        policy.candidate_policy_artifact_id,
    )
    if any(item is None for item in support_ids):
        raise ValueError("production bundle DecisionPolicy lacks complete support semantics")
    continuation = load_continuation_value_policy(
        str(policy.continuation_value_artifact_id),
        store=store,
        as_of=policy.first_available_at,
    )
    chip = load_chip_option_value_policy(
        str(policy.chip_option_value_artifact_id),
        store=store,
        as_of=policy.first_available_at,
    )
    price = load_price_policy(
        str(policy.price_policy_artifact_id),
        store=store,
        as_of=policy.first_available_at,
    )
    candidate = load_candidate_policy(
        str(policy.candidate_policy_artifact_id),
        store=store,
        as_of=policy.first_available_at,
    )
    if any(item.season != policy.season for item in (continuation, chip, price, candidate)):
        raise ValueError("production bundle DecisionPolicy support season mismatch")
    if continuation.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("production bundle continuation horizon mismatch")
    if chip.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("production bundle chip-option horizon mismatch")
    if policy.qualification_artifact_id is None:
        raise ValueError("production bundle DecisionPolicy lacks qualification artifact")
    store.read_bytes(policy.qualification_artifact_id)


def _verify_model_dependencies(model: ForecastModelArtifact, *, store: ArtifactStore) -> None:
    for artifact_id in model.parameter_artifact_ids:
        store.read_bytes(artifact_id)
    if model.qualification_artifact_id is None:
        raise ValueError("production bundle forecast model lacks qualification artifact")
    store.read_bytes(model.qualification_artifact_id)


def _forecast_horizon(forecast: Forecast) -> int:
    gameweeks = sorted(
        {
            row.target.gameweek
            for row in (*forecast.rows, *forecast.abstentions)
        }
    )
    if not gameweeks:
        raise ValueError("production bundle forecast has no declared targets")
    return gameweeks[-1] - gameweeks[0] + 1


def _verify_bundle_lineage(
    bundle: ProductionDecisionBundle,
    *,
    store: ArtifactStore,
) -> VerifiedProductionDecisionBundle:
    try:
        stored_decision = load_decision_result(bundle.decision_result_artifact_id, store=store)
        stored_universe = load_candidate_universe(
            bundle.candidate_universe_artifact_id,
            store=store,
        )
        stored_forecast = load_forecast(bundle.forecast_artifact_id, store=store)
        policy = load_decision_policy(bundle.decision_policy_id, store=store)
        model = load_forecast_model(bundle.forecast_model_id, store=store)
        stored_scenarios = load_scenario_set(bundle.scenario_set_artifact_id, store=store)
        stored_robustness = load_robustness_report(
            bundle.robustness_report_artifact_id,
            store=store,
        )
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError("production decision bundle dependency failed integrity/replay") from exc

    decision = stored_decision.result
    universe = stored_universe.universe
    forecast = stored_forecast.forecast
    scenario_set = stored_scenarios.scenario_set
    report = stored_robustness.report

    if decision.decision_id != bundle.decision_id:
        raise ValueError("production bundle DecisionId does not match replayed decision")
    if decision.decision_input_id != bundle.decision_input_id:
        raise ValueError("production bundle DecisionInputId does not match replayed decision")
    if decision.decision_input.decision_policy_id != bundle.decision_policy_id:
        raise ValueError("production bundle DecisionPolicyId does not match DecisionInput")
    if policy.decision_policy_id != bundle.decision_policy_id:
        raise ValueError("production bundle DecisionPolicy semantics do not match DecisionInput")
    if not policy.production_qualified:
        raise ValueError("production bundle DecisionPolicy is not production-qualified")
    _verify_policy_supports(policy, store=store)

    if decision.decision_input.candidate_universe_id != bundle.candidate_universe_id:
        raise ValueError("production bundle CandidateUniverseId does not match DecisionInput")
    if universe.candidate_universe_id != bundle.candidate_universe_id:
        raise ValueError("production bundle CandidateUniverse semantics do not match DecisionInput")
    if universe.global_world_id != bundle.world_id:
        raise ValueError("production bundle candidate universe world does not match bundle world")
    if decision.decision_input.gameweek != bundle.gameweek:
        raise ValueError("production bundle gameweek does not match DecisionInput")
    if decision.decision_input.use_mode is not DecisionUseMode.PRODUCTION:
        raise ValueError("production bundle cannot expose a non-production DecisionInput")
    if decision.decision_input.numeric_policy_id != policy.numeric_policy_id:
        raise ValueError("production bundle numeric policy differs from DecisionPolicy")

    if forecast.forecast_id != bundle.forecast_id:
        raise ValueError("production bundle ForecastId does not match replayed forecast")
    if decision.decision_input.forecast_id != bundle.forecast_id:
        raise ValueError("production bundle ForecastId does not match DecisionInput")
    if forecast.global_world_id != bundle.world_id:
        raise ValueError("production bundle forecast world does not match bundle world")
    if forecast.season != bundle.season:
        raise ValueError("production bundle forecast season mismatch")
    if not forecast.production_eligible:
        raise ValueError("production bundle forecast is not production-eligible")
    if forecast.model_artifact_id != bundle.forecast_model_id:
        raise ValueError("production bundle forecast model identity mismatch")
    if decision.decision_input.ruleset_id != forecast.ruleset_id:
        raise ValueError("production bundle DecisionInput and Forecast RuleSet identities differ")

    if model.model_artifact_id != bundle.forecast_model_id:
        raise ValueError("production bundle forecast model semantics mismatch")
    _verify_model_dependencies(model, store=store)
    model.require_valid_for(
        season=bundle.season,
        feature_cutoff=forecast.feature_cutoff,
        horizon_gameweeks=_forecast_horizon(forecast),
        production=True,
    )

    if scenario_set.scenario_set_id != bundle.scenario_set_id:
        raise ValueError("production bundle ScenarioSetId mismatch")
    if scenario_set.season != bundle.season:
        raise ValueError("production bundle ScenarioSet season mismatch")
    if scenario_set.forecast_id != bundle.forecast_id:
        raise ValueError("production bundle ScenarioSet forecast mismatch")
    if bundle.gameweek not in scenario_set.gameweeks:
        raise ValueError("production bundle ScenarioSet does not cover release gameweek")

    if report.robustness_report_id != bundle.robustness_report_id:
        raise ValueError("production bundle RobustnessReportId mismatch")
    if report.decision_id != bundle.decision_id:
        raise ValueError("production bundle robustness report decision mismatch")
    if report.forecast_id != bundle.forecast_id:
        raise ValueError("production bundle robustness report forecast mismatch")
    if report.scenario_set_id != bundle.scenario_set_id:
        raise ValueError("production bundle robustness report scenario-set mismatch")
    if report.ev_anchor_action_id != decision.selected_action.action_id:
        raise ValueError("production bundle robustness EV anchor is not selected max-EV action")
    if report.status is not ScenarioConvergenceStatus.CONVERGED or not report.xp_reconciled:
        raise ValueError("production bundle requires converged xP-reconciled robustness evidence")

    return VerifiedProductionDecisionBundle(
        bundle=bundle,
        decision=decision,
        decision_policy=policy,
        candidate_universe=universe,
        forecast=forecast,
        forecast_model=model,
        scenario_set=scenario_set,
        robustness_report=report,
    )


def store_production_decision_bundle(
    bundle: ProductionDecisionBundle,
    *,
    store: ArtifactStore,
) -> VerifiedProductionDecisionBundle:
    """Validate the complete lineage before making its bundle identity durable."""

    verified = _verify_bundle_lineage(bundle, store=store)
    ref = store.put_bytes(
        canonical_json_bytes(bundle.semantic_payload()),
        media_type="application/json",
        schema_name="apex-production-decision-bundle",
        schema_version=str(bundle.schema_version),
    )
    if ref.artifact_id != str(bundle.bundle_id):
        raise ValueError("production decision bundle storage identity mismatch")
    return verified


def load_production_decision_bundle(
    bundle_id: BundleId | str,
    *,
    store: ArtifactStore,
) -> VerifiedProductionDecisionBundle:
    bundle = _load_bundle_contract(bundle_id, store=store)
    return _verify_bundle_lineage(bundle, store=store)
