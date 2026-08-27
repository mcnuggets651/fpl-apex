from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.decision_policy_store import store_decision_policy
from apex_fpl.control.decision_policy_support import store_decision_policy_support
from apex_fpl.control.experiment_registry import load_empirical_qualification_certificate
from apex_fpl.control.forecast_model_store import store_forecast_model
from apex_fpl.control.manager_state_store import store_manager_state
from apex_fpl.control.production_planning_bundle import store_production_planning_bundle
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.control.ruleset_store import store_ruleset
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionUseMode,
    RationalValue,
)
from apex_fpl.core.decision_policy import (
    TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
)
from apex_fpl.core.decision_policy_support import (
    CandidatePolicy,
    ChipOptionValuePolicy,
    ContinuationValuePolicy,
    ExactPolicyValue,
    PricePolicy,
)
from apex_fpl.core.forecast import (
    DiscreteIntegerDistribution,
    Forecast,
    ForecastModelArtifact,
    ForecastUncertainty,
    ForecastUseMode,
    ModelQualificationState,
    PlayerFixtureForecast,
    PlayerFixtureTarget,
    UncertaintyKind,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    FeatureSnapshotId,
    GlobalWorldId,
    PredictionBatchId,
    ScenarioGeneratorId,
    ScenarioPolicyId,
)
from apex_fpl.core.manager_state import ManagerState, ManagerStateScope, OwnedPlayer
from apex_fpl.core.production_bundle import ProductionPlanningBundle
from apex_fpl.core.scenarios import (
    ActionRobustnessMetrics,
    JointPlayerGameweekOutcome,
    JointScenario,
    RobustnessReport,
    ScenarioConvergenceCheckpoint,
    ScenarioConvergenceStatus,
    ScenarioSet,
)
from apex_fpl.decision.planner import optimise_receding_horizon
from apex_fpl.decision.planning_store import store_planning_result
from apex_fpl.decision.scenario_store import store_robustness_report, store_scenario_set
from apex_fpl.decision.store import store_candidate_universe
from apex_fpl.forecast.forecast_store import store_forecast

from empirical_qualification_helpers import synthetic_supported_qualification_artifact
from immutable_fixture_cache import restore_cached_fixture, retain_cached_fixture


OWNED_POSITIONS = {
    1: "GK",
    2: "GK",
    3: "DEF",
    4: "DEF",
    5: "DEF",
    6: "DEF",
    7: "DEF",
    8: "MID",
    9: "MID",
    10: "MID",
    11: "MID",
    12: "MID",
    13: "FWD",
    14: "FWD",
    15: "FWD",
}
CANDIDATE_POSITIONS = {**OWNED_POSITIONS, 16: "MID"}


@dataclass(frozen=True, slots=True)
class DirectQualificationMaterial:
    artifact_id: str
    subject_id: str
    experiment_id: str
    semantic_evidence_id: str


@dataclass(frozen=True, slots=True)
class SyntheticPlanningBundleFixture:
    bundle: ProductionPlanningBundle
    manager_state: ManagerState
    direct_qualifications: dict[str, DirectQualificationMaterial]


def _qualification_material(
    *,
    store: ArtifactStore,
    artifact_id: str,
    semantic_evidence_id: str,
) -> DirectQualificationMaterial:
    certificate = load_empirical_qualification_certificate(artifact_id, store=store)
    if not certificate.supported:
        raise ValueError("synthetic direct qualification must replay as supported")
    return DirectQualificationMaterial(
        artifact_id=artifact_id,
        subject_id=certificate.subject_id,
        experiment_id=certificate.experiment_id,
        semantic_evidence_id=semantic_evidence_id,
    )


