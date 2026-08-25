from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from apex_fpl.assurance.reference_mechanics import certify_selected_action
from apex_fpl.assurance.reference_solver_exchange import (
    build_reference_solver_certificate,
    build_reference_solver_request,
    store_reference_solver_request,
    store_reference_solver_run,
)
from apex_fpl.assurance.solver_parity import (
    build_independent_assurance_report,
    validate_reference_solver_parity,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.reference_solver_registry import ReferenceSolverRegistry
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.assurance import AssuranceParityStatus, ReferenceMechanicsCheck
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionChip,
    DecisionUseMode,
    RationalValue,
    SolverCertificate,
)
from apex_fpl.core.decision_policy import (
    TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    DecisionEvaluationMode,
    DecisionObjectivePolicy,
    DecisionPolicy,
    DecisionPolicyQualificationState,
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
from apex_fpl.core.ids import FeatureSnapshotId, GlobalWorldId, ModelArtifactId, PredictionBatchId
from apex_fpl.core.manager_state import ManagerState, ManagerStateScope, OwnedPlayer
from apex_fpl.core.reference_solver_io import (
    ReferenceSolverRun,
    ReferenceSolverRunStatus,
)
from apex_fpl.decision.engine import optimise_current_gameweek
from apex_fpl.workers.reference_solver import solve_reference_request


ROOT = Path(__file__).resolve().parents[1]
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
WORLD_ID = GlobalWorldId("assurance-world")


def _ruleset():
    return load_ruleset(ROOT / "config/rules/2026-2027.yaml")


def _state(store: FileSystemArtifactStore) -> ManagerState:
    source = store.put_bytes(b"assurance-manager-state-source").artifact_id
    return ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=_ruleset().ruleset_id,
        scope=ManagerStateScope.CURRENT_EXACT,
        bank_tenths=0,
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
            for player_id, position in POSITIONS.items()
        ),
        provenance_artifact_ids=(source,),
    )


