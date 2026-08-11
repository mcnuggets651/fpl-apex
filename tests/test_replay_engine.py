from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from apex_fpl.replay.audit import audit_replay_store
from apex_fpl.replay.context import AsOfContext, SourceManifestEntry
from apex_fpl.replay.engine import (
    DecisionSurface,
    SeasonScore,
    compare_season_scores,
    run_decision_season,
    score_season,
)
from apex_fpl.replay.legality import (
    advance_state,
    fpl_selling_price,
    initialise_replay_state,
    validate_action,
)
from apex_fpl.replay.scoring import WeeklyScore, score_weekly_action
from apex_fpl.replay.state import ReplayState, WeeklyAction


UTC = timezone.utc
DIGEST = "a" * 64


def _source(cutoff: datetime) -> SourceManifestEntry:
    return SourceManifestEntry(
        name="official_fpl",
        revision="fixture",
        content_sha256=DIGEST,
        published_at=cutoff - timedelta(hours=2),
        available_at=cutoff - timedelta(hours=1),
        retrieved_at=cutoff,
    )


def _players() -> pd.DataFrame:
    positions = ["GK", "GK", *(["DEF"] * 5), *(["MID"] * 5), *(["FWD"] * 3)]
    return pd.DataFrame(
        {
            "player_id": range(1, 16),
            "position": positions,
            "team": [f"T{(idx - 1) // 3}" for idx in range(1, 16)],
            "price": [5.0] * 15,
        }
    )


def _state(*, free_transfers: int = 1, bank: float = 0.0) -> ReplayState:
    return ReplayState(
        season="2025-2026",
        next_gameweek=2,
        squad=tuple(range(1, 16)),
        bank=bank,
        free_transfers=free_transfers,
        purchase_prices=tuple((pid, 5.0) for pid in range(1, 16)),
    )


def _action(**overrides) -> WeeklyAction:
    values = {
        "gameweek": 2,
        "transfers": (),
        "chip": None,
        "squad": tuple(range(1, 16)),
        "xi": (1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14),
        "bench_order": (2, 6, 7, 15),
        "captain_id": 13,
        "vice_captain_id": 14,
        "hit_cost": 0,
    }
    values.update(overrides)
    return WeeklyAction(**values)


def _outcomes(*, no_shows: set[int] | None = None) -> pd.DataFrame:
    frame = _players()[["player_id", "position"]].copy()
    frame["minutes"] = 90
    frame["total_points"] = frame["player_id"]
    if no_shows:
        frame.loc[frame["player_id"].isin(no_shows), ["minutes", "total_points"]] = 0
    return frame


def test_selling_price_uses_half_of_profit_rounded_down() -> None:
    assert fpl_selling_price(5.0, 5.3) == 5.1
    assert fpl_selling_price(5.0, 5.4) == 5.2
    assert fpl_selling_price(5.0, 4.8) == 4.8


def test_initial_state_uses_unlimited_selection_and_zero_free_transfers() -> None:
    state = initialise_replay_state(
        season="2025-26",
        squad=tuple(range(1, 16)),
        players=_players(),
    )
    assert state.next_gameweek == 1
    assert state.free_transfers == 0
    assert state.bank == 25.0


def test_action_legality_reconciles_hit_and_cash() -> None:
    players = pd.concat(
        [
            _players(),
            pd.DataFrame([{"player_id": 16, "position": "FWD", "team": "T9", "price": 5.0}]),
        ],
        ignore_index=True,
    )
    action = _action(
        transfers=((15, 16),),
        squad=tuple(range(1, 15)) + (16,),
        bench_order=(2, 6, 7, 16),
    )
    validate_action(_state(), action, players)
    next_state = advance_state(_state(), action, players)
    assert next_state.free_transfers == 1
    assert 16 in next_state.squad and 15 not in next_state.squad
    assert dict(next_state.purchase_prices)[16] == 5.0


def test_action_rejects_incorrect_hit() -> None:
    with pytest.raises(ValueError, match="hit cost does not reconcile"):
        validate_action(_state(free_transfers=1), _action(hit_cost=4), _players())


def test_free_hit_reverts_permanent_state() -> None:
    temporary = _action(chip="free_hit", squad=tuple(range(1, 16)))
    next_state = advance_state(_state(bank=1.0), temporary, _players())
    assert next_state.squad == tuple(range(1, 16))
    assert next_state.bank == 1.0
    assert next_state.chips_used == ((2, "free_hit"),)


def test_scorer_applies_goalkeeper_and_formation_aware_autosubs() -> None:
    action = _action(
        xi=(1, 3, 4, 5, 8, 9, 10, 11, 12, 13, 14),
        bench_order=(2, 15, 6, 7),
    )
    score = score_weekly_action(action, _outcomes(no_shows={1, 3, 13}))
    assert (1, 2) in score.autosubs
    # FWD 15 cannot replace missing DEF 3 in a 3-defender formation, so DEF 6 enters.
    assert (3, 6) in score.autosubs
    # Captain 13 did not appear, so vice 14 receives the captain multiplier.
    assert score.captain_scored == 14
    assert score.captain_multiplier == 2


def test_bench_boost_and_triple_captain_score_exactly() -> None:
    normal = score_weekly_action(_action(), _outcomes())
    bench_boost = score_weekly_action(_action(chip="bench_boost"), _outcomes())
    triple = score_weekly_action(_action(chip="triple_captain"), _outcomes())
    assert bench_boost.gross_points - normal.gross_points == sum((2, 6, 7, 15))
    assert triple.gross_points - normal.gross_points == 13


