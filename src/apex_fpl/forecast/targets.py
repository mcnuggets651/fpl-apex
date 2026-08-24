"""Build the exact player/fixture forecast universe from one sealed Official FPL world."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apex_fpl.acquisition.sealed_world import load_official_global_world
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.features import FeatureSnapshot
from apex_fpl.core.forecast import PlayerFixtureTarget
from apex_fpl.core.identity import OfficialPlayerId, POSITION_BY_ELEMENT_TYPE
from apex_fpl.core.ids import FeatureSnapshotId, GlobalWorldId


def _point(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _exact_positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class OfficialForecastTargetSet:
    global_world_id: GlobalWorldId
    feature_snapshot_id: FeatureSnapshotId
    gameweeks: tuple[int, ...]
    targets: tuple[PlayerFixtureTarget, ...]
    global_world_manifest_artifact_id: str

    def __post_init__(self) -> None:
        gameweeks = tuple(sorted(set(self.gameweeks)))
        if not gameweeks:
            raise ValueError("forecast target set requires at least one gameweek")
        keys = [target.key for target in self.targets]
        if len(keys) != len(set(keys)):
            raise ValueError("forecast target set contains duplicate targets")
        object.__setattr__(self, "gameweeks", gameweeks)
        object.__setattr__(self, "targets", tuple(sorted(self.targets, key=lambda row: row.key)))


def build_official_forecast_targets(
    *,
    global_world_manifest_artifact_id: str,
    feature_snapshot: FeatureSnapshot,
    gameweeks: tuple[int, ...],
    store: ArtifactStore,
) -> OfficialForecastTargetSet:
    """Return every current Official player/fixture target in the requested horizon.

    Target construction is replay-only. The sealed world must be exactly the world named by
    the feature snapshot, and every Official capture used for target identity/fixtures must
    already have existed by the feature cutoff. This blocks future fixture/player leakage in
    historical replay.
    """

    requested = tuple(sorted(set(gameweeks)))
    if not requested or any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0
        for item in requested
    ):
        raise ValueError("forecast gameweeks must be positive integers")

    replay = load_official_global_world(global_world_manifest_artifact_id, store=store)
    if replay.world.world_id != feature_snapshot.global_world_id:
        raise ValueError("forecast target world does not match FeatureSnapshot GlobalWorldId")
    cutoff = _point(feature_snapshot.cutoff)
    for capture in replay.captures:
        if capture.source_name in {"official_fpl_bootstrap", "official_fpl_fixtures"}:
            if _point(capture.retrieved_at) > cutoff:
                raise ValueError(
                    f"forecast target source {capture.source_name} was retrieved after feature cutoff"
                )

    fixtures_by_team: dict[int, list[tuple[int, int, int, bool]]] = {}
    for raw in replay.fixtures:
        event = raw.get("event")
        if event is None:
            continue
        if isinstance(event, bool) or not isinstance(event, int):
            raise ValueError("Official fixture event must be an integer or null")
        if event not in requested:
            continue
        fixture_id = _exact_positive_int(raw.get("id"), label="Official fixture id")
        home = _exact_positive_int(raw.get("team_h"), label=f"fixture {fixture_id} home team")
        away = _exact_positive_int(raw.get("team_a"), label=f"fixture {fixture_id} away team")
        fixtures_by_team.setdefault(home, []).append((fixture_id, event, away, True))
        fixtures_by_team.setdefault(away, []).append((fixture_id, event, home, False))

    targets: list[PlayerFixtureTarget] = []
    elements = replay.bootstrap.get("elements")
    if not isinstance(elements, list):
        raise ValueError("Official bootstrap elements are malformed")
    for raw in elements:
        if not isinstance(raw, dict):
            raise ValueError("Official bootstrap player row must be an object")
        player_id = OfficialPlayerId(_exact_positive_int(raw.get("id"), label="Official player id"))
        team_id = _exact_positive_int(raw.get("team"), label=f"player {player_id} team")
        element_type = _exact_positive_int(
            raw.get("element_type"), label=f"player {player_id} element_type"
        )
        try:
            position = POSITION_BY_ELEMENT_TYPE[element_type]
        except KeyError as exc:
            raise ValueError(f"player {player_id} has invalid Official element_type") from exc
        for fixture_id, gameweek, opponent, is_home in fixtures_by_team.get(team_id, []):
            targets.append(
                PlayerFixtureTarget(
                    fixture_id=fixture_id,
                    gameweek=gameweek,
                    player_id=player_id,
                    team_id=team_id,
                    opponent_team_id=opponent,
                    is_home=is_home,
                    position=position,
                )
            )

    return OfficialForecastTargetSet(
        global_world_id=replay.world.world_id,
        feature_snapshot_id=feature_snapshot.snapshot_id,
        gameweeks=requested,
        targets=tuple(targets),
        global_world_manifest_artifact_id=str(global_world_manifest_artifact_id),
    )
