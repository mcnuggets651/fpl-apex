from __future__ import annotations

from dataclasses import dataclass, replace

from apex_fpl.control.decision_policy_store import store_decision_policy
from apex_fpl.control.decision_policy_support import store_decision_policy_support
from apex_fpl.control.experiment_registry import load_empirical_qualification_certificate
from apex_fpl.control.forecast_model_store import store_forecast_model
from apex_fpl.control.production_bundle import store_production_decision_bundle
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionAction,
    DecisionChip,
    DecisionInput,
    DecisionMechanics,
    DecisionObjectiveModel,
    DecisionResult,
    DecisionUseMode,
    ExactnessClaim,
    ExactnessStatus,
    ExpansionResult,
    RationalValue,
    SolverCertificate,
    SolverStatus,
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
    ManagerStateId,
    PredictionBatchId,
    RuleSetId,
    ScenarioGeneratorId,
)
from apex_fpl.core.production_bundle import ProductionDecisionBundle
from apex_fpl.core.scenarios import (
    ActionRobustnessMetrics,
    JointPlayerGameweekOutcome,
    JointScenario,
    RobustnessReport,
    ScenarioConvergenceCheckpoint,
    ScenarioConvergenceStatus,
    ScenarioSet,
)
from apex_fpl.decision.scenario_store import store_robustness_report, store_scenario_set
from apex_fpl.decision.store import store_candidate_universe, store_decision_result
from apex_fpl.forecast.forecast_store import store_forecast

from empirical_qualification_helpers import synthetic_supported_qualification_artifact


