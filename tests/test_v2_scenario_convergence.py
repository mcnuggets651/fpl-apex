from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.empirical_qualification_admission import (
    SCENARIO_GENERATOR_QUALIFICATION_ID,
    SCENARIO_POLICY_QUALIFICATION_ID,
)
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.control.scenario_registry import (
    ScenarioGovernanceRegistry,
    load_scenario_governance_registry,
)
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
from apex_fpl.core.forecast import (
    DiscreteIntegerDistribution,
    Forecast,
    ForecastUncertainty,
    ForecastUseMode,
    ModelQualificationState,
    PlayerFixtureForecast,
    PlayerFixtureTarget,
    UncertaintyKind,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    DecisionPolicyId,
    FeatureSnapshotId,
    GlobalWorldId,
    ManagerStateId,
    ModelArtifactId,
    PredictionBatchId,
    ScenarioGeneratorId,
)
from apex_fpl.core.scenarios import (
    HISTORICAL_SCENARIO_FLOOR,
    JointPlayerGameweekOutcome,
    JointScenario,
    ScenarioConvergencePolicy,
    ScenarioConvergenceStatus,
    ScenarioGeneratorArtifact,
    ScenarioQualificationState,
    ScenarioSet,
)
from apex_fpl.decision.robustness import (
    evaluate_decision_robustness,
    score_action_scenario,
)
from apex_fpl.decision.scenario_store import (
    load_robustness_report,
    load_scenario_set,
    store_robustness_report,
    store_scenario_set,
)

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


def _ruleset():
    return load_ruleset(Path("config/rules/2026-2027.yaml"))


def _universe(store: FileSystemArtifactStore) -> CandidateUniverse:
    source = store.put_bytes(b"scenario-universe").artifact_id
    return CandidateUniverse(
        global_world_id=GlobalWorldId("scenario-world"),
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
        source_artifact_ids=(source,),
    )


