from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from apex_fpl.assurance.reference_solver_exchange import (
    build_reference_solver_certificate,
    build_reference_solver_request,
    store_reference_solver_request,
    store_reference_solver_run,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.reference_solver_qualification import (
    derive_reference_solver_algorithmic_qualification,
    store_reference_solver_algorithmic_qualification,
    store_reference_solver_qualification_case,
    store_reference_solver_qualification_corpus,
)
from apex_fpl.control.reference_solver_registry import ReferenceSolverRegistry
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.assurance import ReferenceSolverCertificate
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionChip,
    DecisionResult,
    DecisionUseMode,
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
from apex_fpl.core.manager_state import (
    ManagerState,
    ManagerStateScope,
    OwnedPlayer,
    calculate_selling_price_tenths,
)
from apex_fpl.core.reference_solver_qualification import (
    ReferenceSolverQualificationCase,
    ReferenceSolverQualificationCorpus,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)
from apex_fpl.decision.engine import optimise_current_gameweek
from apex_fpl.decision.store import store_decision_result
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
WORLD_ID = GlobalWorldId("qualification-helper-world")


@dataclass(frozen=True, slots=True)
class QualifiedReferenceSolverBundle:
    state: ManagerState
    universe: CandidateUniverse
    forecast: Forecast
    policy: DecisionPolicy
    result: DecisionResult
    request_artifact_id: str
    decision_artifact_id: str
    case_artifact_ids: tuple[str, ...]
    corpus_artifact_id: str
    qualification_artifact_id: str
    solver_certificate: ReferenceSolverCertificate
    worker: ReferenceSolverWorkerArtifact
    registry: ReferenceSolverRegistry


def ruleset():
    return load_ruleset(ROOT / "config/rules/2026-2027.yaml")


def _state(
    store: FileSystemArtifactStore,
    *,
    label: str,
    bank_tenths: int = 0,
    free_transfers: int = 1,
    purchase_basis_tenths: int = 50,
    current_price_tenths: int = 50,
) -> ManagerState:
    source = store.put_bytes(f"qualified-worker-manager-state:{label}".encode()).artifact_id
    selling = calculate_selling_price_tenths(
        purchase_basis_tenths,
        current_price_tenths,
        ruleset=ruleset(),
    )
    return ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=ruleset().ruleset_id,
        scope=ManagerStateScope.CURRENT_EXACT,
        bank_tenths=bank_tenths,
        free_transfers=free_transfers,
        squad=tuple(
            OwnedPlayer(
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                position=position,
                purchase_basis_tenths=purchase_basis_tenths,
                current_price_tenths=current_price_tenths,
                selling_price_tenths=selling,
            )
            for player_id, position in POSITIONS.items()
        ),
        provenance_artifact_ids=(source,),
    )


def _universe(
    store: FileSystemArtifactStore,
    *,
    label: str,
    base_price_tenths: int = 50,
    extra_mid_prices: tuple[tuple[int, int], ...] = (),
) -> CandidateUniverse:
    source = store.put_bytes(f"qualified-worker-universe:{label}".encode()).artifact_id
    players = [
        CandidatePlayer(
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            position=position,
            current_price_tenths=base_price_tenths,
        )
        for player_id, position in POSITIONS.items()
    ]
    players.extend(
        CandidatePlayer(
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            position="MID",
            current_price_tenths=price,
        )
        for player_id, price in extra_mid_prices
    )
    return CandidateUniverse(
        global_world_id=WORLD_ID,
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=tuple(players),
        official_player_count=len(players),
        source_artifact_ids=(source,),
    )


def _row(
    *,
    player_id: int,
    position: str,
    fixture_id: int,
    points_low: int,
    points_high: int,
    appearance_bps: int = 10_000,
) -> PlayerFixtureForecast:
    minutes = (
        DiscreteIntegerDistribution(((60, 5_000), (90, 5_000)))
        if appearance_bps == 10_000
        else DiscreteIntegerDistribution(
            ((0, 10_000 - appearance_bps), (90, appearance_bps))
        )
    )
    points = (
        DiscreteIntegerDistribution(((points_low, 10_000),))
        if points_low == points_high
        else DiscreteIntegerDistribution(((points_low, 5_000), (points_high, 5_000)))
    )
    return PlayerFixtureForecast(
        target=PlayerFixtureTarget(
            fixture_id=fixture_id,
            gameweek=2,
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            opponent_team_id=100 + player_id,
            is_home=True,
            position=position,
        ),
        prediction_row_id=f"qualification-helper-{fixture_id}-{player_id}",
        minutes_distribution=minutes,
        points_distribution=points,
        uncertainty=ForecastUncertainty(
            uncertainty_kind=UncertaintyKind.PROBABILISTIC,
            deterministic_reason=None,
            scenario_count=2,
            minutes_p10=0 if appearance_bps < 9_000 else 60,
            minutes_p50=0 if appearance_bps <= 5_000 else 60,
            minutes_p90=90,
            points_p10=points_low,
            points_p50=points_low,
            points_p90=points_high,
            appearance_probability_bps=appearance_bps,
            sixty_plus_probability_bps=appearance_bps,
        ),
    )


