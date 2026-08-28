from __future__ import annotations

from dataclasses import replace

from apex_fpl.assurance.reference_solver_planning_exchange import (
    build_planning_reference_solver_request,
    store_planning_reference_solver_request,
)
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.reference_solver_planning_qualification import (
    store_planning_reference_solver_qualification_case,
)
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import CandidateUniverse, CandidateUniverseScope, DecisionUseMode
from apex_fpl.core.ids import FeatureSnapshotId, GlobalWorldId, PredictionBatchId
from apex_fpl.core.reference_solver_planning_qualification import (
    PlanningReferenceSolverQualificationCase,
)
from apex_fpl.decision.planner import optimise_receding_horizon
from apex_fpl.decision.planning_store import store_planning_result
from apex_fpl.decision.store import store_candidate_universe



def store_full_surface_qualification_case(
    *,
    store: ArtifactStore,
    verified,
    continuation,
    chip_option,
    price_policy,
    candidate_policy,
    max_search_nodes: int = 500,
) -> str:
    """Store a compact exact case for the full planning/chip action contract.

    Algorithmic worker qualification should prove mechanisms, not repeatedly solve the current
    publication's combinatorial candidate set. This case keeps the exact 15-player owned squad as
    a complete synthetic FULL_OFFICIAL world. With no external transfer candidate, all four chips,
    multi-Gameweek continuation, terminal reserve, exact XI/captain/bench mechanics and the
    declared 15-transfer action contract remain present while redundant transfer combinations are
    absent. The separate finance case proves banked transfers and sale-vs-purchase arithmetic.

    This case owns a distinct deterministic world/feature/batch identity so FULL_OFFICIAL means
    every player in this synthetic proof world; it never masquerades as the 16-player publication
    world. The real publication request is still solved independently, zero-gap, at its certified
    exact search budget before a publication authorization can be created.
    """

    owned_ids = {row.player_id for row in verified.manager_state.squad}
    players = tuple(
        row for row in verified.candidate_universe.players if row.player_id in owned_ids
    )
    if len(players) != 15 or {row.player_id for row in players} != owned_ids:
        raise ValueError("planning surface qualification requires the exact owned 15-player squad")

    ordered_owned_ids = tuple(sorted(int(player_id) for player_id in owned_ids))
    world_id = GlobalWorldId(
        canonical_sha256(
            {
                "schema_name": "synthetic-planning-full-surface-world",
                "source_world_id": str(verified.candidate_universe.global_world_id),
                "player_ids": list(ordered_owned_ids),
            }
        )
    )
    source = store.put_bytes(b"synthetic-planning-full-surface-universe-v2").artifact_id
    universe = CandidateUniverse(
        global_world_id=world_id,
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=players,
        official_player_count=len(players),
        source_artifact_ids=(source,),
    )
    stored_universe = store_candidate_universe(universe, store=store)

    forecast = replace(
        verified.forecast,
        global_world_id=world_id,
        feature_snapshot_id=FeatureSnapshotId(
            canonical_sha256(
                {
                    "schema_name": "synthetic-planning-full-surface-feature-snapshot",
                    "world_id": str(world_id),
                }
            )
        ),
        prediction_batch_id=PredictionBatchId(
            canonical_sha256(
                {
                    "schema_name": "synthetic-planning-full-surface-prediction-batch",
                    "world_id": str(world_id),
                }
            )
        ),
        rows=tuple(
            row for row in verified.forecast.rows if row.target.player_id in owned_ids
        ),
        abstentions=tuple(
            row for row in verified.forecast.abstentions if row.target.player_id in owned_ids
        ),
    )
    policy = verified.decision_policy
    result = optimise_receding_horizon(
        state=verified.manager_state,
        forecast=forecast,
        universe=universe,
        ruleset=verified.ruleset,
        policy=policy,
        continuation=continuation,
        chip_option=chip_option,
        price_policy=price_policy,
        candidate_policy=candidate_policy,
        use_mode=DecisionUseMode.PRODUCTION,
        max_search_nodes=max_search_nodes,
        alternatives_limit=0,
    )
    if not result.solver.search_complete or result.solver.gap.numerator != 0:
        raise ValueError("planning full-surface qualification fixture did not complete exact search")
    if any(step.action.transfers for step in result.selected_trajectory.steps):
        raise ValueError("planning full-surface qualification fixture must not contain transfers")

    stored_result = store_planning_result(
        result,
        manager_state_id=verified.manager_state.manager_state_id,
        universe=universe,
        ruleset=verified.ruleset,
        continuation=continuation,
        chip_option=chip_option,
        store=store,
    )
    request = build_planning_reference_solver_request(
        result=result,
        manager_state=verified.manager_state,
        forecast=forecast,
        candidate_universe=universe,
        ruleset=verified.ruleset,
        decision_policy=policy,
        continuation_policy=continuation,
        chip_option_policy=chip_option,
        price_policy=price_policy,
        candidate_policy=candidate_policy,
        max_search_nodes=max_search_nodes,
    )
    stored_request = store_planning_reference_solver_request(request, store=store)
    case = PlanningReferenceSolverQualificationCase(
        request_artifact_id=stored_request.artifact_id,
        expected_planning_result_artifact_id=stored_result.artifact_id,
        candidate_universe_artifact_id=stored_universe.artifact_id,
    )
    return store_planning_reference_solver_qualification_case(case, store=store)
