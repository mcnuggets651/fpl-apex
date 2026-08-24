from __future__ import annotations

from itertools import combinations
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionChip,
    DecisionUseMode,
    ExactnessStatus,
    SolverStatus,
)
from apex_fpl.core.decision_policy import (
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
from apex_fpl.core.manager_state import ManagerState, ManagerStateScope, OwnedPlayer
from apex_fpl.decision.engine import optimise_current_gameweek
from apex_fpl.decision.mechanics import build_gameweek_values


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
    16: "MID",
    17: "FWD",
}


def _ruleset():
    return load_ruleset(Path("config/rules/2026-2027.yaml"))


def _policy() -> DecisionPolicy:
    return DecisionPolicy(
        policy_name="tactical-reference",
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
        tie_break_policy="lexicographic-official-id-v1",
    )


def _players() -> tuple[CandidatePlayer, ...]:
    return tuple(
        CandidatePlayer(
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            position=position,
            current_price_tenths=50,
        )
        for player_id, position in POSITIONS.items()
    )


def _state(store: FileSystemArtifactStore, *, free_transfers: int = 1) -> ManagerState:
    ruleset = _ruleset()
    source = store.put_bytes(b"exact-current-state").artifact_id
    owned = tuple(
        OwnedPlayer(
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            position=POSITIONS[player_id],
            purchase_basis_tenths=50,
            current_price_tenths=50,
            selling_price_tenths=50,
        )
        for player_id in range(1, 16)
    )
    state = ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=ruleset.ruleset_id,
        scope=ManagerStateScope.CURRENT_EXACT,
        bank_tenths=0,
        free_transfers=free_transfers,
        squad=owned,
        provenance_artifact_ids=(source,),
    )
    state.require_decision_safe(ruleset=ruleset)
    return state


def _forecast(
    *,
    xp: dict[int, int] | None = None,
    appearance_bps: int = 5_000,
) -> Forecast:
    values = {player_id: 2 for player_id in POSITIONS}
    values.update({8: -6, 13: -6, 16: 15, 17: 15})
    if xp:
        values.update(xp)
    if appearance_bps not in {5_000, 10_000}:
        raise ValueError("test forecast supports 50% or 100% appearance only")
    rows = []
    for player_id, position in POSITIONS.items():
        expected = values[player_id]
        points = DiscreteIntegerDistribution(
            ((expected - 1, 5_000), (expected + 1, 5_000))
        )
        minutes = (
            DiscreteIntegerDistribution(((90, 10_000),))
            if appearance_bps == 10_000
            else DiscreteIntegerDistribution(((0, 5_000), (90, 5_000)))
        )
        target = PlayerFixtureTarget(
            fixture_id=100 + player_id,
            gameweek=2,
            player_id=OfficialPlayerId(player_id),
            team_id=player_id,
            opponent_team_id=100 + player_id,
            is_home=True,
            position=position,
        )
        rows.append(
            PlayerFixtureForecast(
                target=target,
                prediction_row_id=f"row-{player_id}",
                minutes_distribution=minutes,
                points_distribution=points,
                uncertainty=ForecastUncertainty(
                    uncertainty_kind=UncertaintyKind.PROBABILISTIC,
                    deterministic_reason=None,
                    scenario_count=2,
                    minutes_p10=90 if appearance_bps == 10_000 else 0,
                    minutes_p50=90 if appearance_bps == 10_000 else 0,
                    minutes_p90=90,
                    points_p10=expected - 1,
                    points_p50=expected - 1,
                    points_p90=expected + 1,
                    appearance_probability_bps=appearance_bps,
                    sixty_plus_probability_bps=appearance_bps,
                ),
            )
        )
    ruleset = _ruleset()
    return Forecast(
        season="2026-2027",
        feature_snapshot_id=FeatureSnapshotId("feature"),
        feature_cutoff="2026-08-24T06:00:00Z",
        global_world_id=GlobalWorldId("synthetic-world"),
        ruleset_id=ruleset.ruleset_id,
        model_artifact_id=ModelArtifactId("shadow-model"),
        prediction_batch_id=PredictionBatchId("shadow-batch"),
        use_mode=ForecastUseMode.SHADOW,
        model_qualification_state=ModelQualificationState.SHADOW,
        rows=tuple(rows),
        abstentions=(),
    )


def _universe(store: FileSystemArtifactStore) -> CandidateUniverse:
    source = store.put_bytes(b"full-official-synthetic-world").artifact_id
    return CandidateUniverse(
        global_world_id=GlobalWorldId("synthetic-world"),
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=_players(),
        official_player_count=len(POSITIONS),
        source_artifact_ids=(source,),
    )


