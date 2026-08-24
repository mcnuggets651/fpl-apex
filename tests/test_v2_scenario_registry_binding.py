from __future__ import annotations

from dataclasses import replace

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.scenario_registry import ScenarioGovernanceRegistry
from apex_fpl.core.decision import RationalValue
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
    FeatureSnapshotId,
    GlobalWorldId,
    ModelArtifactId,
    PredictionBatchId,
    RuleSetId,
    ScenarioGeneratorId,
)
from apex_fpl.core.scenarios import (
    JointPlayerGameweekOutcome,
    JointScenario,
    ScenarioConvergencePolicy,
    ScenarioGeneratorArtifact,
    ScenarioQualificationState,
    ScenarioSet,
)


def _forecast() -> Forecast:
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("scenario-binding-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("scenario-binding-world"),
        ruleset_id=RuleSetId("scenario-binding-rules"),
        model_artifact_id=ModelArtifactId("scenario-binding-model"),
        prediction_batch_id=PredictionBatchId("scenario-binding-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=(
            PlayerFixtureForecast(
                target=PlayerFixtureTarget(
                    fixture_id=1,
                    gameweek=2,
                    player_id=OfficialPlayerId(1),
                    team_id=1,
                    opponent_team_id=2,
                    is_home=True,
                    position="GK",
                ),
                prediction_row_id="scenario-binding-row",
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
            ),
        ),
        abstentions=(),
    )


def _generator(parameter_artifact_id: str, *, max_horizon: int = 8) -> ScenarioGeneratorArtifact:
    return ScenarioGeneratorArtifact(
        generator_name="binding-generator",
        generator_version="1",
        generator_contract="joint-player-gameweek-v1",
        rng_algorithm="binding-rng-v1",
        parameter_artifact_ids=(parameter_artifact_id,),
        qualification_state=ScenarioQualificationState.SHADOW,
        qualification_artifact_id=None,
        valid_seasons=("2026-2027",),
        trained_through="2026-08-20T00:00:00Z",
        first_available_at="2026-08-21T00:00:00Z",
        max_horizon_gameweeks=max_horizon,
    )


def _policy() -> ScenarioConvergencePolicy:
    return ScenarioConvergencePolicy(
        policy_name="binding-policy",
        policy_version="1",
        season="2026-2027",
        qualification_state=ScenarioQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-21T00:00:00Z",
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


def _scenario_set(
    store: FileSystemArtifactStore,
    forecast: Forecast,
    generator: ScenarioGeneratorArtifact,
    *,
    gameweeks: tuple[int, ...] = (2,),
) -> ScenarioSet:
    source = store.put_bytes(b"binding-worker-source").artifact_id
    outcomes = tuple(
        JointPlayerGameweekOutcome(
            player_id=OfficialPlayerId(1),
            gameweek=gameweek,
            appeared=True,
            points=5,
        )
        for gameweek in gameweeks
    )
    return ScenarioSet(
        season="2026-2027",
        forecast_id=forecast.forecast_id,
        scenario_generator_id=generator.scenario_generator_id,
        rng_algorithm=generator.rng_algorithm,
        seed=7,
        gameweeks=gameweeks,
        player_ids=(OfficialPlayerId(1),),
        scenarios=(JointScenario(ordinal=1, weight=1, outcomes=outcomes),),
        source_artifact_ids=(source,),
    )


def test_registry_runtime_contract_binds_generator_rng_forecast_and_sources(tmp_path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    parameter = store.put_bytes(b"binding-parameters").artifact_id
    forecast = _forecast()
    generator = _generator(parameter)
    policy = _policy()
    registry = ScenarioGovernanceRegistry(
        season="2026-2027",
        generators=(generator,),
        policies=(policy,),
    )
    scenario_set = _scenario_set(store, forecast, generator)

    registry.verify_runtime_contract(
        scenario_set,
        generator=generator,
        policy=policy,
        forecast=forecast,
        store=store,
        production=False,
    )

    with pytest.raises(ValueError, match="RNG identity"):
        registry.verify_runtime_contract(
            replace(scenario_set, rng_algorithm="different-rng"),
            generator=generator,
            policy=policy,
            forecast=forecast,
            store=store,
            production=False,
        )

    with pytest.raises(ValueError, match="generator identity"):
        registry.verify_runtime_contract(
            replace(
                scenario_set,
                scenario_generator_id=ScenarioGeneratorId("different-generator"),
            ),
            generator=generator,
            policy=policy,
            forecast=forecast,
            store=store,
            production=False,
        )


def test_registry_generator_horizon_uses_calendar_gameweek_span(tmp_path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    parameter = store.put_bytes(b"binding-parameters").artifact_id
    forecast = _forecast()
    generator = _generator(parameter, max_horizon=2)
    policy = _policy()
    registry = ScenarioGovernanceRegistry(
        season="2026-2027",
        generators=(generator,),
        policies=(policy,),
    )
    scenario_set = _scenario_set(store, forecast, generator, gameweeks=(2, 4))

    with pytest.raises(ValueError, match="outside generator validity scope"):
        registry.verify_runtime_contract(
            scenario_set,
            generator=generator,
            policy=policy,
            forecast=forecast,
            store=store,
            production=False,
        )
