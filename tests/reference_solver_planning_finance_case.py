from __future__ import annotations

from dataclasses import replace

from apex_fpl.assurance.reference_solver_planning_exchange import (
    build_planning_reference_solver_request,
    store_planning_reference_solver_request,
)
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.manager_state_store import store_manager_state
from apex_fpl.control.reference_solver_planning_qualification import (
    store_planning_reference_solver_qualification_case,
)
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import CandidatePlayer, CandidateUniverse, CandidateUniverseScope, DecisionUseMode
from apex_fpl.core.forecast import (
    DiscreteIntegerDistribution,
    Forecast,
    ForecastUncertainty,
    PlayerFixtureForecast,
    PlayerFixtureTarget,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import FeatureSnapshotId, PredictionBatchId
from apex_fpl.core.manager_state import ChipUse
from apex_fpl.core.reference_solver_planning_qualification import (
    PlanningReferenceSolverQualificationCase,
)
from apex_fpl.decision.planner import optimise_receding_horizon
from apex_fpl.decision.planning_store import store_planning_result
from apex_fpl.decision.store import store_candidate_universe


_FINANCE_GAMEWEEK = 6
_FINANCE_EXTRA_PLAYER = OfficialPlayerId(16)
_FINANCE_CLUB_ID = 8
_FINANCE_CLUB_OWNED_IDS = frozenset({3, 4, 8})


def _finance_candidate_universe(verified, *, store: ArtifactStore) -> tuple[CandidateUniverse, str]:
    """Build the smallest legal finance surface while preserving the required semantics.

    The publication fixture separately proves the complete FULL_OFFICIAL/chip action surface.
    This focused case only needs to prove banking and authoritative selling-vs-purchase finance.
    Three owned players deliberately share the target club, so importing player 16 is legal only
    when the intended MID (player 8) leaves. That preserves exact transfer mechanics while
    preventing unrelated same-position swaps from multiplying the qualification search tree.
    """

    base = verified.candidate_universe
    existing = next(
        (row for row in base.players if row.player_id == _FINANCE_EXTRA_PLAYER),
        None,
    )
    if existing is not None and (
        existing.position != "MID" or existing.current_price_tenths != 51
    ):
        raise ValueError(
            "focused finance case player 16 must remain the £5.1m MID qualification target"
        )

    source = store.put_bytes(b"synthetic-planning-finance-universe-source-v2").artifact_id
    shaped_players = tuple(
        replace(player, team_id=_FINANCE_CLUB_ID)
        if int(player.player_id) in (*_FINANCE_CLUB_OWNED_IDS, int(_FINANCE_EXTRA_PLAYER))
        else player
        for player in base.players
    )
    if existing is None:
        shaped_players = (
            *shaped_players,
            CandidatePlayer(
                player_id=_FINANCE_EXTRA_PLAYER,
                team_id=_FINANCE_CLUB_ID,
                position="MID",
                current_price_tenths=51,
            ),
        )

    universe = CandidateUniverse(
        global_world_id=base.global_world_id,
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=shaped_players,
        official_player_count=len(shaped_players),
        source_artifact_ids=(source,),
    )
    target = next(row for row in universe.players if row.player_id == _FINANCE_EXTRA_PLAYER)
    saturated_owned = {
        int(row.player_id)
        for row in universe.players
        if row.team_id == _FINANCE_CLUB_ID and row.player_id != _FINANCE_EXTRA_PLAYER
    }
    if saturated_owned != _FINANCE_CLUB_OWNED_IDS:
        raise ValueError("focused finance universe must saturate the target club with players 3,4,8")
    if target.position != "MID" or target.current_price_tenths != 51:
        raise ValueError("focused finance target semantics drifted")

    stored = store_candidate_universe(universe, store=store)
    return universe, stored.artifact_id


def _finance_manager_state(verified, universe: CandidateUniverse, *, store: ArtifactStore):
    source = store.put_bytes(b"synthetic-planning-finance-chip-history").artifact_id
    chips = (
        ChipUse(chip="BENCH_BOOST", gameweek=2, set_number=1, source_artifact_id=source),
        ChipUse(chip="TRIPLE_CAPTAIN", gameweek=3, set_number=1, source_artifact_id=source),
        ChipUse(chip="WILDCARD", gameweek=4, set_number=1, source_artifact_id=source),
        ChipUse(chip="FREE_HIT", gameweek=5, set_number=1, source_artifact_id=source),
    )
    candidates = {row.player_id: row for row in universe.players}
    squad = tuple(
        replace(row, team_id=candidates[row.player_id].team_id)
        for row in verified.manager_state.squad
    )
    state = replace(
        verified.manager_state,
        gameweek=_FINANCE_GAMEWEEK,
        bank_tenths=1,
        free_transfers=1,
        squad=squad,
        chips_used=chips,
        transfer_ledger=(),
    )
    state.require_decision_safe(ruleset=verified.ruleset)
    club_rows = tuple(row for row in state.squad if row.team_id == _FINANCE_CLUB_ID)
    if {int(row.player_id) for row in club_rows} != _FINANCE_CLUB_OWNED_IDS:
        raise ValueError("focused finance manager state must start with target club at legal maximum")
    store_manager_state(state, store=store)
    return state


def _row_for_depth(verified, *, player_id: int, depth: int) -> PlayerFixtureForecast:
    base_gameweek = verified.bundle.gameweek
    for row in verified.forecast.rows:
        if int(row.target.player_id) == player_id and row.target.gameweek == base_gameweek + depth:
            return row
    raise ValueError(f"missing publication forecast template for player {player_id} depth {depth}")


def _retarget_row(
    template: PlayerFixtureForecast,
    *,
    gameweek: int,
    player_id: OfficialPlayerId,
    team_id: int,
    position: str,
    points: int | None = None,
) -> PlayerFixtureForecast:
    target = PlayerFixtureTarget(
        fixture_id=gameweek * 1000 + int(player_id),
        gameweek=gameweek,
        player_id=player_id,
        team_id=team_id,
        opponent_team_id=100 + team_id,
        is_home=True,
        position=position,
    )
    uncertainty: ForecastUncertainty = template.uncertainty
    points_distribution = template.points_distribution
    if points is not None:
        points_distribution = DiscreteIntegerDistribution(((points, 10_000),))
        uncertainty = replace(
            uncertainty,
            points_p10=points,
            points_p50=points,
            points_p90=points,
        )
    return PlayerFixtureForecast(
        target=target,
        prediction_row_id=canonical_sha256(
            {
                "schema_name": "synthetic-planning-finance-row",
                "gameweek": gameweek,
                "player_id": int(player_id),
            }
        ),
        minutes_distribution=template.minutes_distribution,
        points_distribution=points_distribution,
        uncertainty=uncertainty,
    )


def _finance_forecast(verified, universe: CandidateUniverse) -> Forecast:
    rows: list[PlayerFixtureForecast] = []
    for depth, gameweek in enumerate((_FINANCE_GAMEWEEK, _FINANCE_GAMEWEEK + 1)):
        for player in universe.players:
            player_id = int(player.player_id)
            if player.player_id == _FINANCE_EXTRA_PLAYER:
                template = _row_for_depth(verified, player_id=8, depth=depth)
                rows.append(
                    _retarget_row(
                        template,
                        gameweek=gameweek,
                        player_id=player.player_id,
                        team_id=player.team_id,
                        position=player.position,
                        points=0 if depth == 0 else 12,
                    )
                )
                continue
            template = _row_for_depth(verified, player_id=player_id, depth=depth)
            # Player 8 is deliberately good in GW7 (10 xP in the source fixture), while
            # the £5.1m MID target is 12 xP. Banking first and transferring only in GW7 is
            # therefore uniquely better than sacrificing current-GW points for an early move.
            rows.append(
                _retarget_row(
                    template,
                    gameweek=gameweek,
                    player_id=player.player_id,
                    team_id=player.team_id,
                    position=player.position,
                )
            )
    return replace(
        verified.forecast,
        feature_snapshot_id=FeatureSnapshotId(
            canonical_sha256(
                {
                    "schema_name": "synthetic-planning-finance-feature-snapshot",
                    "world_id": str(universe.global_world_id),
                }
            )
        ),
        prediction_batch_id=PredictionBatchId(
            canonical_sha256(
                {
                    "schema_name": "synthetic-planning-finance-prediction-batch",
                    "world_id": str(universe.global_world_id),
                }
            )
        ),
        rows=tuple(rows),
        abstentions=(),
    )


def store_finance_qualification_case(
    *,
    store: ArtifactStore,
    verified,
    continuation,
    chip_option,
    price_policy,
    candidate_policy,
    max_search_nodes: int = 500,
) -> str:
    """Store a focused finance/banking case for planning-worker qualification.

    Current-set chips are all validly consumed in prior GWs, removing chip branching from this
    case. The publication case proves the complete chip/full-action surface. Club saturation in
    this focused case leaves one legally relevant financed MID replacement, so qualification
    proves the intended mechanism without wasting exact-search nodes on unrelated swaps.
    """

    universe, universe_artifact_id = _finance_candidate_universe(verified, store=store)
    manager_state = _finance_manager_state(verified, universe, store=store)
    forecast = _finance_forecast(verified, universe)
    policy = verified.decision_policy
    result = optimise_receding_horizon(
        state=manager_state,
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
        raise ValueError("focused planning finance fixture did not complete exact search")
    steps = result.selected_trajectory.steps
    if len(steps) != 2 or steps[0].action.transfers or not steps[1].action.transfers:
        raise ValueError("focused planning finance fixture did not bank then transfer")
    if len(steps[1].action.transfers) != 1:
        raise ValueError("focused planning finance fixture must execute exactly one transfer")
    move = steps[1].action.transfers[0]
    if move.outgoing_player_id != OfficialPlayerId(8):
        raise ValueError("focused planning finance fixture selected the wrong outgoing player")
    if move.incoming_player_id != _FINANCE_EXTRA_PLAYER:
        raise ValueError("focused planning finance fixture selected the wrong incoming player")

    stored_result = store_planning_result(
        result,
        manager_state_id=manager_state.manager_state_id,
        universe=universe,
        ruleset=verified.ruleset,
        continuation=continuation,
        chip_option=chip_option,
        store=store,
    )
    request = build_planning_reference_solver_request(
        result=result,
        manager_state=manager_state,
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
        candidate_universe_artifact_id=universe_artifact_id,
    )
    return store_planning_reference_solver_qualification_case(case, store=store)