def _universe(store: FileSystemArtifactStore) -> CandidateUniverse:
    source = store.put_bytes(b"assurance-candidate-universe").artifact_id
    return CandidateUniverse(
        global_world_id=WORLD_ID,
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


def _forecast(*, uncertain_high_player: int | None = None) -> Forecast:
    rows = []
    for player_id, position in POSITIONS.items():
        if player_id == uncertain_high_player:
            minutes = DiscreteIntegerDistribution(((0, 5_000), (90, 5_000)))
            points = DiscreteIntegerDistribution(((0, 5_000), (20, 5_000)))
            appearance = 5_000
            minutes_p10 = minutes_p50 = 0
            points_p10 = points_p50 = 0
            points_p90 = 20
        else:
            minutes = DiscreteIntegerDistribution(((60, 5_000), (90, 5_000)))
            points = DiscreteIntegerDistribution(((4, 5_000), (6, 5_000)))
            appearance = 10_000
            minutes_p10 = minutes_p50 = 60
            points_p10 = points_p50 = 4
            points_p90 = 6
        rows.append(
            PlayerFixtureForecast(
                target=PlayerFixtureTarget(
                    fixture_id=1000 + player_id,
                    gameweek=2,
                    player_id=OfficialPlayerId(player_id),
                    team_id=player_id,
                    opponent_team_id=100 + player_id,
                    is_home=True,
                    position=position,
                ),
                prediction_row_id=f"assurance-row-{player_id}",
                minutes_distribution=minutes,
                points_distribution=points,
                uncertainty=ForecastUncertainty(
                    uncertainty_kind=UncertaintyKind.PROBABILISTIC,
                    deterministic_reason=None,
                    scenario_count=2,
                    minutes_p10=minutes_p10,
                    minutes_p50=minutes_p50,
                    minutes_p90=90,
                    points_p10=points_p10,
                    points_p50=points_p50,
                    points_p90=points_p90,
                    appearance_probability_bps=appearance,
                    sixty_plus_probability_bps=appearance,
                ),
            )
        )
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("assurance-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=WORLD_ID,
        ruleset_id=_ruleset().ruleset_id,
        model_artifact_id=ModelArtifactId("assurance-model"),
        prediction_batch_id=PredictionBatchId("assurance-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=tuple(rows),
        abstentions=(),
    )


def _policy() -> DecisionPolicy:
    return DecisionPolicy(
        policy_name="assurance-tactical-reference",
        policy_version="1",
        season="2026-2027",
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-24T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.TACTICAL_CURRENT_GAMEWEEK,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=1,
        continuation_value_artifact_id=None,
        chip_option_value_artifact_id=None,
        price_policy_artifact_id=None,
        candidate_policy_artifact_id=None,
        tie_break_policy=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    )


def _decision(store: FileSystemArtifactStore, *, uncertain_high_player: int | None = None):
    state = _state(store)
    universe = _universe(store)
    forecast = _forecast(uncertain_high_player=uncertain_high_player)
    result = optimise_current_gameweek(
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=_ruleset(),
        policy=_policy(),
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=0,
        chips_considered=(DecisionChip.NONE,),
        alternatives_limit=2,
    )
    return state, universe, forecast, result


def _solver_certificate(
    store: FileSystemArtifactStore,
    *,
    state: ManagerState,
    universe: CandidateUniverse,
    forecast: Forecast,
    result,
    limited: bool = False,
):
    request = build_reference_solver_request(
        decision_input=result.decision_input,
        manager_state=state,
        forecast=forecast,
        candidate_universe=universe,
        ruleset=_ruleset(),
        decision_policy=_policy(),
        max_search_nodes=100_000,
    )
    stored_request = store_reference_solver_request(request, store=store)
    if limited:
        run = ReferenceSolverRun(
            request_id=request.request_id,
            solver_status=ReferenceSolverRunStatus.SOLVER_LIMIT,
            best_objective=None,
            best_bound=None,
            gap=None,
            selected_action_id=None,
            selected_action_json=None,
            action_surface_complete=False,
            tie_break_policy_id=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
            nodes_evaluated=1,
            actions_evaluated=0,
            limit_reason="synthetic mechanism-only search limit",
        )
    else:
        run = solve_reference_request(request)
        assert run.solver_status is ReferenceSolverRunStatus.OPTIMAL
    stored_run = store_reference_solver_run(run, store=store)
    worker_code = store.put_bytes(
        (ROOT / "src/apex_fpl/workers/reference_solver.py").read_bytes(),
        media_type="text/x-python",
    ).artifact_id
    return build_reference_solver_certificate(
        request_artifact_id=stored_request.artifact_id,
        run_artifact_id=stored_run.artifact_id,
        worker_name="apex-isolated-reference-solver",
        worker_version="1",
        worker_code_artifact_id=worker_code,
        store=store,
    )


def test_reference_mechanics_reconciles_selected_action_with_different_autosub_algorithm(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(store, uncertain_high_player=3)
    certificate = certify_selected_action(
        result,
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=_ruleset(),
    )
    assert certificate.passed is True
    assert certificate.recomputed_mechanics == result.selected_action.mechanics
    assert certificate.recomputed_bank_after_tenths == 0
    assert certificate.recomputed_hit_points == 0
    assert all(row.passed for row in certificate.checks)


def test_reference_mechanics_detects_self_consistent_objective_tampering(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(store)
    old = result.selected_action.mechanics
    plus_one = RationalValue(
        old.xi_points.numerator + old.xi_points.denominator,
        old.xi_points.denominator,
    )
    before = RationalValue(
        old.points_before_hits.numerator + old.points_before_hits.denominator,
        old.points_before_hits.denominator,
    )
    objective = RationalValue(
        old.objective_points.numerator + old.objective_points.denominator,
        old.objective_points.denominator,
    )
    tampered_mechanics = replace(
        old,
        xi_points=plus_one,
        points_before_hits=before,
        objective_points=objective,
    )
    tampered_action = replace(result.selected_action, mechanics=tampered_mechanics)
    tampered_solver = SolverCertificate(
        status=result.solver.status,
        incumbent_objective=objective,
        best_bound=objective,
        gap=RationalValue.zero(),
        numeric_error_bound=result.solver.numeric_error_bound,
        message="synthetic self-consistent tamper",
    )
    tampered_exactness = replace(result.exactness, best_bound=objective, gap=RationalValue.zero())
    tampered = replace(
        result,
        selected_action=tampered_action,
        solver=tampered_solver,
        exactness=tampered_exactness,
    )
    certificate = certify_selected_action(
        tampered,
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=_ruleset(),
    )
    checks = {row.check: row for row in certificate.checks}
    assert certificate.passed is False
    assert checks[ReferenceMechanicsCheck.EXPECTED_MECHANICS].passed is False


def test_solver_parity_replays_exact_worker_io_and_rejects_certificate_tampering(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(store)
    solver = _solver_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
    )
    status, blockers = validate_reference_solver_parity(
        result,
        solver,
        store=store,
        expected_tie_break_policy_id=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    )
    assert status is AssuranceParityStatus.PASS
    assert blockers == ()

    higher = RationalValue(
        result.selected_action.mechanics.objective_points.numerator
        + result.selected_action.mechanics.objective_points.denominator,
        result.selected_action.mechanics.objective_points.denominator,
    )
    mismatch = replace(solver, best_objective=higher, best_bound=higher)
    mismatch_status, mismatch_blockers = validate_reference_solver_parity(
        result,
        mismatch,
        store=store,
    )
    assert mismatch_status is AssuranceParityStatus.FAIL
    assert any("retained I/O failed replay" in row for row in mismatch_blockers)

    tie_mismatch = replace(solver, selected_action_id="sha256:" + "0" * 64)
    tie_status, tie_blockers = validate_reference_solver_parity(
        result,
        tie_mismatch,
        store=store,
        expected_tie_break_policy_id=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    )
    assert tie_status is AssuranceParityStatus.FAIL
    assert any("retained I/O failed replay" in row for row in tie_blockers)


def test_missing_or_limited_reference_solver_stays_inconclusive(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(store)
    mechanics = certify_selected_action(
        result,
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=_ruleset(),
    )
    missing = build_independent_assurance_report(result, mechanics, store=store)
    assert missing.publication_eligible is False
    assert missing.solver_parity_status is AssuranceParityStatus.INCONCLUSIVE
    assert any("absent" in blocker for blocker in missing.blockers)

    limited = _solver_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
        limited=True,
    )
    limited_report = build_independent_assurance_report(
        result,
        mechanics,
        store=store,
        solver=limited,
    )
    assert limited_report.publication_eligible is False
    assert limited_report.solver_parity_status is AssuranceParityStatus.INCONCLUSIVE


def test_unregistered_worker_cannot_make_assurance_publishable(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(store)
    mechanics = certify_selected_action(
        result,
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=_ruleset(),
    )
    solver = _solver_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
    )
    no_registry = build_independent_assurance_report(
        result,
        mechanics,
        store=store,
        solver=solver,
    )
    assert no_registry.publication_eligible is False
    assert no_registry.solver_parity_status is AssuranceParityStatus.INCONCLUSIVE

    empty_registry = ReferenceSolverRegistry(season="2026-2027", workers=())
    unregistered = build_independent_assurance_report(
        result,
        mechanics,
        store=store,
        solver=solver,
        worker_registry=empty_registry,
        season="2026-2027",
        decision_cutoff=forecast.feature_cutoff,
        horizon_gameweeks=1,
    )
    assert unregistered.publication_eligible is False
    assert unregistered.solver_parity_status is AssuranceParityStatus.INCONCLUSIVE
