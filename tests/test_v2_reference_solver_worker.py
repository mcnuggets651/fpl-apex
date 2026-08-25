from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.assurance.reference_solver_exchange import (
    build_reference_solver_certificate,
    build_reference_solver_request,
    store_reference_solver_request,
    store_reference_solver_run,
    verify_reference_solver_certificate_io,
)
from apex_fpl.assurance.solver_parity import validate_reference_solver_parity
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.assurance import AssuranceParityStatus
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionChip,
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
from apex_fpl.core.ids import (
    FeatureSnapshotId,
    GlobalWorldId,
    ModelArtifactId,
    PredictionBatchId,
)
from apex_fpl.core.manager_state import (
    ManagerState,
    ManagerStateScope,
    OwnedPlayer,
    calculate_selling_price_tenths,
)
from apex_fpl.core.reference_solver_io import ReferenceSolverRunStatus
from apex_fpl.decision.engine import optimise_current_gameweek
from apex_fpl.workers.reference_solver import solve_reference_request


ROOT = Path(__file__).resolve().parents[1]
WORLD_ID = GlobalWorldId("reference-solver-worker-world")
BASE_POSITIONS = {
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
    return load_ruleset(ROOT / "config/rules/2026-2027.yaml")


def _policy() -> DecisionPolicy:
    return DecisionPolicy(
        policy_name="reference-worker-tactical",
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


def _state(
    store: FileSystemArtifactStore,
    *,
    bank_tenths: int = 0,
    free_transfers: int = 1,
    purchase_basis_tenths: int = 50,
    current_price_tenths: int = 50,
) -> ManagerState:
    source = store.put_bytes(b"reference-worker-manager-state").artifact_id
    ruleset = _ruleset()
    selling = calculate_selling_price_tenths(
        purchase_basis_tenths,
        current_price_tenths,
        ruleset=ruleset,
    )
    return ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=ruleset.ruleset_id,
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
            for player_id, position in BASE_POSITIONS.items()
        ),
        provenance_artifact_ids=(source,),
    )


def _universe(
    store: FileSystemArtifactStore,
    *,
    extra_mid_price_tenths: int | None = None,
) -> CandidateUniverse:
    source = store.put_bytes(b"reference-worker-candidate-universe").artifact_id
    players = [
        CandidatePlayer(
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            position=position,
            current_price_tenths=50,
        )
        for player_id, position in BASE_POSITIONS.items()
    ]
    if extra_mid_price_tenths is not None:
        players.append(
            CandidatePlayer(
                player_id=OfficialPlayerId(16),
                team_id=16,
                position="MID",
                current_price_tenths=extra_mid_price_tenths,
            )
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
    if appearance_bps == 10_000:
        minutes = DiscreteIntegerDistribution(((60, 5_000), (90, 5_000)))
    else:
        minutes = DiscreteIntegerDistribution(
            ((0, 10_000 - appearance_bps), (90, appearance_bps))
        )
    points = DiscreteIntegerDistribution(((points_low, 5_000), (points_high, 5_000)))
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
        prediction_row_id=f"reference-worker-{fixture_id}-{player_id}",
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
    include_extra_mid: bool = False,
    extra_mid_points: tuple[int, int] = (20, 20),
    uncertain_player: int | None = None,
    double_gameweek_player: int | None = None,
) -> Forecast:
    rows: list[PlayerFixtureForecast] = []
    positions = dict(BASE_POSITIONS)
    if include_extra_mid:
        positions[16] = "MID"
    for player_id, position in positions.items():
        low, high = (4, 6)
        if player_id == 8:
            low, high = (0, 2)
        if player_id == 16:
            low, high = extra_mid_points
        rows.append(
            _row(
                player_id=player_id,
                position=position,
                fixture_id=1000 + player_id,
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
                    fixture_id=2000 + player_id,
                    points_low=3,
                    points_high=7,
                    appearance_bps=7_500,
                )
            )
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("reference-worker-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=WORLD_ID,
        ruleset_id=_ruleset().ruleset_id,
        model_artifact_id=ModelArtifactId("reference-worker-model"),
        prediction_batch_id=PredictionBatchId("reference-worker-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=tuple(rows),
        abstentions=(),
    )


def _decision(
    store: FileSystemArtifactStore,
    *,
    state: ManagerState | None = None,
    universe: CandidateUniverse | None = None,
    forecast: Forecast | None = None,
    max_transfers: int = 0,
    chips: tuple[DecisionChip, ...] = (DecisionChip.NONE,),
):
    state = state or _state(store)
    universe = universe or _universe(store)
    forecast = forecast or _forecast()
    result = optimise_current_gameweek(
        state=state,
        forecast=forecast,
        universe=universe,
        ruleset=_ruleset(),
        policy=_policy(),
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=max_transfers,
        chips_considered=chips,
        alternatives_limit=3,
    )
    return state, universe, forecast, result


def _worker_certificate(
    store: FileSystemArtifactStore,
    *,
    state: ManagerState,
    universe: CandidateUniverse,
    forecast: Forecast,
    result,
    max_search_nodes: int = 100_000,
):
    request = build_reference_solver_request(
        decision_input=result.decision_input,
        manager_state=state,
        forecast=forecast,
        candidate_universe=universe,
        ruleset=_ruleset(),
        decision_policy=_policy(),
        max_search_nodes=max_search_nodes,
    )
    stored_request = store_reference_solver_request(request, store=store)
    run = solve_reference_request(request)
    stored_run = store_reference_solver_run(run, store=store)
    worker_code = store.put_bytes(
        (ROOT / "src/apex_fpl/workers/reference_solver.py").read_bytes(),
        media_type="text/x-python",
    ).artifact_id
    certificate = build_reference_solver_certificate(
        request_artifact_id=stored_request.artifact_id,
        run_artifact_id=stored_run.artifact_id,
        worker_name="apex-isolated-reference-solver",
        worker_version="1",
        worker_code_artifact_id=worker_code,
        store=store,
    )
    return request, run, certificate


def _assert_parity(store, result, certificate) -> None:
    status, blockers = validate_reference_solver_parity(
        result,
        certificate,
        store=store,
        expected_tie_break_policy_id=TACTICAL_REFERENCE_TIE_BREAK_POLICY_ID,
    )
    assert status is AssuranceParityStatus.PASS, blockers
    assert certificate.selected_action_id == result.selected_action.action_id
    assert certificate.best_objective == result.selected_action.mechanics.objective_points


def test_reference_worker_matches_probabilistic_autosub_and_dgw(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(
        store,
        forecast=_forecast(uncertain_player=3, double_gameweek_player=10),
    )
    _, run, certificate = _worker_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
    )
    assert run.solver_status is ReferenceSolverRunStatus.OPTIMAL
    _assert_parity(store, result, certificate)


def test_reference_worker_matches_transfer_hit_and_selling_resource(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state = _state(
        store,
        bank_tenths=1,
        free_transfers=0,
        purchase_basis_tenths=40,
        current_price_tenths=50,
    )
    universe = _universe(store, extra_mid_price_tenths=46)
    forecast = _forecast(include_extra_mid=True, extra_mid_points=(20, 20))
    state, universe, forecast, result = _decision(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        max_transfers=1,
    )
    assert len(result.selected_action.transfers) == 1
    assert result.selected_action.mechanics.hit_points == 4
    _, run, certificate = _worker_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
    )
    assert run.solver_status is ReferenceSolverRunStatus.OPTIMAL
    _assert_parity(store, result, certificate)


@pytest.mark.parametrize(
    "chips",
    [
        (DecisionChip.NONE, DecisionChip.TRIPLE_CAPTAIN),
        (DecisionChip.NONE, DecisionChip.BENCH_BOOST),
        (DecisionChip.NONE, DecisionChip.WILDCARD),
        (DecisionChip.NONE, DecisionChip.FREE_HIT),
    ],
)
def test_reference_worker_matches_declared_chip_surface(
    tmp_path: Path,
    chips: tuple[DecisionChip, ...],
) -> None:
    store = FileSystemArtifactStore(tmp_path / chips[-1].value)
    universe = _universe(store, extra_mid_price_tenths=50)
    forecast = _forecast(include_extra_mid=True, extra_mid_points=(15, 15))
    state, universe, forecast, result = _decision(
        store,
        universe=universe,
        forecast=forecast,
        chips=chips,
    )
    _, run, certificate = _worker_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
    )
    assert run.solver_status is ReferenceSolverRunStatus.OPTIMAL
    _assert_parity(store, result, certificate)


