from __future__ import annotations

from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
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
from apex_fpl.decision.expansion import certify_candidate_expansion
from apex_fpl.decision.store import store_decision_result


def _player(player_id: int) -> CandidatePlayer:
    positions = ("GK", "DEF", "MID", "FWD")
    return CandidatePlayer(
        player_id=OfficialPlayerId(player_id),
        team_id=player_id,
        position=positions[player_id % 4],
        current_price_tenths=50,
    )


def _universes(store: FileSystemArtifactStore) -> tuple[CandidateUniverse, CandidateUniverse]:
    world = GlobalWorldId("world")
    source = store.put_bytes(b"world-source").artifact_id
    filter_ref = store.put_bytes(b"scoped-filter").artifact_id
    baseline = CandidateUniverse(
        global_world_id=world,
        scope=CandidateUniverseScope.SCOPED,
        players=tuple(_player(player_id) for player_id in range(1, 16)),
        official_player_count=16,
        source_artifact_ids=(source, filter_ref),
        filter_artifact_id=filter_ref,
    )
    expanded = CandidateUniverse(
        global_world_id=world,
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=tuple(_player(player_id) for player_id in range(1, 17)),
        official_player_count=16,
        source_artifact_ids=(source,),
    )
    return baseline, expanded


def _action(objective: int) -> DecisionAction:
    ids = tuple(OfficialPlayerId(player_id) for player_id in range(1, 16))
    zero = RationalValue.zero()
    value = RationalValue(objective, 1)
    return DecisionAction(
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


def _result(
    universe: CandidateUniverse,
    *,
    objective: int,
    global_exact: bool,
) -> DecisionResult:
    value = RationalValue(objective, 1)
    zero = RationalValue.zero()
    solver = SolverCertificate(
        status=SolverStatus.OPTIMAL,
        incumbent_objective=value,
        best_bound=value,
        gap=zero,
        numeric_error_bound=zero,
        message="synthetic exhaustive solve",
    )
    exactness = ExactnessClaim(
        status=(
            ExactnessStatus.GLOBAL_OPTIMAL
            if global_exact
            else ExactnessStatus.FEASIBLE_INCUMBENT
        ),
        candidate_universe_id=universe.candidate_universe_id,
        universe_scope=universe.scope,
        solver_status=solver.status,
        action_surface_complete=True,
        search_complete=True,
        best_bound=value,
        gap=zero,
        filter_identity=universe.filter_identity,
        expansion_result=ExpansionResult.NOT_RUN,
        expansion_certificate_id=None,
        numeric_error_bound=zero,
        reasons=() if global_exact else ("scoped pool awaiting expansion",),
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
        max_normal_transfers=15,
        chips_considered=(
            DecisionChip.NONE,
            DecisionChip.TRIPLE_CAPTAIN,
            DecisionChip.BENCH_BOOST,
            DecisionChip.WILDCARD,
            DecisionChip.FREE_HIT,
        ),
    )
    return DecisionResult(
        decision_input=decision_input,
        selected_action=_action(objective),
        alternatives=(),
        solver=solver,
        exactness=exactness,
        enumerated_actions=1,
    )


def _promoted_result(
    store: FileSystemArtifactStore,
) -> tuple[DecisionResult, str]:
    baseline_universe, expanded_universe = _universes(store)
    baseline = _result(baseline_universe, objective=100, global_exact=False)
    expanded = _result(expanded_universe, objective=101, global_exact=True)
    _certificate, artifact_id, promoted = certify_candidate_expansion(
        baseline=baseline,
        expanded=expanded,
        baseline_universe=baseline_universe,
        expanded_universe=expanded_universe,
        materiality_threshold=RationalValue(2, 1),
        store=store,
    )
    return promoted, artifact_id


def test_materially_better_expanded_pool_invalidates_narrow_search_claim(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    baseline_universe, expanded_universe = _universes(store)
    baseline = _result(baseline_universe, objective=100, global_exact=False)
    expanded = _result(expanded_universe, objective=110, global_exact=True)
    certificate, artifact_id, result = certify_candidate_expansion(
        baseline=baseline,
        expanded=expanded,
        baseline_universe=baseline_universe,
        expanded_universe=expanded_universe,
        materiality_threshold=RationalValue(2, 1),
        store=store,
    )
    assert certificate.result is ExpansionResult.MATERIAL_IMPROVEMENT_FOUND
    assert certificate.certifies_baseline_universe is False
    assert result.exactness.status is ExactnessStatus.FEASIBLE_INCUMBENT
    assert store.read_bytes(artifact_id)


def test_full_official_expansion_without_material_improvement_certifies_scoped_pool(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    promoted, artifact_id = _promoted_result(store)
    assert promoted.exactness.status is ExactnessStatus.OPTIMAL_WITHIN_CERTIFIED_UNIVERSE
    assert promoted.exactness.expansion_certificate_id == artifact_id
    assert promoted.exactness.publication_exactness_eligible is True


def test_promoted_scoped_decision_requires_verifying_expansion_artifact(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    promoted, artifact_id = _promoted_result(store)
    stored = store_decision_result(promoted, store=store)
    assert stored.result.exactness.expansion_certificate_id == artifact_id

    empty_store = FileSystemArtifactStore(tmp_path / "empty-artifacts")
    with pytest.raises(FileNotFoundError):
        store_decision_result(promoted, store=empty_store)
