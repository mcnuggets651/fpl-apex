"""Store and independently replay schema-v2 production receding-horizon lineage."""

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
from apex_fpl.control.manager_state_store import load_manager_state
from apex_fpl.control.ruleset_store import load_ruleset_artifact
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import CandidateUniverse, CandidateUniverseScope, DecisionUseMode
from apex_fpl.core.decision_policy import DecisionEvaluationMode, DecisionPolicy
from apex_fpl.core.forecast import Forecast, ForecastModelArtifact
from apex_fpl.core.ids import (
    BundleId,
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    DecisionPolicyId,
    ForecastId,
    GlobalWorldId,
    ManagerStateId,
    ModelArtifactId,
    PlanningResultId,
    RobustnessReportId,
    RuleSetId,
    ScenarioSetId,
)
from apex_fpl.core.manager_state import ManagerState
from apex_fpl.core.planning import (
    PlanningSolverStatus,
    RecedingHorizonDecisionResult,
)
from apex_fpl.core.production_bundle import ProductionPlanningBundle
from apex_fpl.core.rules import RuleSet
from apex_fpl.core.scenarios import RobustnessReport, ScenarioConvergenceStatus, ScenarioSet
from apex_fpl.decision.planning_store import load_planning_result
from apex_fpl.decision.scenario_store import load_robustness_report, load_scenario_set
from apex_fpl.decision.store import load_candidate_universe
from apex_fpl.forecast.forecast_store import load_forecast


@dataclass(frozen=True, slots=True)
class VerifiedProductionPlanningBundle:
    bundle: ProductionPlanningBundle
    manager_state: ManagerState
    ruleset: RuleSet
    decision: RecedingHorizonDecisionResult
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


def _read_json_object(artifact_id: str, *, store: ArtifactStore, label: str) -> dict[str, object]:
    try:
        content = store.read_bytes(artifact_id)
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError(f"production planning bundle {label} failed integrity/replay") from exc
    try:
        value = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"production planning bundle {label} is not UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"production planning bundle {label} must be JSON object")
    return dict(value)


def _load_bundle_contract(
    bundle_id: BundleId | str,
    *,
    store: ArtifactStore,
) -> ProductionPlanningBundle:
    expected = BundleId(str(bundle_id))
    raw = _read_json_object(str(expected), store=store, label="bundle")
    if raw.get("schema_name") != "apex-production-decision-bundle":
        raise ValueError("not an Apex production decision bundle")
    if _int(raw.get("schema_version"), label="production planning schema_version") != 2:
        raise ValueError("production authority requires schema-v2 planning bundle")
    bundle = ProductionPlanningBundle(
        season=_text(raw.get("season"), label="production planning season"),
        entry=_int(raw.get("entry"), label="production planning entry"),
        gameweek=_int(raw.get("gameweek"), label="production planning gameweek"),
        world_id=GlobalWorldId(_text(raw.get("world_id"), label="world_id")),
        manager_state_id=ManagerStateId(
            _text(raw.get("manager_state_id"), label="manager_state_id")
        ),
        manager_state_artifact_id=_text(
            raw.get("manager_state_artifact_id"), label="manager_state_artifact_id"
        ),
        ruleset_id=RuleSetId(_text(raw.get("ruleset_id"), label="ruleset_id")),
        ruleset_artifact_id=_text(raw.get("ruleset_artifact_id"), label="ruleset_artifact_id"),
        forecast_id=ForecastId(_text(raw.get("forecast_id"), label="forecast_id")),
        forecast_artifact_id=_text(raw.get("forecast_artifact_id"), label="forecast_artifact_id"),
        forecast_model_id=ModelArtifactId(
            _text(raw.get("forecast_model_id"), label="forecast_model_id")
        ),
        decision_policy_id=DecisionPolicyId(
            _text(raw.get("decision_policy_id"), label="decision_policy_id")
        ),
        candidate_universe_id=CandidateUniverseId(
            _text(raw.get("candidate_universe_id"), label="candidate_universe_id")
        ),
        candidate_universe_artifact_id=_text(
            raw.get("candidate_universe_artifact_id"), label="candidate_universe_artifact_id"
        ),
        decision_input_id=DecisionInputId(
            _text(raw.get("decision_input_id"), label="decision_input_id")
        ),
        decision_id=DecisionId(_text(raw.get("decision_id"), label="decision_id")),
        planning_result_id=PlanningResultId(
            _text(raw.get("planning_result_id"), label="planning_result_id")
        ),
        planning_result_artifact_id=_text(
            raw.get("planning_result_artifact_id"), label="planning_result_artifact_id"
        ),
        scenario_set_id=ScenarioSetId(
            _text(raw.get("scenario_set_id"), label="scenario_set_id")
        ),
        scenario_set_artifact_id=_text(
            raw.get("scenario_set_artifact_id"), label="scenario_set_artifact_id"
        ),
        robustness_report_id=RobustnessReportId(
            _text(raw.get("robustness_report_id"), label="robustness_report_id")
        ),
        robustness_report_artifact_id=_text(
            raw.get("robustness_report_artifact_id"), label="robustness_report_artifact_id"
        ),
        schema_version=2,
    )
    if bundle.bundle_id != expected:
        raise ValueError("production planning bundle semantic identity mismatch")
    if canonical_json_bytes(raw) != store.read_bytes(str(expected)):
        raise ValueError("production planning bundle is not canonical JSON")
    return bundle