POSITIONS = {
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


@dataclass(frozen=True, slots=True)
class DirectQualificationMaterial:
    artifact_id: str
    subject_id: str
    experiment_id: str
    semantic_evidence_id: str


@dataclass(frozen=True, slots=True)
class SyntheticProductionBundleFixture:
    bundle: ProductionDecisionBundle
    direct_qualifications: dict[str, DirectQualificationMaterial]


def _qualification_material(
    *,
    store,
    artifact_id: str,
    semantic_evidence_id: str,
) -> DirectQualificationMaterial:
    certificate = load_empirical_qualification_certificate(artifact_id, store=store)
    return DirectQualificationMaterial(
        artifact_id=artifact_id,
        subject_id=certificate.subject_id,
        experiment_id=certificate.experiment_id,
        semantic_evidence_id=semantic_evidence_id,
    )


def synthetic_production_bundle(
    *,
    store,
    season: str = "2026-2027",
    entry: int = 63984,
    gameweek: int = 2,
) -> SyntheticProductionBundleFixture:
    """Build mechanism-only production lineage; never real production evidence."""

    world_id = GlobalWorldId(
        canonical_sha256(
            {
                "schema_name": "synthetic-production-world",
                "season": season,
                "entry": entry,
                "gameweek": gameweek,
            }
        )
    )
    ruleset_id = RuleSetId(
        canonical_sha256({"schema_name": "synthetic-ruleset", "season": season})
    )

    universe_source = store.put_bytes(b"synthetic-production-universe-source").artifact_id
    universe = CandidateUniverse(
        global_world_id=world_id,
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=tuple(
            CandidatePlayer(
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                position=position,
                current_price_tenths=50,
            )
            for player_id, position in POSITIONS.items()
        ),
        official_player_count=15,
        source_artifact_ids=(universe_source,),
    )
    stored_universe = store_candidate_universe(universe, store=store)

    model_parameter = store.put_bytes(b"synthetic-production-model-parameters").artifact_id
    shadow_model = ForecastModelArtifact(
        model_name="synthetic-production-model",
        model_version="1",
        feature_contract="synthetic-features-v1",
        prediction_contract="synthetic-predictions-v1",
        parameter_artifact_ids=(model_parameter,),
        qualification_state=ModelQualificationState.SHADOW,
        qualification_artifact_id=None,
        valid_seasons=(season,),
        trained_through="2026-07-15T00:00:00Z",
        first_available_at="2026-08-01T00:00:00Z",
        max_horizon_gameweeks=3,
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

    target = PlayerFixtureTarget(
        fixture_id=1001,
        gameweek=gameweek,
        player_id=OfficialPlayerId(1),
        team_id=1,
        opponent_team_id=2,
        is_home=True,
        position="GK",
    )
    forecast = Forecast(
        season=season,
        feature_snapshot_id=FeatureSnapshotId(
            canonical_sha256({"schema_name": "synthetic-feature", "world": str(world_id)})
        ),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=world_id,
        ruleset_id=ruleset_id,
        model_artifact_id=model.model_artifact_id,
        prediction_batch_id=PredictionBatchId(
            canonical_sha256({"schema_name": "synthetic-predictions", "world": str(world_id)})
        ),
        use_mode=ForecastUseMode.PRODUCTION,
        model_qualification_state=ModelQualificationState.QUALIFIED,
        rows=(
            PlayerFixtureForecast(
                target=target,
                prediction_row_id=canonical_sha256(
                    {"schema_name": "synthetic-prediction-row", "target": target.target_id}
                ),
                minutes_distribution=DiscreteIntegerDistribution(
                    ((60, 5_000), (90, 5_000))
                ),
                points_distribution=DiscreteIntegerDistribution(((4, 5_000), (6, 5_000))),
                uncertainty=ForecastUncertainty(
                    uncertainty_kind=UncertaintyKind.PROBABILISTIC,
                    deterministic_reason=None,
                    scenario_count=2,
                    minutes_p10=60,
                    minutes_p50=60,
                    minutes_p90=90,
                    points_p10=4,
                    points_p50=4,
                    points_p90=6,
                    appearance_probability_bps=10_000,
                    sixty_plus_probability_bps=10_000,
                ),
            ),
        ),
        abstentions=(),
    )
    stored_forecast = store_forecast(forecast, store=store)

    support_available = "2026-08-01T00:00:00Z"
    continuation = ContinuationValuePolicy(
        season=season,
        horizon_gameweeks=3,
        first_available_at=support_available,
        gameweek_weights=(
            ExactPolicyValue.one(),
            ExactPolicyValue(1, 2),
            ExactPolicyValue(1, 2),
        ),
    )
    chip_option = ChipOptionValuePolicy(
        season=season,
        horizon_gameweeks=3,
        first_available_at=support_available,
        option_values=(
            ("BENCH_BOOST", ExactPolicyValue(4, 1)),
            ("FREE_HIT", ExactPolicyValue(3, 1)),
            ("TRIPLE_CAPTAIN", ExactPolicyValue(5, 1)),
            ("WILDCARD", ExactPolicyValue(6, 1)),
        ),
    )
    price = PricePolicy(season=season, first_available_at=support_available)
    candidate = CandidatePolicy(season=season, first_available_at=support_available)
    support_ids = tuple(
        store_decision_policy_support(item, store=store)
        for item in (continuation, chip_option, price, candidate)
    )
    shadow_policy = DecisionPolicy(
        policy_name="synthetic-production-receding-policy",
        policy_version="1",
        season=season,
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-02T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=3,
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

    zero = RationalValue.zero()
    action = DecisionAction(
        chip=DecisionChip.NONE,
        transfers=(),
        squad_ids=tuple(OfficialPlayerId(player_id) for player_id in range(1, 16)),
        xi_ids=tuple(
            OfficialPlayerId(player_id)
            for player_id in (1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14)
        ),
        captain_id=OfficialPlayerId(13),
        vice_captain_id=OfficialPlayerId(14),
        bench_gk_id=OfficialPlayerId(2),
        outfield_bench_order=(
            OfficialPlayerId(6),
            OfficialPlayerId(7),
            OfficialPlayerId(15),
        ),
        bank_after_tenths=0,
        mechanics=DecisionMechanics(
            xi_points=zero,
            autosub_points=zero,
            captain_bonus=zero,
            squad_points_if_bench_boost=zero,
            points_before_hits=zero,
            hit_points=0,
            objective_points=zero,
        ),
    )
    decision_input = DecisionInput(
        manager_state_id=ManagerStateId(
            canonical_sha256({"schema_name": "synthetic-manager-state", "entry": entry})
        ),
        forecast_id=forecast.forecast_id,
        ruleset_id=ruleset_id,
        candidate_universe_id=universe.candidate_universe_id,
        decision_policy_id=policy.decision_policy_id,
        gameweek=gameweek,
        use_mode=DecisionUseMode.PRODUCTION,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=0,
        chips_considered=(DecisionChip.NONE,),
        numeric_policy_id=policy.numeric_policy_id,
    )
    decision = DecisionResult(
        decision_input=decision_input,
        selected_action=action,
        alternatives=(),
        solver=SolverCertificate(
            status=SolverStatus.OPTIMAL,
            incumbent_objective=zero,
            best_bound=zero,
            gap=zero,
            numeric_error_bound=zero,
            message="synthetic exact optimum",
        ),
        exactness=ExactnessClaim(
            status=ExactnessStatus.GLOBAL_OPTIMAL,
            candidate_universe_id=universe.candidate_universe_id,
            universe_scope=CandidateUniverseScope.FULL_OFFICIAL,
            solver_status=SolverStatus.OPTIMAL,
            action_surface_complete=True,
            search_complete=True,
            best_bound=zero,
            gap=zero,
            filter_identity=universe.filter_identity,
            expansion_result=ExpansionResult.NOT_RUN,
            expansion_certificate_id=None,
            numeric_error_bound=zero,
            reasons=(),
        ),
        enumerated_actions=1,
    )
    stored_decision = store_decision_result(decision, store=store)

    scenario_source = store.put_bytes(b"synthetic-production-scenario-source").artifact_id
    scenario_set = ScenarioSet(
        season=season,
        forecast_id=forecast.forecast_id,
        scenario_generator_id=ScenarioGeneratorId(
            canonical_sha256({"schema_name": "synthetic-scenario-generator", "season": season})
        ),
        rng_algorithm="synthetic-counter-v1",
        seed=1,
        gameweeks=(gameweek,),
        player_ids=(OfficialPlayerId(1),),
        scenarios=tuple(
            JointScenario(
                ordinal=ordinal,
                weight=1,
                outcomes=(
                    JointPlayerGameweekOutcome(
                        player_id=OfficialPlayerId(1),
                        gameweek=gameweek,
                        appeared=True,
                        points=4 if ordinal % 2 else 6,
                    ),
                ),
            )
            for ordinal in range(1, 513)
        ),
        source_artifact_ids=(scenario_source,),
    )
    stored_scenarios = store_scenario_set(scenario_set, store=store)
    metric_256 = ActionRobustnessMetrics(
        action_id=action.action_id,
        sample_count=256,
        mean_points=RationalValue(5, 1),
        lower_cvar_points=RationalValue(4, 1),
        lower_quantile_points=4,
    )
    metric_512 = replace(metric_256, sample_count=512)
    report = RobustnessReport(
        decision_id=decision.decision_id,
        forecast_id=forecast.forecast_id,
        scenario_set_id=scenario_set.scenario_set_id,
        scenario_policy_id=policy_id_for_synthetic_scenario_convergence(season),
        ev_anchor_action_id=action.action_id,
        robust_preferred_action_id=action.action_id,
        robust_preferred_ev_regret=zero,
        status=ScenarioConvergenceStatus.CONVERGED,
        xp_reconciled=True,
        checkpoints=(
            ScenarioConvergenceCheckpoint(
                sample_count=256,
                metrics=(metric_256,),
                mean_ranking=(action.action_id,),
                cvar_ranking=(action.action_id,),
                tail_ranking=(action.action_id,),
            ),
            ScenarioConvergenceCheckpoint(
                sample_count=512,
                metrics=(metric_512,),
                mean_ranking=(action.action_id,),
                cvar_ranking=(action.action_id,),
                tail_ranking=(action.action_id,),
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

    bundle = ProductionDecisionBundle(
        season=season,
        entry=entry,
        gameweek=gameweek,
        world_id=world_id,
        forecast_id=forecast.forecast_id,
        forecast_artifact_id=stored_forecast.artifact_id,
        forecast_model_id=model.model_artifact_id,
        decision_policy_id=policy.decision_policy_id,
        candidate_universe_id=universe.candidate_universe_id,
        candidate_universe_artifact_id=stored_universe.artifact_id,
        decision_input_id=decision.decision_input_id,
        decision_id=decision.decision_id,
        decision_result_artifact_id=stored_decision.artifact_id,
        scenario_set_id=scenario_set.scenario_set_id,
        scenario_set_artifact_id=stored_scenarios.artifact_id,
        robustness_report_id=report.robustness_report_id,
        robustness_report_artifact_id=stored_report.artifact_id,
    )
    store_production_decision_bundle(bundle, store=store)

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
    return SyntheticProductionBundleFixture(bundle=bundle, direct_qualifications=direct)


def policy_id_for_synthetic_scenario_convergence(season: str):
    from apex_fpl.core.ids import ScenarioPolicyId

    return ScenarioPolicyId(
        canonical_sha256({"schema_name": "synthetic-scenario-policy", "season": season})
    )
