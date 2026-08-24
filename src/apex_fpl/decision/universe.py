"""Build decision candidate universes from one sealed Official FPL world."""

from __future__ import annotations

from typing import Iterable

from apex_fpl.acquisition.sealed_world import load_official_global_world
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.decision import CandidatePlayer, CandidateUniverse, CandidateUniverseScope
from apex_fpl.core.identity import OfficialPlayerId, POSITION_BY_ELEMENT_TYPE


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def build_official_candidate_universe(
    *,
    global_world_manifest_artifact_id: str,
    store: ArtifactStore,
    included_player_ids: Iterable[OfficialPlayerId] | None = None,
) -> CandidateUniverse:
    """Create FULL_OFFICIAL or explicitly SCOPED decision universe from sealed identity."""

    replay = load_official_global_world(global_world_manifest_artifact_id, store=store)
    raw_elements = replay.bootstrap.get("elements")
    if not isinstance(raw_elements, list) or not raw_elements:
        raise ValueError("Official bootstrap has no candidate players")
    requested = None if included_player_ids is None else set(included_player_ids)
    all_ids: set[OfficialPlayerId] = set()
    players: list[CandidatePlayer] = []
    for raw in raw_elements:
        if not isinstance(raw, dict):
            raise ValueError("Official player candidate row must be an object")
        player_id = OfficialPlayerId(_positive_int(raw.get("id"), label="Official player id"))
        if player_id in all_ids:
            raise ValueError(f"duplicate Official candidate player ID: {player_id}")
        all_ids.add(player_id)
        if requested is not None and player_id not in requested:
            continue
        team_id = _positive_int(raw.get("team"), label=f"candidate {player_id} team")
        element_type = _positive_int(
            raw.get("element_type"), label=f"candidate {player_id} element_type"
        )
        price = _positive_int(raw.get("now_cost"), label=f"candidate {player_id} price")
        try:
            position = POSITION_BY_ELEMENT_TYPE[element_type]
        except KeyError as exc:
            raise ValueError(f"candidate {player_id} has invalid Official position") from exc
        players.append(
            CandidatePlayer(
                player_id=player_id,
                team_id=team_id,
                position=position,
                current_price_tenths=price,
            )
        )
    if requested is not None:
        missing = sorted(int(item) for item in requested - all_ids)
        if missing:
            raise ValueError(f"scoped candidate universe contains unknown Official IDs: {missing}")
    scope = (
        CandidateUniverseScope.FULL_OFFICIAL
        if requested is None or requested == all_ids
        else CandidateUniverseScope.SCOPED
    )
    return CandidateUniverse(
        global_world_id=replay.world.world_id,
        scope=scope,
        players=tuple(players),
        official_player_count=len(all_ids),
        source_artifact_ids=(str(global_world_manifest_artifact_id),),
    )