def _forecast_horizon(forecast: Forecast) -> int:
    gameweeks = sorted({row.target.gameweek for row in (*forecast.rows, *forecast.abstentions)})
    if not gameweeks:
        raise ValueError("production planning forecast has no targets")
    return gameweeks[-1] - gameweeks[0] + 1


def _verify_model_dependencies(model: ForecastModelArtifact, *, store: ArtifactStore) -> None:
    for artifact_id in model.parameter_artifact_ids:
        if not store.verify(artifact_id):
            raise ValueError("production planning model parameter is missing/corrupt")
    if model.qualification_artifact_id is None or not store.verify(model.qualification_artifact_id):
        raise ValueError("production planning model qualification is missing/corrupt")


def _load_policy_supports(policy: DecisionPolicy, *, store: ArtifactStore):
    ids = (
        policy.continuation_value_artifact_id,
        policy.chip_option_value_artifact_id,
        policy.price_policy_artifact_id,
        policy.candidate_policy_artifact_id,
    )
    if any(item is None for item in ids):
        raise ValueError("production planning DecisionPolicy lacks complete support semantics")
    continuation = load_continuation_value_policy(
        str(policy.continuation_value_artifact_id), store=store, as_of=policy.first_available_at
    )
    chip = load_chip_option_value_policy(
        str(policy.chip_option_value_artifact_id), store=store, as_of=policy.first_available_at
    )
    price = load_price_policy(
        str(policy.price_policy_artifact_id), store=store, as_of=policy.first_available_at
    )
    candidate = load_candidate_policy(
        str(policy.candidate_policy_artifact_id), store=store, as_of=policy.first_available_at
    )
    if any(item.season != policy.season for item in (continuation, chip, price, candidate)):
        raise ValueError("production planning DecisionPolicy support season mismatch")
    if continuation.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("production planning continuation horizon mismatch")
    if chip.horizon_gameweeks != policy.horizon_gameweeks:
        raise ValueError("production planning chip-option horizon mismatch")
    return continuation, chip, price, candidate