def synthetic_production_planning_bundle(
    *,
    store: ArtifactStore,
    season: str = "2026-2027",
    entry: int = 63984,
    gameweek: int = 2,
) -> SyntheticPlanningBundleFixture:
    """Build mechanism-only schema-v2 lineage; never real production evidence.

    The synthetic world intentionally contains one affordable non-owned midfielder whose
    value arrives in the second planning Gameweek. Exact trajectory tie-breaking therefore
    prefers banking the first free transfer and executing a real financed transfer later.
    Positive chip option values also force a non-zero retained terminal reserve.
    """

    cache_key = (season, entry, gameweek)
    cached = restore_cached_fixture(
        "production-planning-bundle",
        cache_key,
        store=store,
    )
    if cached is not None:
        if not isinstance(cached, SyntheticPlanningBundleFixture):
            raise TypeError("production planning fixture cache type mismatch")
        return cached

    ruleset = load_ruleset(Path("config/rules/2026-2027.yaml"))
    ruleset_artifact = store_ruleset(ruleset, store=store)
    world_id = GlobalWorldId(
        canonical_sha256(
            {
                "schema_name": "synthetic-production-planning-world",
                "season": season,
                "entry": entry,
                "gameweek": gameweek,
            }
        )
    )

    universe_source = store.put_bytes(b"synthetic-planning-universe-source").artifact_id
    universe = CandidateUniverse(
        global_world_id=world_id,
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=tuple(
            CandidatePlayer(
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                position=position,
                current_price_tenths=51 if player_id == 16 else 50,
            )
            for player_id, position in CANDIDATE_POSITIONS.items()
        ),
        official_player_count=len(CANDIDATE_POSITIONS),
        source_artifact_ids=(universe_source,),
    )
    stored_universe = store_candidate_universe(universe, store=store)

    manager_source = store.put_bytes(b"synthetic-current-manager-source").artifact_id
    manager_state = ManagerState(
        season=season,
        entry_id=entry,
        gameweek=gameweek,
        ruleset_id=ruleset.ruleset_id,
        scope=ManagerStateScope.CURRENT_EXACT,
        bank_tenths=1,
        free_transfers=1,
        squad=tuple(
            OwnedPlayer(
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                position=position,
                purchase_basis_tenths=50,
                current_price_tenths=50,
                selling_price_tenths=50,
            )
            for player_id, position in OWNED_POSITIONS.items()
        ),
        provenance_artifact_ids=(manager_source,),
    )
    manager_state.require_decision_safe(ruleset=ruleset)
    manager_artifact = store_manager_state(manager_state, store=store)

    parameter = store.put_bytes(b"synthetic-planning-model-parameters").artifact_id
    shadow_model = ForecastModelArtifact(
        model_name="synthetic-planning-model",
        model_version="1",
        feature_contract="synthetic-planning-features-v1",
        prediction_contract="synthetic-planning-predictions-v1",
        parameter_artifact_ids=(parameter,),
        qualification_state=ModelQualificationState.SHADOW,
        qualification_artifact_id=None,
        valid_seasons=(season,),
        trained_through="2026-07-15T00:00:00Z",
        first_available_at="2026-08-01T00:00:00Z",
        max_horizon_gameweeks=2,
    )
    model_qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=shadow_model.semantic_payload(),
        subject_kind="apex.forecast-model",
        proof_id="PO-FORECAST-QUALIFICATION-001",
        season=season,
    )
    model = replace(
        shadow_model,
        qualification_state=ModelQualificationState.QUALIFIED,
        qualification_artifact_id=model_qualification,
    )
    store_forecast_model(model, store=store)

    rows = []
    for target_gw in (gameweek, gameweek + 1):
        for player_id, position in CANDIDATE_POSITIONS.items():
            points = 3
            if player_id == 8 and target_gw == gameweek + 1:
                points = 10
            if player_id == 16:
                points = 0 if target_gw == gameweek else 12
            target = PlayerFixtureTarget(
                fixture_id=target_gw * 1000 + player_id,
                gameweek=target_gw,
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                opponent_team_id=100 + player_id,
                is_home=True,
                position=position,
            )
            rows.append(
                PlayerFixtureForecast(
                    target=target,
                    prediction_row_id=canonical_sha256(
                        {
                            "schema_name": "synthetic-planning-row",
                            "gameweek": target_gw,
                            "player_id": player_id,
                        }
                    ),
                    minutes_distribution=DiscreteIntegerDistribution(((90, 10_000),)),
                    points_distribution=DiscreteIntegerDistribution(((points, 10_000),)),
                    uncertainty=ForecastUncertainty(
                        uncertainty_kind=UncertaintyKind.PROBABILISTIC,
                        deterministic_reason=None,
                        scenario_count=1,
                        minutes_p10=90,
                        minutes_p50=90,
                        minutes_p90=90,
                        points_p10=points,
                        points_p50=points,
                        points_p90=points,
                        appearance_probability_bps=10_000,
                        sixty_plus_probability_bps=10_000,
                    ),
                )
            )
    forecast = Forecast(
        season=season,
        feature_snapshot_id=FeatureSnapshotId(
            canonical_sha256(
                {"schema_name": "synthetic-planning-feature", "world": str(world_id)}
            )
        ),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=world_id,
        ruleset_id=ruleset.ruleset_id,
        model_artifact_id=model.model_artifact_id,
        prediction_batch_id=PredictionBatchId(
            canonical_sha256(
                {"schema_name": "synthetic-planning-batch", "world": str(world_id)}
            )
        ),
        use_mode=ForecastUseMode.PRODUCTION,
        model_qualification_state=ModelQualificationState.QUALIFIED,
        rows=tuple(rows),
        abstentions=(),
    )
    stored_forecast = store_forecast(forecast, store=store)

    continuation = ContinuationValuePolicy(
        season=season,
        horizon_gameweeks=2,
        first_available_at="2026-08-01T00:00:00Z",
        gameweek_weights=(ExactPolicyValue.one(), ExactPolicyValue.one()),
    )
    chip_option = ChipOptionValuePolicy(
        season=season,
        horizon_gameweeks=2,
        first_available_at="2026-08-01T00:00:00Z",
        option_values=tuple(
            (chip, ExactPolicyValue.one())
            for chip in ("BENCH_BOOST", "FREE_HIT", "TRIPLE_CAPTAIN", "WILDCARD")
        ),
    )
    price = PricePolicy(season=season, first_available_at="2026-08-01T00:00:00Z")
    candidate = CandidatePolicy(season=season, first_available_at="2026-08-01T00:00:00Z")
    support_ids = tuple(
        store_decision_policy_support(item, store=store)
        for item in (continuation, chip_option, price, candidate)
    )
    shadow_policy = DecisionPolicy(
        policy_name="synthetic-production-planning-policy",
        policy_version="1",
        season=season,
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-02T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=2,
        continuation_value_artifact_id=support_ids[0],
        chip_option_value_artifact_id=support_ids[1],
        price_policy_artifact_id=support_ids[2],
        candidate_policy_artifact_id=support_ids[3],
        tie_break_policy=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    )
    policy_qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=shadow_policy.semantic_payload(),
        subject_kind="apex.decision-policy",
        proof_id="PO-DECISION-POLICY-QUALIFICATION-001",
        season=season,
    )
    policy = replace(
        shadow_policy,
        qualification_state=DecisionPolicyQualificationState.QUALIFIED,
        qualification_artifact_id=policy_qualification,
    )
    store_decision_policy(policy, store=store)

    decision = optimise_receding_horizon(
        state=manager_state,
        forecast=forecast,
        universe=universe,
        ruleset=ruleset,
        policy=policy,
        continuation=continuation,
        chip_option=chip_option,
        price_policy=price,
        candidate_policy=candidate,
        use_mode=DecisionUseMode.PRODUCTION,
        max_search_nodes=5_000,
        alternatives_limit=0,
    )
    stored_decision = store_planning_result(
        decision,
        manager_state_id=manager_state.manager_state_id,
        universe=universe,
        ruleset=ruleset,
        continuation=continuation,
        chip_option=chip_option,
        store=store,
    )

    scenario_source = store.put_bytes(b"synthetic-planning-scenario-source").artifact_id
    scenarios = tuple(
        JointScenario(
            ordinal=ordinal,
            weight=1,
            outcomes=tuple(
                JointPlayerGameweekOutcome(
                    player_id=OfficialPlayerId(player_id),
                    gameweek=gameweek,
                    appeared=True,
                    points=0 if player_id == 16 else 3,
                )
                for player_id in CANDIDATE_POSITIONS
            ),
        )
        for ordinal in range(1, 513)
    )
    scenario_set = ScenarioSet(
        season=season,
        forecast_id=forecast.forecast_id,
        scenario_generator_id=ScenarioGeneratorId(
            canonical_sha256(
                {"schema_name": "synthetic-planning-generator", "season": season}
            )
        ),
        rng_algorithm="synthetic-planning-counter-v1",
        seed=1,
        gameweeks=(gameweek,),
        player_ids=tuple(
            OfficialPlayerId(player_id) for player_id in CANDIDATE_POSITIONS
        ),
        scenarios=scenarios,
        source_artifact_ids=(scenario_source,),
    )
    stored_scenarios = store_scenario_set(scenario_set, store=store)
    action_id = decision.selected_action.action_id
    current_points = decision.selected_action.mechanics.objective_points
    metric_256 = ActionRobustnessMetrics(
        action_id=action_id,
        sample_count=256,
        mean_points=current_points,
        lower_cvar_points=current_points,
        lower_quantile_points=current_points.numerator // current_points.denominator,
    )
    metric_512 = replace(metric_256, sample_count=512)
    report = RobustnessReport(
        decision_id=decision.decision_id,
        forecast_id=forecast.forecast_id,
        scenario_set_id=scenario_set.scenario_set_id,
        scenario_policy_id=ScenarioPolicyId(
            canonical_sha256(
                {"schema_name": "synthetic-planning-scenario-policy", "season": season}
            )
        ),
        ev_anchor_action_id=action_id,
        robust_preferred_action_id=action_id,
        robust_preferred_ev_regret=RationalValue.zero(),
        status=ScenarioConvergenceStatus.CONVERGED,
        xp_reconciled=True,
        checkpoints=(
            ScenarioConvergenceCheckpoint(
                sample_count=256,
                metrics=(metric_256,),
                mean_ranking=(action_id,),
                cvar_ranking=(action_id,),
                tail_ranking=(action_id,),
            ),
            ScenarioConvergenceCheckpoint(
                sample_count=512,
                metrics=(metric_512,),
                mean_ranking=(action_id,),
                cvar_ranking=(action_id,),
                tail_ranking=(action_id,),
            ),
        ),
        blockers=(),
    )
    stored_report = store_robustness_report(report, store=store)
    scenario_qualification = synthetic_supported_qualification_artifact(
        store=store,
        subject_payload=report.semantic_payload(),
        subject_kind="apex.scenario-convergence",
        proof_id="PO-SCENARIO-CONVERGENCE-001",
        season=season,
    )

    bundle = ProductionPlanningBundle(
        season=season,
        entry=entry,
        gameweek=gameweek,
        world_id=world_id,
        manager_state_id=manager_state.manager_state_id,
        manager_state_artifact_id=manager_artifact,
        ruleset_id=ruleset.ruleset_id,
        ruleset_artifact_id=ruleset_artifact,
        forecast_id=forecast.forecast_id,
        forecast_artifact_id=stored_forecast.artifact_id,
        forecast_model_id=model.model_artifact_id,
        decision_policy_id=policy.decision_policy_id,
        candidate_universe_id=universe.candidate_universe_id,
        candidate_universe_artifact_id=stored_universe.artifact_id,
        decision_input_id=decision.decision_input.decision_input_id,
        decision_id=decision.decision_id,
        planning_result_id=decision.planning_result_id,
        planning_result_artifact_id=stored_decision.artifact_id,
        scenario_set_id=scenario_set.scenario_set_id,
        scenario_set_artifact_id=stored_scenarios.artifact_id,
        robustness_report_id=report.robustness_report_id,
        robustness_report_artifact_id=stored_report.artifact_id,
    )
    store_production_planning_bundle(bundle, store=store)

    direct = {
        "PO-FORECAST-QUALIFICATION-001": _qualification_material(
            store=store,
            artifact_id=model_qualification,
            semantic_evidence_id=str(model.model_artifact_id),
        ),
        "PO-DECISION-POLICY-QUALIFICATION-001": _qualification_material(
            store=store,
            artifact_id=policy_qualification,
            semantic_evidence_id=str(policy.decision_policy_id),
        ),
        "PO-SCENARIO-CONVERGENCE-001": _qualification_material(
            store=store,
            artifact_id=scenario_qualification,
            semantic_evidence_id=str(report.robustness_report_id),
        ),
    }
    fixture = SyntheticPlanningBundleFixture(
        bundle=bundle,
        manager_state=manager_state,
        direct_qualifications=direct,
    )
    cached_fixture = retain_cached_fixture(
        "production-planning-bundle",
        cache_key,
        fixture,
        store=store,
    )
    if not isinstance(cached_fixture, SyntheticPlanningBundleFixture):
        raise TypeError("production planning fixture cache type mismatch")
    return cached_fixture