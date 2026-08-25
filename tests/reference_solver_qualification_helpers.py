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
from apex_fpl.core.manager_state import ManagerState, ManagerStateScope, OwnedPlayer
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
    corpus_artifact_id: str
    qualification_artifact_id: str
    solver_certificate: ReferenceSolverCertificate
    worker: ReferenceSolverWorkerArtifact
    registry: ReferenceSolverRegistry


def ruleset():
    return load_ruleset(ROOT / "config/rules/2026-2027.yaml")


def _state(store: FileSystemArtifactStore) -> ManagerState:
    source = store.put_bytes(b"qualified-worker-manager-state").artifact_id
    return ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=ruleset().ruleset_id,
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
    source = store.put_bytes(b"qualified-worker-universe").artifact_id
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


def _forecast() -> Forecast:
    rows = tuple(
        PlayerFixtureForecast(
            target=PlayerFixtureTarget(
                fixture_id=3000 + player_id,
                gameweek=2,
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                opponent_team_id=100 + player_id,
                is_home=True,
                position=position,
            ),
            prediction_row_id=f"qualification-helper-{player_id}",
            minutes_distribution=DiscreteIntegerDistribution(((60, 5_000), (90, 5_000))),
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
        )
        for player_id, position in POSITIONS.items()
    )
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("qualification-helper-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=WORLD_ID,
        ruleset_id=ruleset().ruleset_id,
        model_artifact_id=ModelArtifactId("qualification-helper-model"),
        prediction_batch_id=PredictionBatchId("qualification-helper-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=rows,
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


def build_qualified_reference_solver_bundle(
    store: FileSystemArtifactStore,
) -> QualifiedReferenceSolverBundle:
    state = _state(store)
    universe = _universe(store)
    forecast = _forecast()
    policy = _policy()
    result = optimise_current_gameweek(
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=ruleset(),
        policy=policy,
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=0,
        chips_considered=(DecisionChip.NONE,),
        alternatives_limit=2,
    )
    decision_artifact = store_decision_result(result, store=store).artifact_id
    request = build_reference_solver_request(
        decision_input=result.decision_input,
        manager_state=state,
        forecast=forecast,
        candidate_universe=universe,
        ruleset=ruleset(),
        decision_policy=policy,
        max_search_nodes=100_000,
    )
    request_artifact = store_reference_solver_request(request, store=store).artifact_id
    case = ReferenceSolverQualificationCase(
        request_artifact_id=request_artifact,
        expected_decision_artifact_id=decision_artifact,
    )
    case_artifact = store_reference_solver_qualification_case(case, store=store)
    corpus = ReferenceSolverQualificationCorpus(
        season="2026-2027",
        horizon_gameweeks=1,
        solver_contract="apex-v2-exact-decision-parity-v1",
        case_artifact_ids=(case_artifact,),
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
    run = solve_reference_request(request)
    stored_run = store_reference_solver_run(run, store=store)
    solver_certificate = build_reference_solver_certificate(
        request_artifact_id=request_artifact,
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
        state=state,
        universe=universe,
        forecast=forecast,
        policy=policy,
        result=result,
        request_artifact_id=request_artifact,
        decision_artifact_id=decision_artifact,
        corpus_artifact_id=corpus_artifact,
        qualification_artifact_id=qualification_artifact,
        solver_certificate=solver_certificate,
        worker=worker,
        registry=registry,
    )
