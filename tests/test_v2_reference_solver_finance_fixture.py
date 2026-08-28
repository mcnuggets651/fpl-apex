from __future__ import annotations

from types import SimpleNamespace

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import CandidatePlayer, CandidateUniverse, CandidateUniverseScope
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import GlobalWorldId

from reference_solver_planning_finance_case import _finance_candidate_universe


def _verified_with_players(store, players: tuple[CandidatePlayer, ...]):
    source = store.put_bytes(b"finance-fixture-unit-source").artifact_id
    universe = CandidateUniverse(
        global_world_id=GlobalWorldId(
            canonical_sha256({"schema_name": "finance-fixture-unit-world"})
        ),
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=players,
        official_player_count=len(players),
        source_artifact_ids=(source,),
    )
    return SimpleNamespace(candidate_universe=universe)


def test_finance_case_reuses_retained_player_16_without_duplicate(tmp_path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    player = CandidatePlayer(
        player_id=OfficialPlayerId(16),
        team_id=16,
        position="MID",
        current_price_tenths=51,
    )
    verified = _verified_with_players(store, (player,))

    universe, artifact_id = _finance_candidate_universe(verified, store=store)

    assert universe == verified.candidate_universe
    assert len(universe.players) == 1
    assert universe.players[0].player_id == OfficialPlayerId(16)
    assert store.verify(artifact_id)


def test_finance_case_rejects_drifted_retained_player_16(tmp_path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    player = CandidatePlayer(
        player_id=OfficialPlayerId(16),
        team_id=16,
        position="MID",
        current_price_tenths=50,
    )
    verified = _verified_with_players(store, (player,))

    with pytest.raises(ValueError, match="£5.1m MID qualification target"):
        _finance_candidate_universe(verified, store=store)


def test_finance_case_still_injects_target_for_older_fixture(tmp_path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    player = CandidatePlayer(
        player_id=OfficialPlayerId(8),
        team_id=8,
        position="MID",
        current_price_tenths=50,
    )
    verified = _verified_with_players(store, (player,))

    universe, artifact_id = _finance_candidate_universe(verified, store=store)

    assert len(universe.players) == 2
    target = next(row for row in universe.players if row.player_id == OfficialPlayerId(16))
    assert target.team_id == 16
    assert target.position == "MID"
    assert target.current_price_tenths == 51
    assert universe.official_player_count == 2
    assert store.verify(artifact_id)