def _forecast() -> Forecast:
    rows = []
    for player_id, position in POSITIONS.items():
        rows.append(
            PlayerFixtureForecast(
                target=PlayerFixtureTarget(
                    fixture_id=100 + player_id,
                    gameweek=2,
                    player_id=OfficialPlayerId(player_id),
                    team_id=player_id,
                    opponent_team_id=100 + player_id,
                    is_home=True,
                    position=position,
                ),
                prediction_row_id=f"scenario-row-{player_id}",
                minutes_distribution=DiscreteIntegerDistribution(
                    ((60, 5_000), (90, 5_000))
                ),
                points_distribution=DiscreteIntegerDistribution(
                    ((4, 5_000), (6, 5_000))
                ),
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
            )
        )
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("scenario-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("scenario-world"),
        ruleset_id=_ruleset().ruleset_id,
        model_artifact_id=ModelArtifactId("scenario-model"),
        prediction_batch_id=PredictionBatchId("scenario-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=tuple(rows),
        abstentions=(),
    )


def _mechanics(objective: int) -> DecisionMechanics:
    return DecisionMechanics(
        xi_points=RationalValue(objective - 10, 1),
        autosub_points=RationalValue.zero(),
        captain_bonus=RationalValue(10, 1),
        squad_points_if_bench_boost=RationalValue.zero(),
        points_before_hits=RationalValue(objective, 1),
        hit_points=0,
        objective_points=RationalValue(objective, 1),
    )


def _action(*, captain: int, vice: int, objective: int) -> DecisionAction:
    return DecisionAction(
        chip=DecisionChip.NONE,
        transfers=(),
        squad_ids=tuple(OfficialPlayerId(player_id) for player_id in range(1, 16)),
        xi_ids=tuple(
            OfficialPlayerId(player_id)
            for player_id in (1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14)
        ),
        captain_id=OfficialPlayerId(captain),
        vice_captain_id=OfficialPlayerId(vice),
        bench_gk_id=OfficialPlayerId(2),
        outfield_bench_order=(
            OfficialPlayerId(6),
            OfficialPlayerId(7),
            OfficialPlayerId(15),
        ),
        bank_after_tenths=0,
        mechanics=_mechanics(objective),
    )


def _decision(forecast: Forecast, universe: CandidateUniverse) -> DecisionResult:
    selected = _action(captain=13, vice=14, objective=60)
    alternative = _action(captain=14, vice=13, objective=59)
    zero = RationalValue.zero()
    decision_input = DecisionInput(
        manager_state_id=ManagerStateId("scenario-state"),
        forecast_id=forecast.forecast_id,
        ruleset_id=_ruleset().ruleset_id,
        candidate_universe_id=universe.candidate_universe_id,
        decision_policy_id=DecisionPolicyId("scenario-decision-policy"),
        gameweek=2,
        use_mode=DecisionUseMode.SHADOW,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=0,
        chips_considered=(DecisionChip.NONE,),
    )
    solver = SolverCertificate(
        status=SolverStatus.OPTIMAL,
        incumbent_objective=RationalValue(60, 1),
        best_bound=RationalValue(60, 1),
        gap=zero,
        numeric_error_bound=zero,
        message="synthetic exact decision",
    )
    exactness = ExactnessClaim(
        status=ExactnessStatus.GLOBAL_OPTIMAL,
        candidate_universe_id=universe.candidate_universe_id,
        universe_scope=CandidateUniverseScope.FULL_OFFICIAL,
        solver_status=SolverStatus.OPTIMAL,
        action_surface_complete=True,
        search_complete=True,
        best_bound=RationalValue(60, 1),
        gap=zero,
        filter_identity="FULL_OFFICIAL",
        expansion_result=ExpansionResult.NOT_RUN,
        expansion_certificate_id=None,
        numeric_error_bound=zero,
        reasons=(),
    )
    return DecisionResult(
        decision_input=decision_input,
        selected_action=selected,
        alternatives=(alternative,),
        solver=solver,
        exactness=exactness,
        enumerated_actions=2,
    )


def _scenarios(
    store: FileSystemArtifactStore,
    forecast: Forecast,
    *,
    unstable_second_half: bool = False,
    captain_volatility: bool = False,
) -> ScenarioSet:
    source = store.put_bytes(b"sealed-joint-scenario-worker-output").artifact_id
    rows = []
    for ordinal in range(1, 513):
        if unstable_second_half and ordinal > 256:
            base_points = 10
        else:
            base_points = 4 if ordinal % 2 else 6
        outcomes = []
        for player_id in range(1, 16):
            points = base_points
            if captain_volatility and player_id == 13:
                points = 0 if ordinal % 2 else 10
            elif captain_volatility and player_id == 14:
                points = 5
            outcomes.append(
                JointPlayerGameweekOutcome(
                    player_id=OfficialPlayerId(player_id),
                    gameweek=2,
                    appeared=True,
                    points=points,
                )
            )
        rows.append(
            JointScenario(
                ordinal=ordinal,
                weight=1,
                outcomes=tuple(outcomes),
            )
        )
    return ScenarioSet(
        season="2026-2027",
        forecast_id=forecast.forecast_id,
        scenario_generator_id=ScenarioGeneratorId("synthetic-joint-generator"),
        rng_algorithm="synthetic-common-stream-v1",
        seed=20260824,
        gameweeks=(2,),
        player_ids=tuple(OfficialPlayerId(player_id) for player_id in range(1, 16)),
        scenarios=tuple(rows),
        source_artifact_ids=(source,),
    )


def _policy() -> ScenarioConvergencePolicy:
    return ScenarioConvergencePolicy(
        policy_name="synthetic-shadow-convergence",
        policy_version="1",
        season="2026-2027",
        qualification_state=ScenarioQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-24T00:00:00Z",
        checkpoint_counts=(256, 512),
        max_scenarios=1024,
        cvar_alpha_bps=5_000,
        lower_quantile_bps=1_000,
        mean_tolerance=RationalValue.zero(),
        cvar_tolerance=RationalValue.zero(),
        tail_tolerance=RationalValue.zero(),
        xp_absolute_tolerance=RationalValue.zero(),
        sampling_sigma_multiplier=RationalValue.zero(),
        max_ev_regret_tolerance=RationalValue(1, 1),
    )


def test_scenario_policy_has_historical_floor_and_registry_has_no_fabricated_champion() -> None:
    assert HISTORICAL_SCENARIO_FLOOR == 256
    registry = load_scenario_governance_registry(Path("config/scenario_governance_v2.yaml"))
    assert registry.generators == ()
    assert registry.policies == ()
    assert registry.champion_generator() is None
    assert registry.champion_policy() is None
    with pytest.raises(ValueError, match=">= 256"):
        replace(_policy(), checkpoint_counts=(128, 256))


def test_scenario_set_identity_binds_seed_weight_order_and_outcomes(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    base = _scenarios(store, forecast)
    changed = replace(base, seed=base.seed + 1)
    assert base.scenario_set_id != changed.scenario_set_id


def test_fixed_action_scenario_scoring_applies_autosub_and_vice_without_hindsight(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    universe = _universe(store)
    action = _action(captain=13, vice=14, objective=60)
    outcomes = []
    for player_id in range(1, 16):
        appeared = player_id not in {3, 13}
        points = 0 if not appeared else 1
        if player_id == 14:
            points = 5
        if player_id == 6:
            points = 7
        outcomes.append(
            JointPlayerGameweekOutcome(
                player_id=OfficialPlayerId(player_id),
                gameweek=2,
                appeared=appeared,
                points=points,
            )
        )
    score = score_action_scenario(
        action,
        JointScenario(ordinal=1, weight=1, outcomes=tuple(outcomes)),
        gameweek=2,
        universe=universe,
        ruleset=_ruleset(),
    )
    assert score == 26


def test_common_nested_stream_converges_and_preserves_ev_anchor(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    universe = _universe(store)
    decision = _decision(forecast, universe)
    report = evaluate_decision_robustness(
        decision,
        _scenarios(store, forecast),
        forecast,
        universe,
        _ruleset(),
        _policy(),
    )
    assert report.status is ScenarioConvergenceStatus.CONVERGED
    assert report.xp_reconciled is True
    assert [row.sample_count for row in report.checkpoints] == [256, 512]
    assert report.ev_anchor_action_id == decision.selected_action.action_id
    assert report.robust_preferred_action_id in {
        decision.selected_action.action_id,
        decision.alternatives[0].action_id,
    }


def test_robustness_preference_cannot_leave_governed_ev_regret_band(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    universe = _universe(store)
    decision = _decision(forecast, universe)
    report = evaluate_decision_robustness(
        decision,
        _scenarios(store, forecast, captain_volatility=True),
        forecast,
        universe,
        _ruleset(),
        replace(_policy(), max_ev_regret_tolerance=RationalValue.zero()),
    )
    assert report.status is ScenarioConvergenceStatus.CONVERGED
    assert report.checkpoints[-1].cvar_ranking[0] == decision.alternatives[0].action_id
    assert report.robust_preferred_action_id == decision.selected_action.action_id
    assert report.robust_preferred_ev_regret == RationalValue.zero()


def test_nonconverged_stream_is_inconclusive_not_stable(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    universe = _universe(store)
    report = evaluate_decision_robustness(
        _decision(forecast, universe),
        _scenarios(store, forecast, unstable_second_half=True),
        forecast,
        universe,
        _ruleset(),
        _policy(),
    )
    assert report.status is ScenarioConvergenceStatus.INCONCLUSIVE
    assert any("did not converge" in blocker for blocker in report.blockers)
    assert report.xp_reconciled is False
    assert report.robust_preferred_action_id is None
    assert report.robust_preferred_ev_regret is None


def test_future_convergence_policy_cannot_retroactively_govern_forecast(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    universe = _universe(store)
    future_policy = replace(
        _policy(),
        first_available_at="2026-08-25T00:00:00Z",
    )
    with pytest.raises(ValueError, match="not available at cutoff"):
        evaluate_decision_robustness(
            _decision(forecast, universe),
            _scenarios(store, forecast),
            forecast,
            universe,
            _ruleset(),
            future_policy,
        )


def test_missing_forecast_reconciliation_target_fails_closed(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    full = _forecast()
    incomplete = replace(full, rows=full.rows[:-1])
    universe = _universe(store)
    with pytest.raises(ValueError, match="Forecast misses scenario reconciliation target"):
        evaluate_decision_robustness(
            _decision(incomplete, universe),
            _scenarios(store, incomplete),
            incomplete,
            universe,
            _ruleset(),
            _policy(),
        )


def test_scenario_and_robustness_replay_preserve_semantic_identity(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    universe = _universe(store)
    scenario_set = _scenarios(store, forecast)
    stored_set = store_scenario_set(scenario_set, store=store)
    replayed_set = load_scenario_set(stored_set.artifact_id, store=store)
    assert replayed_set.scenario_set.scenario_set_id == scenario_set.scenario_set_id

    report = evaluate_decision_robustness(
        _decision(forecast, universe),
        scenario_set,
        forecast,
        universe,
        _ruleset(),
        _policy(),
    )
    stored_report = store_robustness_report(report, store=store)
    replayed_report = load_robustness_report(stored_report.artifact_id, store=store)
    assert replayed_report.report.robustness_report_id == report.robustness_report_id


def test_qualified_registry_requires_real_artifacts_and_champions(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    parameter = store.put_bytes(b"scenario-parameter").artifact_id
    generator = ScenarioGeneratorArtifact(
        generator_name="qualified-joint-generator",
        generator_version="1",
        generator_contract="joint-player-gameweek-v1",
        rng_algorithm="qualified-rng-v1",
        parameter_artifact_ids=(parameter,),
        qualification_state=ScenarioQualificationState.QUALIFIED,
        qualification_artifact_id=store.put_bytes(b"generator-placeholder").artifact_id,
        valid_seasons=("2026-2027",),
        trained_through="2026-08-20T00:00:00Z",
        first_available_at="2026-08-21T00:00:00Z",
        max_horizon_gameweeks=8,
    )
    generator = replace(
        generator,
        qualification_artifact_id=synthetic_supported_qualification_artifact(
            store=store,
            subject_payload=generator.semantic_payload(),
            subject_kind="apex.scenario-generator",
            proof_id=SCENARIO_GENERATOR_QUALIFICATION_ID,
            season="2026-2027",
        ),
    )
    policy = replace(
        _policy(),
        qualification_state=ScenarioQualificationState.QUALIFIED,
        qualification_artifact_id=store.put_bytes(b"policy-placeholder").artifact_id,
    )
    policy = replace(
        policy,
        qualification_artifact_id=synthetic_supported_qualification_artifact(
            store=store,
            subject_payload=policy.semantic_payload(),
            subject_kind="apex.scenario-policy",
            proof_id=SCENARIO_POLICY_QUALIFICATION_ID,
            season="2026-2027",
        ),
    )
    registry = ScenarioGovernanceRegistry(
        season="2026-2027",
        generators=(generator,),
        policies=(policy,),
        champion_generator_id=generator.scenario_generator_id,
        champion_policy_id=policy.scenario_policy_id,
    )
    as_of = "2026-08-24T06:00:00Z"
    registry.verify_generator_artifacts(
        generator,
        store=store,
        production=True,
        as_of=as_of,
    )
    registry.verify_policy_artifacts(
        policy,
        store=store,
        production=True,
        as_of=as_of,
    )

    empty_store = FileSystemArtifactStore(tmp_path / "missing")
    with pytest.raises(FileNotFoundError):
        registry.verify_generator_artifacts(
            generator,
            store=empty_store,
            production=True,
            as_of=as_of,
        )
