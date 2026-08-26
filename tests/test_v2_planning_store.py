from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.manager_state_store import load_manager_state, store_manager_state
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionUseMode,
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
from apex_fpl.decision.planner import optimise_receding_horizon
from apex_fpl.decision.planning_store import load_planning_result, store_planning_result


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
    source = store.put_bytes(b"retained-current-manager-truth").artifact_id
    state = ManagerState(
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
    state.require_decision_safe(ruleset=ruleset)
    return state


def _universe(store: FileSystemArtifactStore) -> CandidateUniverse:
    source = store.put_bytes(b"retained-full-official-world").artifact_id
    return CandidateUniverse(
        global_world_id=GlobalWorldId("planning-store-world"),
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
            points = 3 + (player_id == 8) * (8 if gameweek == 3 else 1)
            distribution = DiscreteIntegerDistribution(((points, 10_000),))
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
                    prediction_row_id=f"store-gw{gameweek}-p{player_id}",
                    minutes_distribution=DiscreteIntegerDistribution(((90, 10_000),)),
                    points_distribution=distribution,
                    uncertainty=ForecastUncertainty(
                        uncertainty_kind=UncertaintyKind.PROBABILISTIC,
                        deterministic_reason=None,
                        scenario_count=1,
                        minutes_p10=90,
                        minutes_p50=90,
                        minutes_p90=90,
                        points_p10=points,
                        points_p50=points,
                        points_p90=points,
                        appearance_probability_bps=10_000,
                        sixty_plus_probability_bps=10_000,
                    ),
                )
            )
    ruleset = _ruleset()
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("planning-store-feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("planning-store-world"),
        ruleset_id=ruleset.ruleset_id,
        model_artifact_id=ModelArtifactId("planning-store-model"),
        prediction_batch_id=PredictionBatchId("planning-store-batch"),
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
    chip = ChipOptionValuePolicy(
        season="2026-2027",
        horizon_gameweeks=2,
        first_available_at="2026-08-01T00:00:00Z",
        option_values=tuple(
            (name, ExactPolicyValue.zero())
            for name in ("BENCH_BOOST", "FREE_HIT", "TRIPLE_CAPTAIN", "WILDCARD")
        ),
    )
    price = PricePolicy(season="2026-2027", first_available_at="2026-08-01T00:00:00Z")
    candidate = CandidatePolicy(season="2026-2027", first_available_at="2026-08-01T00:00:00Z")
    policy = DecisionPolicy(
        policy_name="planning-store-policy",
        policy_version="1",
        season="2026-2027",
        qualification_state=DecisionPolicyQualificationState.SHADOW,
        qualification_artifact_id=None,
        first_available_at="2026-08-01T00:00:00Z",
        evaluation_mode=DecisionEvaluationMode.RECEDING_HORIZON_WITH_CONTINUATION,
        objective_policy=DecisionObjectivePolicy.MAX_EXPECTED_FPL_POINTS_OVER_TIME,
        horizon_gameweeks=2,
        continuation_value_artifact_id=continuation.policy_id,
        chip_option_value_artifact_id=chip.policy_id,
        price_policy_artifact_id=price.policy_id,
        candidate_policy_artifact_id=candidate.policy_id,
        tie_break_policy="lexicographic-official-id-v1",
    )
    return policy, continuation, chip, price, candidate


def _decision(store: FileSystemArtifactStore):
    state = _state(store)
    universe = _universe(store)
    policy, continuation, chip, price, candidate = _supports()
    result = optimise_receding_horizon(
        state=state,
        forecast=_forecast(),
        universe=universe,
        ruleset=_ruleset(),
        policy=policy,
        continuation=continuation,
        chip_option=chip,
        price_policy=price,
        candidate_policy=candidate,
        use_mode=DecisionUseMode.SHADOW,
        max_search_nodes=1,
        alternatives_limit=0,
    )
    return state, universe, continuation, chip, result


def test_manager_state_store_is_self_addressing_and_replayable(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "manager-store")
    state = _state(store)
    artifact_id = store_manager_state(state, store=store)
    assert artifact_id == str(state.manager_state_id)
    assert load_manager_state(artifact_id, store=store).semantic_payload() == state.semantic_payload()


def test_planning_result_replays_every_retained_transition(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "planning-store")
    state, universe, continuation, chip, result = _decision(store)
    manager_id = store_manager_state(state, store=store)
    stored = store_planning_result(
        result,
        manager_state_id=manager_id,
        universe=universe,
        ruleset=_ruleset(),
        continuation=continuation,
        chip_option=chip,
        store=store,
    )
    assert stored.artifact_id == str(result.planning_result_id)
    replayed = load_planning_result(
        stored.artifact_id,
        manager_state_id=manager_id,
        universe=universe,
        ruleset=_ruleset(),
        continuation=continuation,
        chip_option=chip,
        store=store,
    )
    assert replayed.result.semantic_payload() == result.semantic_payload()


def test_missing_retained_hypothetical_state_fails_replay(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "missing-state")
    state, universe, continuation, chip, result = _decision(store)
    manager_id = store_manager_state(state, store=store)
    stored = store_planning_result(
        result,
        manager_state_id=manager_id,
        universe=universe,
        ruleset=_ruleset(),
        continuation=continuation,
        chip_option=chip,
        store=store,
    )
    missing_id = str(result.selected_trajectory.steps[-1].state_after_id)
    digest = store._digest_from_id(missing_id)
    store._object_path(digest).unlink()
    with pytest.raises(ValueError, match="PlanningState artifact failed integrity"):
        load_planning_result(
            stored.artifact_id,
            manager_state_id=manager_id,
            universe=universe,
            ruleset=_ruleset(),
            continuation=continuation,
            chip_option=chip,
            store=store,
        )


def test_wrong_manager_truth_cannot_replay_planning_result(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "wrong-manager")
    state, universe, continuation, chip, result = _decision(store)
    manager_id = store_manager_state(state, store=store)
    stored = store_planning_result(
        result,
        manager_state_id=manager_id,
        universe=universe,
        ruleset=_ruleset(),
        continuation=continuation,
        chip_option=chip,
        store=store,
    )
    other_source = store.put_bytes(b"different-current-truth").artifact_id
    wrong_state = ManagerState(
        season=state.season,
        entry_id=state.entry_id,
        gameweek=state.gameweek,
        ruleset_id=state.ruleset_id,
        scope=state.scope,
        bank_tenths=1,
        free_transfers=state.free_transfers,
        squad=state.squad,
        provenance_artifact_ids=(other_source,),
    )
    wrong_id = store_manager_state(wrong_state, store=store)
    with pytest.raises(ValueError, match="retained ManagerState identity mismatch"):
        load_planning_result(
            stored.artifact_id,
            manager_state_id=wrong_id,
            universe=universe,
            ruleset=_ruleset(),
            continuation=continuation,
            chip_option=chip,
            store=store,
        )
