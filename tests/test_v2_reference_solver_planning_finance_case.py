from __future__ import annotations

from types import SimpleNamespace

from apex_fpl.control.artifact_store import ArtifactStore, FileSystemArtifactStore
from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.decision import CandidatePlayer, CandidateUniverse, CandidateUniverseScope
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import GlobalWorldId

from reference_solver_planning_finance_case import (
    _FINANCE_CLUB_ID,
    _FINANCE_CLUB_OWNED_IDS,
    _FINANCE_EXTRA_PLAYER,
    _finance_candidate_universe,
)


_POSITIONS = {
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
}


def _base_universe(store: ArtifactStore) -> CandidateUniverse:
    source = store.put_bytes(b"focused-finance-regression-source").artifact_id
    return CandidateUniverse(
        global_world_id=GlobalWorldId(
            canonical_sha256({"schema_name": "focused-finance-regression-world"})
        ),
        scope=CandidateUniverseScope.FULL_OFFICIAL,
        players=tuple(
            CandidatePlayer(
                player_id=OfficialPlayerId(player_id),
                team_id=player_id,
                position=position,
                current_price_tenths=51 if player_id == 16 else 50,
            )
            for player_id, position in _POSITIONS.items()
        ),
        official_player_count=len(_POSITIONS),
        source_artifact_ids=(source,),
    )


def test_finance_universe_saturates_target_club_without_price_or_position_drift(tmp_path) -> None:
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    verified = SimpleNamespace(candidate_universe=_base_universe(store))

    universe, artifact_id = _finance_candidate_universe(verified, store=store)

    assert store.verify(artifact_id)
    target = next(row for row in universe.players if row.player_id == _FINANCE_EXTRA_PLAYER)
    assert target.team_id == _FINANCE_CLUB_ID
    assert target.position == "MID"
    assert target.current_price_tenths == 51
    assert {
        int(row.player_id)
        for row in universe.players
        if row.team_id == _FINANCE_CLUB_ID and row.player_id != _FINANCE_EXTRA_PLAYER
    } == _FINANCE_CLUB_OWNED_IDS
    assert universe.official_player_count == 16