def test_decision_surface_rejects_target_columns() -> None:
    deadline = datetime(2025, 8, 23, 10, tzinfo=UTC)
    context = AsOfContext(
        season="2025-2026",
        gameweek=2,
        deadline_utc=deadline,
        cutoff_utc=deadline - timedelta(hours=2),
        code_sha="deadbeef",
        config_sha256=DIGEST,
        random_seed=7,
        sources=(),
    )
    surface = DecisionSurface(
        context=context,
        players=_players().assign(total_points=0),
        projections=pd.DataFrame({"player_id": range(1, 16), "gw": 2, "xp": 1.0}),
    )
    with pytest.raises(ValueError, match="decision firewall"):
        surface.validate()


def test_store_audit_never_treats_outcomes_as_deadline_bundles(tmp_path: Path) -> None:
    outcomes = tmp_path / "2025-2026" / "outcomes"
    outcomes.mkdir(parents=True)
    for gameweek in range(1, 39):
        (outcomes / f"GW{gameweek}.csv").write_text("player_id,total_points\n", encoding="utf-8")
    audit = audit_replay_store(tmp_path)
    assert not audit.apex_replay_eligible
    assert len(audit.incomplete_gameweeks) == 38
    assert len(audit.outcome_gameweeks) == 38


def test_store_audit_verifies_cutoff_and_file_content_hashes(tmp_path: Path) -> None:
    directory = tmp_path / "2025-2026" / "GW1"
    directory.mkdir(parents=True)
    files = {}
    for filename, content in {
        "players.csv": "player_id,position,team,price\n1,GK,A,4.5\n",
        "projections.csv": "player_id,gw,xp\n1,1,3.0\n",
    }.items():
        (directory / filename).write_text(content, encoding="utf-8")
        files[filename] = {"sha256": hashlib.sha256(content.encode()).hexdigest()}
    manifest = {
        "season": "2025-2026",
        "gameweek": 1,
        "deadline_utc": "2025-08-16T10:00:00+00:00",
        "cutoff_utc": "2025-08-16T08:00:00+00:00",
        "sources": [{"available_at": "2025-08-16T07:00:00+00:00"}],
        "files": files,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    audit = audit_replay_store(tmp_path)
    assert audit.complete_gameweeks == (1,)

    manifest["sources"][0]["available_at"] = "2025-08-16T08:00:01+00:00"
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert audit_replay_store(tmp_path).complete_gameweeks == ()


def test_full_season_engine_seals_38_deterministic_decisions_before_scoring() -> None:
    class HoldPolicy:
        name = "hold"

        def decide(self, state, surface):
            return _action(gameweek=surface.context.gameweek)

    surfaces = []
    for gameweek in range(1, 39):
        deadline = datetime(2025, 8, 1, tzinfo=UTC) + timedelta(days=7 * gameweek)
        cutoff = deadline - timedelta(hours=2)
        context = AsOfContext(
            season="2025-2026",
            gameweek=gameweek,
            deadline_utc=deadline,
            cutoff_utc=cutoff,
            code_sha="deadbeef",
            config_sha256=DIGEST,
            random_seed=7,
            sources=(_source(cutoff),),
        )
        surfaces.append(
            DecisionSurface(
                context=context,
                players=_players(),
                projections=pd.DataFrame(
                    {"player_id": range(1, 16), "gw": gameweek, "xp": 1.0}
                ),
            )
        )
    initial = initialise_replay_state(
        season="2025-2026",
        squad=tuple(range(1, 16)),
        players=_players(),
    )
    decisions = run_decision_season(
        initial_state=initial,
        surfaces=tuple(surfaces),
        policy=HoldPolicy(),
    )
    outcomes = {gameweek: _outcomes() for gameweek in range(1, 39)}
    score = score_season(decisions, outcomes)
    assert len(decisions.decisions) == 38
    assert decisions.decisions[0].action.hit_cost == 0
    assert decisions.decisions[0].state_after.free_transfers == 1
    assert len(decisions.final_decision_sha256) == 64
    assert len(decisions.decisions[0].surface_sha256) == 64
    assert score.total_points == score.weeks[0].net_points * 38


def test_season_comparison_uses_paired_gameweek_blocks() -> None:
    def season(policy: str, weekly_points: int) -> SeasonScore:
        weeks = tuple(
            WeeklyScore(
                gameweek=gw,
                gross_points=weekly_points,
                hit_cost=0,
                net_points=weekly_points,
                starters=(),
                autosubs=(),
                captain_scored=1,
                captain_multiplier=2,
                bench_points=0,
            )
            for gw in range(1, 39)
        )
        return SeasonScore(
            season="2025-2026",
            policy=policy,
            total_points=weekly_points * 38,
            gross_points=weekly_points * 38,
            hit_cost=0,
            weeks=weeks,
            final_decision_sha256=DIGEST,
        )

    comparison = compare_season_scores(
        season("apex", 61),
        season("baseline", 60),
        samples=200,
    )
    assert comparison.realised_delta == 38
    assert comparison.lower_90 == 38
    assert comparison.probability_candidate_better == 1.0
    assert comparison.classification == "strong_pass"
