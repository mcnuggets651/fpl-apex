from __future__ import annotations

from pathlib import Path

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionChip,
    DecisionUseMode,
    RationalValue,
)
from apex_fpl.core.decision_policy import (
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
from apex_fpl.core.planning import PlanningSolverStatus
from apex_fpl.decision.planner import optimise_receding_horizon


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


def _state(store: FileSystemArtifactStore) -> ManagerState:
    ruleset = _ruleset()
    source = store.put_bytes(b"planner-current-state").artifact_id
    return ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=ruleset.ruleset_id,
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
    source = store.put_bytes(b"planner-full-world").artifact_id
    return CandidateUniverse(
        global_world_id=GlobalWorldId("planner-world"),
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
        official_player_count=len(POSITIONS),
        source_artifact_ids=(source,),
    )


def _forecast() -> Forecast:
    rows = []
    for gameweek in (2, 3):
        for player_id, position in POSITIONS.items():
            base = 2
            if player_id == 8:
                base = 5 if gameweek == 2 else 20
            distribution = DiscreteIntegerDistribution(((base, 10_000),))
            rows.append(
                PlayerFixtureForecast(
                    target=PlayerFixtureTarget(
                        fixture_id=gameweek * 1000 + player_id,
                        gameweek=gameweek,
                        player_id=OfficialPlayerId(player_id),
                        team_id=player_id,
                        opponent_team_id=100 + player_id,
                        is_home=True,
                        position=position,
                    ),
                    prediction_row_id=f"gw{gameweek}-p{player_id}",
                    minutes_distribution=DiscreteIntegerDistribution(((90, 10_000),)),
                    points_distribution=distribution,
                    uncertainty=ForecastUncertainty(
                        uncertainty_kind=UncertaintyKind.PROBABILISTIC,
                        deterministic_reason=None,
                        scenario_count=1,
                        minutes_p10=90,
                        minutes_p50=90,
                        minutes_p90=90,
                        points_p10=base,
                        points_p50=base,
                        points_p90=base,
                        appearance_probability_bps=10_000,
                        sixty_plus_probability_bps=10_000,
                    ),
                )
            )
    ruleset = _ruleset()
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("planner-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("planner-world"),
        ruleset_id=ruleset.ruleset_id,
        model_artifact_id=ModelArtifactId("planner-model"),
        prediction_batch_id=PredictionBatchId("planner-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=tuple(rows),
        abstentions=(),
    )


def _supports():
    continuation = ContinuationValuePolicy(
        season="2026-2027",
        horizon_gameweeks=2,
        first_available_at="2026-08-01T00:00:00Z",
        gameweek_weights=(ExactPolicyValue.one(), ExactPolicyValue.one()),
    )
    chip_option = ChipOptionValuePolicy(
        season="2026-2027",
        horizon_gameweeks=2,
        first_available_at="2026-08-01T00:00:00Z",
        option_values=tuple(
            (chip, ExactPolicyValue.zero())
            for chip in ("BENCH_BOOST", "FREE_HIT", "TRIPLE_CAPTAIN", "WILDCARD")
        ),
    )
    price = PricePolicy(season="2026-2027", first_available_at="2026-08-01T00:00:00Z")
    candidate = CandidatePolicy(season="2026-2027", first_available_at="2026-08-01T00:00:00Z")
    policy = DecisionPolicy(
        policy_name="test-receding",
        policy_version="1",
        season="2026-2027",
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-01T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=2,
        continuation_value_artifact_id=continuation.policy_id,
        chip_option_value_artifact_id=chip_option.policy_id,
        price_policy_artifact_id=price.policy_id,
        candidate_policy_artifact_id=candidate.policy_id,
        tie_break_policy="lexicographic-official-id-v1",
    )
    return policy, continuation, chip_option, price, candidate


def _run(tmp_path: Path, *, max_search_nodes: int):
    store = FileSystemArtifactStore(tmp_path / f"artifacts-{max_search_nodes}")
    policy, continuation, chip_option, price, candidate = _supports()
    return optimise_receding_horizon(
        state=_state(store),
        forecast=_forecast(),
        universe=_universe(store),
        ruleset=_ruleset(),
        policy=policy,
        continuation=continuation,
        chip_option=chip_option,
        price_policy=price,
        candidate_policy=candidate,
        use_mode=DecisionUseMode.SHADOW,
        max_search_nodes=max_search_nodes,
        alternatives_limit=5,
    )


def test_small_full_official_world_exhausts_to_exact_optimum(tmp_path: Path) -> None:
    result = _run(tmp_path, max_search_nodes=500)
    assert result.solver.status is PlanningSolverStatus.OPTIMAL
    assert result.solver.search_complete is True
    assert result.solver.gap == RationalValue.zero()
    # GW3 has the much stronger captaincy ceiling, so the exact horizon policy must not
    # burn Triple Captain in GW2.
    assert result.selected_trajectory.steps[0].action.chip is not DecisionChip.TRIPLE_CAPTAIN
    assert result.selected_trajectory.steps[1].action.chip is DecisionChip.TRIPLE_CAPTAIN
    assert result.decision_input.max_normal_transfers == 15
    assert set(result.decision_input.chips_considered) == set(DecisionChip)


def test_node_limit_never_becomes_false_optimality(tmp_path: Path) -> None:
    result = _run(tmp_path, max_search_nodes=1)
    assert result.solver.status is PlanningSolverStatus.SOLVER_LIMIT
    assert result.solver.search_complete is False
    assert result.solver.best_bound is not None
    assert result.solver.incumbent_objective == result.selection_objective
    assert result.solver.gap is not None
    assert result.solver.gap.numerator >= 0
