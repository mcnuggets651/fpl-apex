from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from apex_fpl.acquisition import (
    FPL_BOOTSTRAP_URL,
    FPL_FIXTURES_URL,
    HttpResponse,
    acquire_official_global_world,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.experiment_registry import (
    ExperimentRegistration,
    ExperimentRegistry,
    derive_empirical_qualification_certificate,
    store_empirical_qualification_certificate,
    store_experiment_definition,
    store_experiment_registry,
    store_experiment_result,
)
from apex_fpl.control.feature_snapshot import build_and_store_feature_snapshot
from apex_fpl.control.forecast_model_registry import (
    ForecastModelRegistry,
    load_forecast_model_registry,
)
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.experiments import (
    ExactQualificationValue,
    ExperimentDefinition,
    ExperimentResult,
    QualificationMetricDirection,
    QualificationMetricResult,
    QualificationMetricRule,
    qualification_subject_id,
)
from apex_fpl.core.features import (
    FeatureObservation,
    FeatureScope,
    FeatureSnapshot,
    FeatureValue,
    FeatureValueKind,
)
from apex_fpl.core.forecast import (
    DiscreteIntegerDistribution,
    ForecastModelArtifact,
    ForecastUseMode,
    ModelQualificationState,
    PlayerFixtureScenario,
    PlayerFixtureTarget,
    PlayerMatchOutcome,
    PredictionBatch,
    PredictionDisposition,
    PredictionRow,
    UncertaintyKind,
    compile_prediction_row,
    score_match_outcome,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import FeatureSnapshotId, GlobalWorldId
from apex_fpl.forecast.engine import compile_sealed_forecast
from apex_fpl.forecast.forecast_store import load_forecast
from apex_fpl.forecast.prediction_store import store_prediction_batch
from apex_fpl.forecast.targets import build_official_forecast_targets
from apex_fpl.forecast.validation import validate_prediction_batch_safety


BOOTSTRAP = {
    "elements": [
        {
            "id": 1,
            "element_type": 3,
            "team": 1,
            "now_cost": 55,
            "web_name": "Alpha Mid",
        },
        {
            "id": 2,
            "element_type": 4,
            "team": 2,
            "now_cost": 70,
            "web_name": "Beta Fwd",
        },
    ],
    "teams": [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}],
    "events": [{"id": 1, "deadline_time": "2026-08-25T17:30:00Z"}],
}
FIXTURES = [{"id": 10, "team_h": 1, "team_a": 2, "event": 1}]


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class FixedClock:
    def __init__(self, stamp: datetime):
        self.stamp = stamp

    def now(self) -> datetime:
        return self.stamp


class FakeTransport:
    def __init__(self, *, bootstrap: object = BOOTSTRAP, fixtures: object = FIXTURES):
        self.payloads = {
            FPL_BOOTSTRAP_URL: _bytes(bootstrap),
            FPL_FIXTURES_URL: _bytes(fixtures),
        }

    def get(self, url: str, *, params: dict[str, str]) -> HttpResponse:
        assert params == {}
        return HttpResponse(
            status_code=200,
            body=self.payloads[url],
            headers={"Content-Type": "application/json", "ETag": '"forecast-test"'},
        )


def _ruleset():
    return load_ruleset(Path("config/rules/2026-2027.yaml"))


def _feature_snapshot(
    store: FileSystemArtifactStore,
    *,
    world_id: GlobalWorldId = GlobalWorldId("world"),
    source_artifact_id: str | None = None,
    cutoff: str = "2026-08-24T06:00:00Z",
) -> FeatureSnapshot:
    source = source_artifact_id or store.put_bytes(b"feature-source").artifact_id
    observation = FeatureObservation(
        feature_name="test.marker",
        scope=FeatureScope.GLOBAL,
        entity_id="global",
        value=FeatureValue(kind=FeatureValueKind.INTEGER, integer_value=1, unit="flag"),
        observed_at="2026-08-24T05:00:00Z",
        first_known_at="2026-08-24T05:00:00Z",
        source_artifact_ids=(source,),
        derivation_id="test.marker.v1",
    )
    return FeatureSnapshot(
        season="2026-2027",
        cutoff=cutoff,
        global_world_id=world_id,
        observations=(observation,),
        input_artifact_ids=(source,),
    )


def _typed_model_qualification(
    store: FileSystemArtifactStore,
    provisional: ForecastModelArtifact,
) -> str:
    evaluator = store.put_bytes(b"forecast-qualification-evaluator").artifact_id
    policy = store.put_bytes(b"forecast-qualification-policy").artifact_id
    source = store.put_bytes(b"forecast-qualification-source").artifact_id
    definition = ExperimentDefinition(
        proof_id="PO-FORECAST-QUALIFICATION-001",
        subject_kind="apex.forecast-model",
        subject_id=qualification_subject_id(provisional.semantic_payload()),
        season="2026-2027",
        evaluator_artifact_id=evaluator,
        policy_artifact_id=policy,
        declared_at="2026-08-20T00:00:00Z",
        evaluation_window_start="2026-08-21T00:00:00Z",
        evaluation_window_end="2026-08-23T00:00:00Z",
        minimum_sample_size=1,
        metric_rules=(
            QualificationMetricRule(
                "synthetic-calibration",
                QualificationMetricDirection.AT_LEAST,
                ExactQualificationValue(1, 1),
            ),
        ),
        valid_until="2027-05-31T23:59:59Z",
    )
    definition_ref = store_experiment_definition(definition, store=store)
    result = ExperimentResult(
        experiment_id=definition.experiment_id,
        proof_id=definition.proof_id,
        subject_kind=definition.subject_kind,
        subject_id=definition.subject_id,
        season=definition.season,
        evaluator_artifact_id=evaluator,
        evaluated_at="2026-08-23T00:00:00Z",
        sample_size=1,
        metrics=(
            QualificationMetricResult(
                "synthetic-calibration",
                ExactQualificationValue(1, 1),
            ),
        ),
        source_artifact_ids=(source,),
    )
    result_ref = store_experiment_result(result, store=store)
    registry_ref = store_experiment_registry(
        ExperimentRegistry(
            season="2026-2027",
            registrations=(
                ExperimentRegistration(definition.experiment_id, definition_ref.artifact_id),
            ),
        ),
        store=store,
    )
    certificate = derive_empirical_qualification_certificate(
        definition_artifact_id=definition_ref.artifact_id,
        result_artifact_id=result_ref.artifact_id,
        registry_artifact_id=registry_ref.artifact_id,
        store=store,
    )
    return store_empirical_qualification_certificate(certificate, store=store).artifact_id


def _model(
    store: FileSystemArtifactStore,
    *,
    state: ModelQualificationState = ModelQualificationState.QUALIFIED,
    trained_through: str = "2026-08-23T00:00:00Z",
    first_available_at: str = "2026-08-23T12:00:00Z",
    max_horizon: int = 8,
) -> ForecastModelArtifact:
    parameter = store.put_bytes(b"model-parameters").artifact_id
    if state is not ModelQualificationState.QUALIFIED:
        return ForecastModelArtifact(
            model_name="test-distribution-model",
            model_version="1",
            feature_contract="FeatureSnapshot.v1",
            prediction_contract="PredictionBatch.v1",
            parameter_artifact_ids=(parameter,),
            qualification_state=state,
            qualification_artifact_id=None,
            valid_seasons=("2026-2027",),
            trained_through=trained_through,
            first_available_at=first_available_at,
            max_horizon_gameweeks=max_horizon,
        )
    placeholder = store.put_bytes(b"qualification-placeholder").artifact_id
    provisional = ForecastModelArtifact(
        model_name="test-distribution-model",
        model_version="1",
        feature_contract="FeatureSnapshot.v1",
        prediction_contract="PredictionBatch.v1",
        parameter_artifact_ids=(parameter,),
        qualification_state=state,
        qualification_artifact_id=placeholder,
        valid_seasons=("2026-2027",),
        trained_through=trained_through,
        first_available_at=first_available_at,
        max_horizon_gameweeks=max_horizon,
    )
    qualification = _typed_model_qualification(store, provisional)
    return ForecastModelArtifact(
        model_name=provisional.model_name,
        model_version=provisional.model_version,
        feature_contract=provisional.feature_contract,
        prediction_contract=provisional.prediction_contract,
        parameter_artifact_ids=provisional.parameter_artifact_ids,
        qualification_state=state,
        qualification_artifact_id=qualification,
        valid_seasons=provisional.valid_seasons,
        trained_through=trained_through,
        first_available_at=first_available_at,
        max_horizon_gameweeks=max_horizon,
    )


def _probabilistic_row(target: PlayerFixtureTarget) -> PredictionRow:
    return PredictionRow(
        target=target,
        disposition=PredictionDisposition.PREDICTED,
        uncertainty_kind=UncertaintyKind.PROBABILISTIC,
        scenarios=(
            PlayerFixtureScenario(
                scenario_id="no-show",
                probability_bps=4_000,
                outcome=PlayerMatchOutcome(minutes=0),
            ),
            PlayerFixtureScenario(
                scenario_id="full-match-goal",
                probability_bps=6_000,
                outcome=PlayerMatchOutcome(minutes=90, goals=1),
            ),
        ),
    )


def _batch(
    *,
    snapshot: FeatureSnapshot,
    model: ForecastModelArtifact,
    targets: tuple[PlayerFixtureTarget, ...],
    rows: tuple[PredictionRow, ...] | None = None,
) -> PredictionBatch:
    return PredictionBatch(
        season=snapshot.season,
        feature_snapshot_id=snapshot.snapshot_id,
        feature_cutoff=snapshot.cutoff,
        global_world_id=snapshot.global_world_id,
        model_artifact_id=model.model_artifact_id,
        gameweeks=(1,),
        rows=rows or tuple(_probabilistic_row(target) for target in targets),
    )


def _sealed_fixture(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    sealed = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 24, 5, tzinfo=timezone.utc)),
        store=store,
    )
    snapshot = _feature_snapshot(
        store,
        world_id=sealed.world.world_id,
        source_artifact_id=sealed.manifest_artifact_id,
    )
    stored_snapshot = build_and_store_feature_snapshot(
        season=snapshot.season,
        cutoff=snapshot.cutoff,
        global_world_id=snapshot.global_world_id,
        observations=snapshot.observations,
        input_artifact_ids=snapshot.input_artifact_ids,
        store=store,
    )
    targets = build_official_forecast_targets(
        global_world_manifest_artifact_id=sealed.manifest_artifact_id,
        feature_snapshot=snapshot,
        gameweeks=(1,),
        store=store,
    )
    return store, sealed, stored_snapshot, targets