def _forecast(
    *,
    label: str,
    extra_mid_points: tuple[tuple[int, tuple[int, int]], ...] = (),
    uncertain_player: int | None = None,
    double_gameweek_player: int | None = None,
    point_overrides: tuple[tuple[int, tuple[int, int]], ...] = (),
) -> Forecast:
    points = dict(point_overrides)
    points.update(dict(extra_mid_points))
    positions = dict(POSITIONS)
    for player_id, _ in extra_mid_points:
        positions[player_id] = "MID"
    rows: list[PlayerFixtureForecast] = []
    for player_id, position in positions.items():
        low, high = points.get(player_id, (4, 6))
        rows.append(
            _row(
                player_id=player_id,
                position=position,
                fixture_id=3000 + player_id,
                points_low=low,
                points_high=high,
                appearance_bps=5_000 if player_id == uncertain_player else 10_000,
            )
        )
        if player_id == double_gameweek_player:
            rows.append(
                _row(
                    player_id=player_id,
                    position=position,
                    fixture_id=4000 + player_id,
                    points_low=3,
                    points_high=7,
                    appearance_bps=7_500,
                )
            )
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId(f"qualification-helper-feature-{label}"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=WORLD_ID,
        ruleset_id=ruleset().ruleset_id,
        model_artifact_id=ModelArtifactId(f"qualification-helper-model-{label}"),
        prediction_batch_id=PredictionBatchId(f"qualification-helper-batch-{label}"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=tuple(rows),
        abstentions=(),
    )


def _policy() -> DecisionPolicy:
    return DecisionPolicy(
        policy_name="qualification-helper-tactical",
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


def _seal_case(
    store: FileSystemArtifactStore,
    *,
    state: ManagerState,
    universe: CandidateUniverse,
    forecast: Forecast,
    policy: DecisionPolicy,
    max_normal_transfers: int,
    chips_considered: tuple[DecisionChip, ...],
    alternatives_limit: int = 5,
    max_search_nodes: int = 100_000,
) -> tuple[DecisionResult, str, str, str]:
    result = optimise_current_gameweek(
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=ruleset(),
        policy=policy,
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=max_normal_transfers,
        chips_considered=chips_considered,
        alternatives_limit=alternatives_limit,
    )
    decision_artifact = store_decision_result(result, store=store).artifact_id
    request = build_reference_solver_request(
        decision_input=result.decision_input,
        manager_state=state,
        forecast=forecast,
        candidate_universe=universe,
        ruleset=ruleset(),
        decision_policy=policy,
        max_search_nodes=max_search_nodes,
    )
    request_artifact = store_reference_solver_request(request, store=store).artifact_id
    case = ReferenceSolverQualificationCase(
        request_artifact_id=request_artifact,
        expected_decision_artifact_id=decision_artifact,
    )
    case_artifact = store_reference_solver_qualification_case(case, store=store)
    return result, request_artifact, decision_artifact, case_artifact


def build_qualified_reference_solver_bundle(
    store: FileSystemArtifactStore,
) -> QualifiedReferenceSolverBundle:
    policy = _policy()

    baseline_state = _state(store, label="autosub-dgw")
    baseline_universe = _universe(store, label="autosub-dgw")
    baseline_forecast = _forecast(
        label="autosub-dgw",
        uncertain_player=9,
        double_gameweek_player=10,
        point_overrides=((9, (18, 22)), (10, (10, 14))),
    )
    baseline_result, baseline_request, baseline_decision, baseline_case = _seal_case(
        store,
        state=baseline_state,
        universe=baseline_universe,
        forecast=baseline_forecast,
        policy=policy,
        max_normal_transfers=0,
        chips_considered=(DecisionChip.NONE,),
    )
    if OfficialPlayerId(9) not in baseline_result.selected_action.xi_ids:
        raise AssertionError("qualification autosub case failed to select uncertain player")
    if OfficialPlayerId(10) not in baseline_result.selected_action.xi_ids:
        raise AssertionError("qualification DGW case failed to select double-gameweek player")

    finance_state = _state(
        store,
        label="finance-tie",
        bank_tenths=1,
        free_transfers=0,
        purchase_basis_tenths=40,
        current_price_tenths=50,
    )
    finance_universe = _universe(
        store,
        label="finance-tie",
        extra_mid_prices=((16, 46), (17, 46)),
    )
    finance_forecast = _forecast(
        label="finance-tie",
        extra_mid_points=((16, (20, 20)), (17, (20, 20))),
        point_overrides=((8, (0, 2)),),
    )
    finance_result, _, _, finance_case = _seal_case(
        store,
        state=finance_state,
        universe=finance_universe,
        forecast=finance_forecast,
        policy=policy,
        max_normal_transfers=1,
        chips_considered=(DecisionChip.NONE,),
    )
    if not finance_result.selected_action.transfers:
        raise AssertionError("qualification finance case failed to exercise a transfer")
    if finance_result.selected_action.mechanics.hit_points <= 0:
        raise AssertionError("qualification finance case failed to exercise paid hit")
    selected_objective = finance_result.selected_action.mechanics.objective_points
    if not any(
        row.action_id != finance_result.selected_action.action_id
        and row.mechanics.objective_points == selected_objective
        for row in finance_result.alternatives
    ):
        raise AssertionError("qualification finance case failed to create equal-objective tie")

    chip_state = _state(store, label="chips")
    chip_universe = _universe(store, label="chips")
    chip_forecast = _forecast(label="chips")
    _, _, _, chip_case = _seal_case(
        store,
        state=chip_state,
        universe=chip_universe,
        forecast=chip_forecast,
        policy=policy,
        max_normal_transfers=0,
        chips_considered=(
            DecisionChip.NONE,
            DecisionChip.TRIPLE_CAPTAIN,
            DecisionChip.BENCH_BOOST,
            DecisionChip.WILDCARD,
            DecisionChip.FREE_HIT,
        ),
        max_search_nodes=250_000,
    )

    case_artifacts = (baseline_case, finance_case, chip_case)
    corpus = ReferenceSolverQualificationCorpus(
        season="2026-2027",
        horizon_gameweeks=1,
        solver_contract="apex-v2-exact-decision-parity-v1",
        case_artifact_ids=case_artifacts,
    )
    corpus_artifact = store_reference_solver_qualification_corpus(corpus, store=store)
    worker_code = store.put_bytes(
        (ROOT / "src/apex_fpl/workers/reference_solver.py").read_bytes(),
        media_type="text/x-python",
    ).artifact_id
    shadow_worker = ReferenceSolverWorkerArtifact(
        worker_name="apex-isolated-reference-solver",
        worker_version="1",
        solver_contract="apex-v2-exact-decision-parity-v1",
        code_artifact_id=worker_code,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
        valid_seasons=("2026-2027",),
        first_available_at="2026-08-24T00:00:00Z",
        max_horizon_gameweeks=1,
    )
    qualification = derive_reference_solver_algorithmic_qualification(
        shadow_worker,
        corpus_artifact_id=corpus_artifact,
        store=store,
    )
    qualification_artifact = store_reference_solver_algorithmic_qualification(
        qualification,
        store=store,
    )
    worker = replace(
        shadow_worker,
        qualification_state=ReferenceSolverWorkerQualification.QUALIFIED,
        qualification_artifact_id=qualification_artifact,
    )

    baseline_request_object = build_reference_solver_request(
        decision_input=baseline_result.decision_input,
        manager_state=baseline_state,
        forecast=baseline_forecast,
        candidate_universe=baseline_universe,
        ruleset=ruleset(),
        decision_policy=policy,
        max_search_nodes=100_000,
    )
    if store_reference_solver_request(baseline_request_object, store=store).artifact_id != baseline_request:
        raise AssertionError("qualification baseline request did not replay to identical artifact")
    run = solve_reference_request(baseline_request_object)
    stored_run = store_reference_solver_run(run, store=store)
    solver_certificate = build_reference_solver_certificate(
        request_artifact_id=baseline_request,
        run_artifact_id=stored_run.artifact_id,
        worker_name=worker.worker_name,
        worker_version=worker.worker_version,
        worker_code_artifact_id=worker.code_artifact_id,
        store=store,
    )
    registry = ReferenceSolverRegistry(
        season="2026-2027",
        workers=(worker,),
        champion_worker_id=worker.worker_id,
    )
    return QualifiedReferenceSolverBundle(
        state=baseline_state,
        universe=baseline_universe,
        forecast=baseline_forecast,
        policy=policy,
        result=baseline_result,
        request_artifact_id=baseline_request,
        decision_artifact_id=baseline_decision,
        case_artifact_ids=case_artifacts,
        corpus_artifact_id=corpus_artifact,
        qualification_artifact_id=qualification_artifact,
        solver_certificate=solver_certificate,
        worker=worker,
        registry=registry,
    )