def _verify_bundle_lineage(
    bundle: ProductionPlanningBundle,
    *,
    store: ArtifactStore,
) -> VerifiedProductionPlanningBundle:
    manager_state = load_manager_state(bundle.manager_state_id, store=store)
    ruleset = load_ruleset_artifact(bundle.ruleset_id, store=store)
    stored_universe = load_candidate_universe(bundle.candidate_universe_artifact_id, store=store)
    stored_forecast = load_forecast(bundle.forecast_artifact_id, store=store)
    policy = load_decision_policy(bundle.decision_policy_id, store=store)
    model = load_forecast_model(bundle.forecast_model_id, store=store)
    stored_scenarios = load_scenario_set(bundle.scenario_set_artifact_id, store=store)
    stored_report = load_robustness_report(bundle.robustness_report_artifact_id, store=store)
    continuation, chip, _, _ = _load_policy_supports(policy, store=store)
    stored_decision = load_planning_result(
        bundle.planning_result_id,
        manager_state_id=bundle.manager_state_id,
        universe=stored_universe.universe,
        ruleset=ruleset,
        continuation=continuation,
        chip_option=chip,
        store=store,
    )

    universe = stored_universe.universe
    forecast = stored_forecast.forecast
    decision = stored_decision.result
    scenario_set = stored_scenarios.scenario_set
    report = stored_report.report

    if manager_state.manager_state_id != bundle.manager_state_id:
        raise ValueError("production planning ManagerState identity mismatch")
    manager_state.require_decision_safe(ruleset=ruleset)
    if manager_state.entry_id != bundle.entry or manager_state.gameweek != bundle.gameweek:
        raise ValueError("production planning ManagerState entry/gameweek mismatch")
    if manager_state.season != bundle.season or ruleset.season != bundle.season:
        raise ValueError("production planning manager/rules season mismatch")
    if manager_state.ruleset_id != bundle.ruleset_id:
        raise ValueError("production planning ManagerState RuleSet identity mismatch")

    if decision.planning_result_id != bundle.planning_result_id:
        raise ValueError("production planning result identity mismatch")
    if decision.decision_id != bundle.decision_id:
        raise ValueError("production planning DecisionId mismatch")
    if decision.decision_input.decision_input_id != bundle.decision_input_id:
        raise ValueError("production planning DecisionInputId mismatch")
    if decision.decision_input.manager_state_id != bundle.manager_state_id:
        raise ValueError("production planning DecisionInput ManagerState mismatch")
    if decision.decision_input.ruleset_id != bundle.ruleset_id:
        raise ValueError("production planning DecisionInput RuleSet mismatch")
    if decision.decision_input.use_mode is not DecisionUseMode.PRODUCTION:
        raise ValueError("production planning bundle cannot expose non-production DecisionInput")
    if (
        decision.solver.status is not PlanningSolverStatus.OPTIMAL
        or not decision.solver.search_complete
        or decision.solver.gap is None
        or decision.solver.gap.numerator != 0
    ):
        raise ValueError("production planning bundle requires complete zero-gap optimal planner")

    if policy.decision_policy_id != bundle.decision_policy_id:
        raise ValueError("production planning DecisionPolicy identity mismatch")
    if decision.decision_input.decision_policy_id != bundle.decision_policy_id:
        raise ValueError("production planning DecisionInput DecisionPolicy mismatch")
    if not policy.production_qualified:
        raise ValueError("production planning DecisionPolicy is not production-qualified")
    if policy.evaluation_mode is not DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION:
        raise ValueError("production planning DecisionPolicy is not receding-horizon")
    if policy.qualification_artifact_id is None or not store.verify(policy.qualification_artifact_id):
        raise ValueError("production planning DecisionPolicy qualification is missing/corrupt")

    if universe.candidate_universe_id != bundle.candidate_universe_id:
        raise ValueError("production planning CandidateUniverse identity mismatch")
    if decision.decision_input.candidate_universe_id != bundle.candidate_universe_id:
        raise ValueError("production planning DecisionInput CandidateUniverse mismatch")
    if universe.scope is not CandidateUniverseScope.FULL_OFFICIAL:
        raise ValueError("production planning requires FULL_OFFICIAL CandidateUniverse")
    if universe.global_world_id != bundle.world_id:
        raise ValueError("production planning candidate world mismatch")

    if forecast.forecast_id != bundle.forecast_id:
        raise ValueError("production planning Forecast identity mismatch")
    if decision.decision_input.forecast_id != bundle.forecast_id:
        raise ValueError("production planning DecisionInput Forecast mismatch")
    if forecast.global_world_id != bundle.world_id:
        raise ValueError("production planning forecast world mismatch")
    if forecast.ruleset_id != bundle.ruleset_id:
        raise ValueError("production planning Forecast RuleSet mismatch")
    if forecast.season != bundle.season or not forecast.production_eligible:
        raise ValueError("production planning forecast is not production-eligible for bundle season")
    if forecast.model_artifact_id != bundle.forecast_model_id:
        raise ValueError("production planning forecast model identity mismatch")

    if model.model_artifact_id != bundle.forecast_model_id:
        raise ValueError("production planning forecast model semantic mismatch")
    _verify_model_dependencies(model, store=store)
    model.require_valid_for(
        season=bundle.season,
        feature_cutoff=forecast.feature_cutoff,
        horizon_gameweeks=_forecast_horizon(forecast),
        production=True,
    )

    if scenario_set.scenario_set_id != bundle.scenario_set_id:
        raise ValueError("production planning ScenarioSet identity mismatch")
    if scenario_set.forecast_id != bundle.forecast_id or scenario_set.season != bundle.season:
        raise ValueError("production planning ScenarioSet forecast/season mismatch")
    if bundle.gameweek not in scenario_set.gameweeks:
        raise ValueError("production planning ScenarioSet misses release gameweek")

    if report.robustness_report_id != bundle.robustness_report_id:
        raise ValueError("production planning RobustnessReport identity mismatch")
    if report.decision_id != bundle.decision_id:
        raise ValueError("production planning robustness decision mismatch")
    if report.forecast_id != bundle.forecast_id or report.scenario_set_id != bundle.scenario_set_id:
        raise ValueError("production planning robustness lineage mismatch")
    if report.ev_anchor_action_id != decision.selected_action.action_id:
        raise ValueError("production planning robustness anchor is not selected root action")
    if report.status is not ScenarioConvergenceStatus.CONVERGED or not report.xp_reconciled:
        raise ValueError("production planning requires converged xP-reconciled robustness")

    return VerifiedProductionPlanningBundle(
        bundle=bundle,
        manager_state=manager_state,
        ruleset=ruleset,
        decision=decision,
        decision_policy=policy,
        candidate_universe=universe,
        forecast=forecast,
        forecast_model=model,
        scenario_set=scenario_set,
        robustness_report=report,
    )


def store_production_planning_bundle(
    bundle: ProductionPlanningBundle,
    *,
    store: ArtifactStore,
) -> VerifiedProductionPlanningBundle:
    verified = _verify_bundle_lineage(bundle, store=store)
    ref = store.put_bytes(
        canonical_json_bytes(bundle.semantic_payload()),
        media_type="application/json",
        schema_name="apex-production-decision-bundle",
        schema_version="2",
    )
    if ref.artifact_id != str(bundle.bundle_id):
        raise ValueError("production planning bundle storage identity mismatch")
    return verified


def load_production_planning_bundle(
    bundle_id: BundleId | str,
    *,
    store: ArtifactStore,
) -> VerifiedProductionPlanningBundle:
    bundle = _load_bundle_contract(bundle_id, store=store)
    return _verify_bundle_lineage(bundle, store=store)