def _independent_no_transfer_oracle(xp: dict[int, int]) -> int:
    ruleset = _ruleset()
    minimum = ruleset.mapping("FPL-XI-MIN-POSITIONS-001")
    maximum = ruleset.mapping("FPL-XI-MAX-POSITIONS-001")
    by_position = {
        position: tuple(
            player_id
            for player_id in range(1, 16)
            if POSITIONS[player_id] == position
        )
        for position in ("GK", "DEF", "MID", "FWD")
    }
    best: int | None = None
    for goalkeeper in by_position["GK"]:
        for defenders in range(int(minimum["DEF"]), int(maximum["DEF"]) + 1):
            for midfielders in range(int(minimum["MID"]), int(maximum["MID"]) + 1):
                forwards = 10 - defenders - midfielders
                if not int(minimum["FWD"]) <= forwards <= int(maximum["FWD"]):
                    continue
                for chosen_def in combinations(by_position["DEF"], defenders):
                    for chosen_mid in combinations(by_position["MID"], midfielders):
                        for chosen_fwd in combinations(by_position["FWD"], forwards):
                            xi = (
                                goalkeeper,
                                *chosen_def,
                                *chosen_mid,
                                *chosen_fwd,
                            )
                            xi_points = sum(xp[player_id] for player_id in xi)
                            captain_bonus = max(xp[player_id] for player_id in xi)
                            objective = xi_points + captain_bonus
                            best = objective if best is None else max(best, objective)
    assert best is not None
    return best


def test_small_universe_decision_matches_independent_bruteforce_true_optimum(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    xp = {
        1: 2,
        2: 1,
        3: 8,
        4: 7,
        5: 6,
        6: 1,
        7: -2,
        8: 9,
        9: 5,
        10: 4,
        11: 3,
        12: -3,
        13: 10,
        14: 2,
        15: -4,
        16: 30,
        17: 30,
    }
    result = optimise_current_gameweek(
        state=_state(store),
        forecast=_forecast(xp=xp, appearance_bps=10_000),
        universe=_universe(store),
        ruleset=_ruleset(),
        policy=_policy(),
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=0,
        chips_considered=(DecisionChip.NONE,),
    )
    objective = result.selected_action.mechanics.objective_points
    assert objective.denominator == 1
    assert objective.numerator == _independent_no_transfer_oracle(xp)


def test_one_free_transfer_is_selected_without_hit_and_uses_exact_selling_resource(
    tmp_path: Path,
) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    result = optimise_current_gameweek(
        state=_state(store, free_transfers=1),
        forecast=_forecast(),
        universe=_universe(store),
        ruleset=_ruleset(),
        policy=_policy(),
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=1,
        chips_considered=(DecisionChip.NONE,),
    )
    assert len(result.selected_action.transfers) == 1
    move = result.selected_action.transfers[0]
    assert move.outgoing_player_id == OfficialPlayerId(8)
    assert move.incoming_player_id == OfficialPlayerId(16)
    assert result.selected_action.mechanics.hit_points == 0
    assert result.selected_action.bank_after_tenths == 0
    assert result.solver.status is SolverStatus.OPTIMAL
    assert result.solver.gap == result.solver.numeric_error_bound
    assert result.exactness.status is ExactnessStatus.FEASIBLE_INCUMBENT


def test_second_transfer_is_exactly_one_four_point_hit_not_double_counted(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    result = optimise_current_gameweek(
        state=_state(store, free_transfers=1),
        forecast=_forecast(),
        universe=_universe(store),
        ruleset=_ruleset(),
        policy=_policy(),
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=2,
        chips_considered=(DecisionChip.NONE,),
    )
    assert len(result.selected_action.transfers) == 2
    assert {
        (int(move.outgoing_player_id), int(move.incoming_player_id))
        for move in result.selected_action.transfers
    } == {(8, 16), (13, 17)}
    assert result.selected_action.mechanics.hit_points == 4


def test_negative_expected_points_remain_negative_in_decision_values(tmp_path: Path) -> None:
    FileSystemArtifactStore(tmp_path / "artifacts")
    values = build_gameweek_values(
        _forecast(),
        gameweek=2,
        player_ids=(OfficialPlayerId(8),),
    )
    assert values[OfficialPlayerId(8)].expected_points == -6


def test_wildcard_and_free_hit_rebuild_paths_use_verified_ruleset_keys(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    common = dict(
        state=_state(store, free_transfers=1),
        forecast=_forecast(),
        universe=_universe(store),
        ruleset=_ruleset(),
        policy=_policy(),
        use_mode=DecisionUseMode.SHADOW,
        max_normal_transfers=0,
    )
    wildcard = optimise_current_gameweek(
        **common,
        chips_considered=(DecisionChip.NONE, DecisionChip.WILDCARD),
    )
    free_hit = optimise_current_gameweek(
        **common,
        chips_considered=(DecisionChip.NONE, DecisionChip.FREE_HIT),
    )
    assert wildcard.selected_action.chip is DecisionChip.WILDCARD
    assert free_hit.selected_action.chip is DecisionChip.FREE_HIT
    assert free_hit.selected_action.bank_after_tenths == common["state"].bank_tenths


def test_tactical_engine_refuses_production_even_with_full_universe(tmp_path: Path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    with pytest.raises(ValueError, match="shadow-only"):
        optimise_current_gameweek(
            state=_state(store),
            forecast=_forecast(),
            universe=_universe(store),
            ruleset=_ruleset(),
            policy=_policy(),
            use_mode=DecisionUseMode.PRODUCTION,
            max_normal_transfers=15,
            chips_considered=(
                DecisionChip.NONE,
                DecisionChip.TRIPLE_CAPTAIN,
                DecisionChip.BENCH_BOOST,
                DecisionChip.WILDCARD,
                DecisionChip.FREE_HIT,
            ),
        )