def test_discrete_distribution_is_exact_and_rejects_unbalanced_probability_mass():
    distribution = DiscreteIntegerDistribution(((90, 6_000), (0, 4_000)))
    assert distribution.support == ((0, 4_000), (90, 6_000))
    assert distribution.expectation_numerator == 540_000
    assert distribution.quantile(1_000) == 0
    assert distribution.quantile(5_000) == 90
    assert distribution.probability_at_least(60) == 6_000
    with pytest.raises(ValueError, match="probability mass"):
        DiscreteIntegerDistribution(((0, 5_000), (90, 4_999)))


def test_ruleset_scoring_boundaries_are_applied_independently_of_model_xp():
    ruleset = _ruleset()
    assert score_match_outcome(
        ruleset=ruleset,
        position="MID",
        outcome=PlayerMatchOutcome(minutes=59, goals=1, assists=1, yellow_cards=1),
    ) == 8
    assert score_match_outcome(
        ruleset=ruleset,
        position="MID",
        outcome=PlayerMatchOutcome(
            minutes=60,
            goals_conceded_while_on_pitch=0,
            defensive_contributions=12,
        ),
    ) == 5
    assert score_match_outcome(
        ruleset=ruleset,
        position="GK",
        outcome=PlayerMatchOutcome(
            minutes=90,
            goals_conceded_while_on_pitch=2,
            goalkeeper_saves=7,
            penalty_saves=1,
            bonus_points=3,
        ),
    ) == 11
    assert score_match_outcome(
        ruleset=ruleset,
        position="DEF",
        outcome=PlayerMatchOutcome(
            minutes=90,
            goals=1,
            goals_conceded_while_on_pitch=0,
            defensive_contributions=10,
            own_goals=1,
        ),
    ) == 12


