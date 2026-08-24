from __future__ import annotations

import json
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.canonical import canonical_json_bytes
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
    JointPlayerGameweekOutcome,
    JointScenario,
    ScenarioConvergencePolicy,
    ScenarioConvergenceStatus,
    ScenarioQualificationState,
    ScenarioSet,
)
from apex_fpl.decision.robustness import evaluate_decision_robustness
from apex_fpl.decision.scenario_store import load_scenario_set, store_scenario_set


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
    source = store.put_bytes(b"scenario-adversarial-universe").artifact_id
    return CandidateUniverse(
        global_world_id=GlobalWorldId("scenario-adversarial-world"),
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
    rows = tuple(
        PlayerFixtureForecast(
            target=PlayerFixtureTarget(
                fixture_id=200 + player_id,
                gameweek=2,
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                opponent_team_id=200 + player_id,
                is_home=True,
                position=position,
            ),
            prediction_row_id=f"adversarial-row-{player_id}",
            minutes_distribution=DiscreteIntegerDistribution(((90, 10_000),)),
            points_distribution=DiscreteIntegerDistribution(((5, 10_000),)),
            uncertainty=ForecastUncertainty(
                uncertainty_kind=UncertaintyKind.PROBABILISTIC,
                deterministic_reason=None,
                scenario_count=1,
                minutes_p10=90,
                minutes_p50=90,
                minutes_p90=90,
                points_p10=5,
                points_p50=5,
                points_p90=5,
                appearance_probability_bps=10_000,
                sixty_plus_probability_bps=10_000,
            ),
        )
        for player_id, position in POSITIONS.items()
    )
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("scenario-adversarial-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("scenario-adversarial-world"),
        ruleset_id=_ruleset().ruleset_id,
        model_artifact_id=ModelArtifactId("scenario-adversarial-model"),
        prediction_batch_id=PredictionBatchId("scenario-adversarial-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=rows,
        abstentions=(),
    )


def _mechanics() -> DecisionMechanics:
    return DecisionMechanics(
        xi_points=RationalValue(55, 1),
        autosub_points=RationalValue.zero(),
        captain_bonus=RationalValue(5, 1),
        squad_points_if_bench_boost=RationalValue.zero(),
        points_before_hits=RationalValue(60, 1),
        hit_points=0,
        objective_points=RationalValue(60, 1),
    )


def _action() -> DecisionAction:
    return DecisionAction(
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
        mechanics=_mechanics(),
    )


def _decision(forecast: Forecast, universe: CandidateUniverse) -> DecisionResult:
    action = _action()
    zero = RationalValue.zero()
    decision_input = DecisionInput(
        manager_state_id=ManagerStateId("scenario-adversarial-state"),
        forecast_id=forecast.forecast_id,
        ruleset_id=_ruleset().ruleset_id,
        candidate_universe_id=universe.candidate_universe_id,
        decision_policy_id=DecisionPolicyId("scenario-adversarial-policy"),
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
        message="synthetic exact adversarial decision",
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
        selected_action=action,
        alternatives=(),
        solver=solver,
        exactness=exactness,
        enumerated_actions=1,
    )


def _scenario_set(
    store: FileSystemArtifactStore,
    forecast: Forecast,
    *,
    count: int,
) -> ScenarioSet:
    source = store.put_bytes(b"retained-worker-joint-scenario-bytes").artifact_id
    scenarios = tuple(
        JointScenario(
            ordinal=ordinal,
            weight=1,
            outcomes=tuple(
                JointPlayerGameweekOutcome(
                    player_id=OfficialPlayerId(player_id),
                    gameweek=2,
                    appeared=True,
                    points=5,
                )
                for player_id in range(1, 16)
            ),
        )
        for ordinal in range(1, count + 1)
    )
    return ScenarioSet(
        season="2026-2027",
        forecast_id=forecast.forecast_id,
        scenario_generator_id=ScenarioGeneratorId("adversarial-joint-generator"),
        rng_algorithm="sealed-worker-stream-v1",
        seed=20260824,
        gameweeks=(2,),
        player_ids=tuple(OfficialPlayerId(player_id) for player_id in range(1, 16)),
        scenarios=scenarios,
        source_artifact_ids=(source,),
    )


def _policy() -> ScenarioConvergencePolicy:
    return ScenarioConvergencePolicy(
        policy_name="adversarial-shadow-convergence",
        policy_version="1",
        season="2026-2027",
        qualification_state=ScenarioQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-24T00:00:00Z",
        checkpoint_counts=(256, 512),
        max_scenarios=512,
        cvar_alpha_bps=5_000,
        lower_quantile_bps=1_000,
        mean_tolerance=RationalValue.zero(),
        cvar_tolerance=RationalValue.zero(),
        tail_tolerance=RationalValue.zero(),
        xp_absolute_tolerance=RationalValue.zero(),
        sampling_sigma_multiplier=RationalValue.zero(),
        max_ev_regret_tolerance=RationalValue.zero(),
    )


def test_256_scenarios_is_floor_not_convergence_certificate(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    universe = _universe(store)
    report = evaluate_decision_robustness(
        _decision(forecast, universe),
        _scenario_set(store, forecast, count=256),
        forecast,
        universe,
        _ruleset(),
        _policy(),
    )
    assert report.status is ScenarioConvergenceStatus.INCONCLUSIVE
    assert report.robust_preferred_action_id is None
    assert report.robust_preferred_ev_regret is None
    assert report.blockers == (
        "insufficient nested scenario checkpoints for convergence",
    )


def test_scenario_replay_requires_retained_worker_source_artifact(tmp_path: Path) -> None:
    source_store = FileSystemArtifactStore(tmp_path / "source")
    forecast = _forecast()
    stored = store_scenario_set(
        _scenario_set(source_store, forecast, count=1),
        store=source_store,
    )
    envelope_bytes = source_store.read_bytes(stored.artifact_id)

    incomplete_store = FileSystemArtifactStore(tmp_path / "incomplete")
    copied = incomplete_store.put_bytes(envelope_bytes)
    assert copied.artifact_id == stored.artifact_id
    with pytest.raises(FileNotFoundError):
        load_scenario_set(copied.artifact_id, store=incomplete_store)


def test_scenario_replay_rejects_declared_semantic_identity_tampering(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    forecast = _forecast()
    stored = store_scenario_set(
        _scenario_set(store, forecast, count=1),
        store=store,
    )
    envelope = json.loads(store.read_bytes(stored.artifact_id).decode("utf-8"))
    envelope["scenario_set_id"] = "tampered-scenario-set-id"
    tampered = store.put_bytes(canonical_json_bytes(envelope))
    with pytest.raises(ValueError, match="semantic identity mismatch"):
        load_scenario_set(tampered.artifact_id, store=store)
