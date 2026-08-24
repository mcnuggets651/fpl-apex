from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
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
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    DecisionPolicyId,
    ForecastId,
    GlobalWorldId,
    ManagerStateId,
    RuleSetId,
)
from apex_fpl.decision.store import (
    load_candidate_universe,
    load_decision_result,
    store_candidate_universe,
    store_decision_result,
)


def _universe(store: FileSystemArtifactStore) -> CandidateUniverse:
    source = store.put_bytes(b"world").artifact_id
    filter_ref = store.put_bytes(b"filter").artifact_id
    players = tuple(
        CandidatePlayer(
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            position=("GK", "DEF", "MID", "FWD")[player_id % 4],
            current_price_tenths=50,
        )
        for player_id in range(1, 16)
    )
    return CandidateUniverse(
        global_world_id=GlobalWorldId("world"),
        scope=CandidateUniverseScope.SCOPED,
        players=players,
        official_player_count=16,
        source_artifact_ids=(source, filter_ref),
        filter_artifact_id=filter_ref,
    )


def _result(universe: CandidateUniverse) -> DecisionResult:
    ids = tuple(OfficialPlayerId(player_id) for player_id in range(1, 16))
    value = RationalValue(42, 1)
    zero = RationalValue.zero()
    action = DecisionAction(
        chip=DecisionChip.NONE,
        transfers=(),
        squad_ids=ids,
        xi_ids=ids[:11],
        captain_id=ids[0],
        vice_captain_id=ids[1],
        bench_gk_id=ids[11],
        outfield_bench_order=ids[12:],
        bank_after_tenths=0,
        mechanics=DecisionMechanics(
            xi_points=value,
            autosub_points=zero,
            captain_bonus=zero,
            squad_points_if_bench_boost=value,
            points_before_hits=value,
            hit_points=0,
            objective_points=value,
        ),
    )
    solver = SolverCertificate(
        status=SolverStatus.OPTIMAL,
        incumbent_objective=value,
        best_bound=value,
        gap=zero,
        numeric_error_bound=zero,
        message="replay fixture",
    )
    decision_input = DecisionInput(
        manager_state_id=ManagerStateId("state"),
        forecast_id=ForecastId("forecast"),
        ruleset_id=RuleSetId("rules"),
        candidate_universe_id=universe.candidate_universe_id,
        decision_policy_id=DecisionPolicyId("policy"),
        gameweek=2,
        use_mode=DecisionUseMode.SHADOW,
        objective_model=DecisionObjectiveModel.MARGINAL_INDEPENDENCE_BASELINE,
        max_normal_transfers=1,
        chips_considered=(DecisionChip.NONE,),
    )
    exactness = ExactnessClaim(
        status=ExactnessStatus.FEASIBLE_INCUMBENT,
        candidate_universe_id=universe.candidate_universe_id,
        universe_scope=universe.scope,
        solver_status=solver.status,
        action_surface_complete=False,
        search_complete=True,
        best_bound=value,
        gap=zero,
        filter_identity=universe.filter_identity,
        expansion_result=ExpansionResult.NOT_RUN,
        expansion_certificate_id=None,
        numeric_error_bound=zero,
        reasons=("scoped replay fixture",),
    )
    return DecisionResult(
        decision_input=decision_input,
        selected_action=action,
        alternatives=(),
        solver=solver,
        exactness=exactness,
        enumerated_actions=1,
    )


def test_candidate_universe_and_decision_replay_preserve_semantic_identities(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    universe = _universe(store)
    stored_universe = store_candidate_universe(universe, store=store)
    replay_universe = load_candidate_universe(stored_universe.artifact_id, store=store)
    assert replay_universe.universe.candidate_universe_id == universe.candidate_universe_id

    result = _result(universe)
    stored_result = store_decision_result(result, store=store)
    replay_result = load_decision_result(stored_result.artifact_id, store=store)
    assert replay_result.result.decision_id == result.decision_id
    assert replay_result.result.decision_input.decision_policy_id == DecisionPolicyId("policy")


def test_decision_replay_rejects_declared_semantic_identity_mismatch(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    result = _result(_universe(store))
    bad = {
        "schema_name": "apex-stored-decision-result",
        "schema_version": 1,
        "decision_id": "different-decision",
        "decision_result": result.semantic_payload(),
    }
    ref = store.put_bytes(canonical_json_bytes(bad))
    with pytest.raises(ValueError, match="semantic identity mismatch"):
        load_decision_result(ref.artifact_id, store=store)


def test_decision_replay_rejects_bool_fields_laundered_as_integers(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    result = _result(_universe(store))
    payload = result.semantic_payload()
    exactness = payload["exactness"]
    assert isinstance(exactness, dict)
    exactness["action_surface_complete"] = 1
    bad = {
        "schema_name": "apex-stored-decision-result",
        "schema_version": 1,
        "decision_id": str(result.decision_id),
        "decision_result": payload,
    }
    ref = store.put_bytes(canonical_json_bytes(bad))
    with pytest.raises(ValueError, match="must be boolean"):
        load_decision_result(ref.artifact_id, store=store)