def test_model_scenarios_compile_to_exact_minutes_and_points_distributions():
    target = PlayerFixtureTarget(
        fixture_id=10,
        gameweek=1,
        player_id=OfficialPlayerId(1),
        team_id=1,
        opponent_team_id=2,
        is_home=True,
        position="MID",
    )
    forecast = compile_prediction_row(_probabilistic_row(target), ruleset=_ruleset())
    assert not hasattr(forecast, "reason")
    assert forecast.minutes_distribution.support == ((0, 4_000), (90, 6_000))
    assert forecast.points_distribution.support == ((0, 4_000), (8, 6_000))
    assert forecast.expected_points_numerator == 48_000
    assert forecast.uncertainty.appearance_probability_bps == 6_000
    assert forecast.uncertainty.sixty_plus_probability_bps == 6_000
    assert forecast.uncertainty.points_p10 == 0
    assert forecast.uncertainty.points_p90 == 8


def test_prediction_contract_rejects_fake_deterministic_90_and_impossible_zero_minute_events():
    target = PlayerFixtureTarget(10, 1, OfficialPlayerId(1), 1, 2, True, "MID")
    fake_nailed = PredictionRow(
        target=target,
        disposition=PredictionDisposition.PREDICTED,
        uncertainty_kind=UncertaintyKind.STRUCTURALLY_DETERMINISTIC,
        deterministic_reason="NAILED_90",
        scenarios=(
            PlayerFixtureScenario("certain", 10_000, PlayerMatchOutcome(minutes=90)),
        ),
    )
    batch = PredictionBatch(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("world"),
        model_artifact_id=_model(FileSystemArtifactStore(Path("/tmp/apex-test-fake-model"))).model_artifact_id,
        gameweeks=(1,),
        rows=(fake_nailed,),
    )
    with pytest.raises(ValueError, match="structural determinism"):
        validate_prediction_batch_safety(batch)

    impossible = PredictionRow(
        target=target,
        disposition=PredictionDisposition.PREDICTED,
        uncertainty_kind=UncertaintyKind.PROBABILISTIC,
        scenarios=(
            PlayerFixtureScenario("impossible", 5_000, PlayerMatchOutcome(minutes=0, goals=1)),
            PlayerFixtureScenario("plays", 5_000, PlayerMatchOutcome(minutes=90)),
        ),
    )
    bad = PredictionBatch(
        season=batch.season,
        feature_snapshot_id=batch.feature_snapshot_id,
        feature_cutoff=batch.feature_cutoff,
        global_world_id=batch.global_world_id,
        model_artifact_id=batch.model_artifact_id,
        gameweeks=(1,),
        rows=(impossible,),
    )
    with pytest.raises(ValueError, match="zero-minute scenario"):
        validate_prediction_batch_safety(bad)