def test_search_limit_never_becomes_false_optimal(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    universe = _universe(store, extra_mid_price_tenths=50)
    forecast = _forecast(include_extra_mid=True)
    state, universe, forecast, result = _decision(
        store,
        universe=universe,
        forecast=forecast,
        max_transfers=1,
    )
    _, run, certificate = _worker_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
        max_search_nodes=1,
    )
    assert run.solver_status is ReferenceSolverRunStatus.SOLVER_LIMIT
    assert run.action_surface_complete is False
    assert run.limit_reason
    status, blockers = validate_reference_solver_parity(result, certificate, store=store)
    assert status is AssuranceParityStatus.INCONCLUSIVE
    assert any("SOLVER_LIMIT" in blocker for blocker in blockers)


def test_certificate_fields_cannot_diverge_from_retained_worker_io(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(store)
    _, _, certificate = _worker_certificate(
        store,
        state=state,
        universe=universe,
        forecast=forecast,
        result=result,
    )
    verify_reference_solver_certificate_io(certificate, store=store)
    tampered = replace(certificate, selected_action_id="sha256:" + "0" * 64)
    status, blockers = validate_reference_solver_parity(result, tampered, store=store)
    assert status is AssuranceParityStatus.FAIL
    assert any("retained I/O failed replay" in blocker for blocker in blockers)


def test_request_builder_rejects_foreign_semantic_context(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    state, universe, forecast, result = _decision(store)
    foreign_forecast = replace(
        forecast,
        prediction_batch_id=PredictionBatchId("different-reference-worker-batch"),
    )
    with pytest.raises(ValueError, match="DecisionInput/Forecast identity mismatch"):
        build_reference_solver_request(
            decision_input=result.decision_input,
            manager_state=state,
            forecast=foreign_forecast,
            candidate_universe=universe,
            ruleset=_ruleset(),
            decision_policy=_policy(),
            max_search_nodes=100,
        )


def test_reference_worker_has_no_prohibited_apex_imports() -> None:
    worker_path = ROOT / "src/apex_fpl/workers/reference_solver.py"
    tree = ast.parse(worker_path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    prohibited_prefixes = (
        "apex_fpl.decision",
        "apex_fpl.optimisation",
        "apex_fpl.services",
        "apex_fpl.assurance.reference_mechanics",
    )
    assert not any(
        module == prefix or module.startswith(prefix + ".")
        for module in imported
        for prefix in prohibited_prefixes
    )