def test_official_suspension_can_be_structural_zero_without_claiming_general_football_certainty(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    model = _model(store)
    target = PlayerFixtureTarget(10, 1, OfficialPlayerId(1), 1, 2, True, "MID")
    row = PredictionRow(
        target=target,
        disposition=PredictionDisposition.PREDICTED,
        uncertainty_kind=UncertaintyKind.STRUCTURALLY_DETERMINISTIC,
        deterministic_reason="OFFICIAL_SUSPENSION",
        scenarios=(PlayerFixtureScenario("suspended", 10_000, PlayerMatchOutcome(minutes=0)),),
    )
    batch = PredictionBatch(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("world"),
        model_artifact_id=model.model_artifact_id,
        gameweeks=(1,),
        rows=(row,),
    )
    validate_prediction_batch_safety(batch)


def test_no_hindsight_model_validity_blocks_future_training_and_future_model_availability(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    future_training = _model(
        store,
        trained_through="2026-08-25T00:00:00Z",
        first_available_at="2026-08-25T01:00:00Z",
    )
    with pytest.raises(ValueError, match="training data leaks"):
        future_training.require_valid_for(
            season="2026-2027",
            feature_cutoff="2026-08-24T06:00:00Z",
            horizon_gameweeks=1,
            production=False,
        )
    future_release = _model(
        store,
        trained_through="2026-08-23T00:00:00Z",
        first_available_at="2026-08-25T01:00:00Z",
    )
    with pytest.raises(ValueError, match="not available"):
        future_release.require_valid_for(
            season="2026-2027",
            feature_cutoff="2026-08-24T06:00:00Z",
            horizon_gameweeks=1,
            production=False,
        )


def test_registry_has_no_fabricated_default_champion_and_unqualified_model_cannot_produce(tmp_path: Path):
    configured = load_forecast_model_registry(Path("config/forecast_models_v2.yaml"))
    assert configured.models == ()
    assert configured.champion() is None

    store = FileSystemArtifactStore(tmp_path / "artifacts")
    shadow = _model(store, state=ModelQualificationState.SHADOW)
    registry = ForecastModelRegistry(models=(shadow,))
    with pytest.raises(ValueError, match="not QUALIFIED"):
        registry.verify_model_artifacts(shadow, store=store, production=True)


def test_prediction_batch_requires_exact_official_target_coverage():
    first = PlayerFixtureTarget(10, 1, OfficialPlayerId(1), 1, 2, True, "MID")
    second = PlayerFixtureTarget(10, 1, OfficialPlayerId(2), 2, 1, False, "FWD")
    store = FileSystemArtifactStore(Path("/tmp/apex-test-coverage-model"))
    model = _model(store)
    batch = PredictionBatch(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("world"),
        model_artifact_id=model.model_artifact_id,
        gameweeks=(1,),
        rows=(_probabilistic_row(first),),
    )
    with pytest.raises(ValueError, match="coverage mismatch"):
        batch.require_exact_target_coverage((first, second))


def test_shadow_forecast_compiles_and_replays_but_is_not_production_eligible(tmp_path: Path):
    store, sealed, stored_snapshot, targets = _sealed_fixture(tmp_path)
    model = _model(store, state=ModelQualificationState.SHADOW)
    batch = _batch(snapshot=stored_snapshot.snapshot, model=model, targets=targets.targets)
    stored_batch = store_prediction_batch(batch, store=store)
    registry = ForecastModelRegistry(models=(model,))

    compiled = compile_sealed_forecast(
        feature_snapshot_artifact_id=stored_snapshot.artifact_id,
        prediction_batch_artifact_id=stored_batch.artifact_id,
        global_world_manifest_artifact_id=sealed.manifest_artifact_id,
        ruleset=_ruleset(),
        model_registry=registry,
        use_mode=ForecastUseMode.SHADOW,
        store=store,
    )
    replay = load_forecast(compiled.artifact_id, store=store)
    assert replay.forecast.forecast_id == compiled.forecast.forecast_id
    assert replay.forecast.production_eligible is False
    assert len(replay.forecast.rows) == 2
    assert replay.forecast.abstentions == ()


def test_production_forecast_requires_qualified_registered_champion_and_complete_predictions(tmp_path: Path):
    store, sealed, stored_snapshot, targets = _sealed_fixture(tmp_path)
    model = _model(store, state=ModelQualificationState.QUALIFIED)
    registry = ForecastModelRegistry(
        models=(model,),
        champion_model_id=model.model_artifact_id,
    )
    batch = _batch(snapshot=stored_snapshot.snapshot, model=model, targets=targets.targets)
    stored_batch = store_prediction_batch(batch, store=store)
    compiled = compile_sealed_forecast(
        feature_snapshot_artifact_id=stored_snapshot.artifact_id,
        prediction_batch_artifact_id=stored_batch.artifact_id,
        global_world_manifest_artifact_id=sealed.manifest_artifact_id,
        ruleset=_ruleset(),
        model_registry=registry,
        use_mode=ForecastUseMode.PRODUCTION,
        store=store,
    )
    assert compiled.forecast.production_eligible is True
    assert len(compiled.forecast.rows) == 2

    abstained = PredictionRow(
        target=targets.targets[0],
        disposition=PredictionDisposition.ABSTAINED,
        abstention_reason="insufficient calibrated evidence",
    )
    rows = (abstained,) + tuple(
        _probabilistic_row(target) for target in targets.targets[1:]
    )
    incomplete = _batch(
        snapshot=stored_snapshot.snapshot,
        model=model,
        targets=targets.targets,
        rows=rows,
    )
    incomplete_artifact = store_prediction_batch(incomplete, store=store)
    with pytest.raises(ValueError, match="cannot omit/abstain"):
        compile_sealed_forecast(
            feature_snapshot_artifact_id=stored_snapshot.artifact_id,
            prediction_batch_artifact_id=incomplete_artifact.artifact_id,
            global_world_manifest_artifact_id=sealed.manifest_artifact_id,
            ruleset=_ruleset(),
            model_registry=registry,
            use_mode=ForecastUseMode.PRODUCTION,
            store=store,
        )


def test_forecast_target_builder_rejects_later_world_or_later_capture(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    early = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 24, 5, tzinfo=timezone.utc)),
        store=store,
    )
    snapshot = _feature_snapshot(
        store,
        world_id=early.world.world_id,
        source_artifact_id=early.manifest_artifact_id,
        cutoff="2026-08-24T06:00:00Z",
    )
    late_fixtures = [{"id": 10, "team_h": 2, "team_a": 1, "event": 1}]
    late = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(fixtures=late_fixtures),
        clock=FixedClock(datetime(2026, 8, 24, 7, tzinfo=timezone.utc)),
        store=store,
    )
    with pytest.raises(ValueError, match="does not match FeatureSnapshot"):
        build_official_forecast_targets(
            global_world_manifest_artifact_id=late.manifest_artifact_id,
            feature_snapshot=snapshot,
            gameweeks=(1,),
            store=store,
        )


def test_model_horizon_uses_calendar_span_not_number_of_selected_gameweeks(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    model = _model(store, max_horizon=2)
    with pytest.raises(ValueError, match="outside model validity"):
        model.require_valid_for(
            season="2026-2027",
            feature_cutoff="2026-08-24T06:00:00Z",
            horizon_gameweeks=8,
            production=False,
        )
