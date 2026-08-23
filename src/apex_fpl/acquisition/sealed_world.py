"""Acquire, seal and replay the manager-neutral official FPL GlobalWorld."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.world import GlobalWorld, WorldSource

from .contracts import Clock, HttpTransport, RawCapture, SourceRequest, StoredRawCapture


FPL_BOOTSTRAP_URL = "https://fantasy.premierleague.com/api/bootstrap-static/"
FPL_FIXTURES_URL = "https://fantasy.premierleague.com/api/fixtures/"
SEALED_WORLD_SCHEMA_NAME = "apex-sealed-global-world"
SEALED_WORLD_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SealedGlobalWorld:
    world: GlobalWorld
    manifest_artifact_id: str
    capture_manifest_artifact_ids: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "global_world_id": str(self.world.world_id),
            "manifest_artifact_id": self.manifest_artifact_id,
            "capture_manifest_artifact_ids": [
                [name, artifact_id]
                for name, artifact_id in self.capture_manifest_artifact_ids
            ],
        }


@dataclass(frozen=True, slots=True)
class ReplayedGlobalWorld:
    world: GlobalWorld
    bootstrap: dict[str, Any]
    fixtures: list[dict[str, Any]]
    captures: tuple[RawCapture, ...]


def capture_request(
    request: SourceRequest,
    *,
    transport: HttpTransport,
    clock: Clock,
    store: ArtifactStore,
) -> StoredRawCapture:
    response = transport.get(request.url, params=request.params_dict())
    if response.status_code < 200 or response.status_code >= 300:
        raise RuntimeError(
            f"{request.source_name} acquisition returned HTTP {response.status_code}"
        )
    body_ref = store.put_bytes(
        response.body,
        media_type="application/json",
        schema_name=request.schema_name,
        schema_version=request.schema_version,
    )
    capture = RawCapture.create(
        request=request,
        retrieved_at=clock.now(),
        response=response,
        body_artifact_id=body_ref.artifact_id,
        body_sha256=body_ref.digest,
        body_size=body_ref.size,
    )
    manifest_ref = store.put_bytes(
        canonical_json_bytes(capture.as_dict()),
        media_type="application/json",
        schema_name="apex-raw-capture",
        schema_version="1",
    )
    return StoredRawCapture(capture=capture, manifest_artifact_id=manifest_ref.artifact_id)


def _decode_json(content: bytes, *, source_name: str) -> Any:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source_name} raw capture is not valid UTF-8 JSON") from exc


def _validate_official_payloads(
    bootstrap: object,
    fixtures: object,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(bootstrap, dict):
        raise ValueError("official bootstrap payload must be an object")
    if not isinstance(fixtures, list):
        raise ValueError("official fixtures payload must be an array")
    elements = bootstrap.get("elements")
    teams = bootstrap.get("teams")
    events = bootstrap.get("events")
    if not isinstance(elements, list) or not elements:
        raise ValueError("official bootstrap has no players")
    if not isinstance(teams, list) or not teams:
        raise ValueError("official bootstrap has no teams")
    if not isinstance(events, list) or not events:
        raise ValueError("official bootstrap has no events")

    team_ids = {int(row["id"]) for row in teams}
    player_ids = [int(row["id"]) for row in elements]
    if len(player_ids) != len(set(player_ids)):
        raise ValueError("official bootstrap has duplicate player IDs")
    for player in elements:
        player_id = int(player["id"])
        if int(player.get("element_type", 0)) not in {1, 2, 3, 4}:
            raise ValueError(f"official bootstrap has invalid position for player_id={player_id}")
        if int(player.get("team", -1)) not in team_ids:
            raise ValueError(f"official bootstrap has invalid team for player_id={player_id}")
        if int(player.get("now_cost", 0) or 0) <= 0:
            raise ValueError(f"official bootstrap has invalid price for player_id={player_id}")

    fixture_rows: list[dict[str, Any]] = []
    fixture_ids: list[int] = []
    for item in fixtures:
        if not isinstance(item, dict):
            raise ValueError("official fixture row must be an object")
        fixture = dict(item)
        fixture_rows.append(fixture)
        if fixture.get("id") is not None:
            fixture_ids.append(int(fixture["id"]))
        if int(fixture.get("team_h", -1)) not in team_ids:
            raise ValueError(f"fixture {fixture.get('id')} has invalid home team")
        if int(fixture.get("team_a", -1)) not in team_ids:
            raise ValueError(f"fixture {fixture.get('id')} has invalid away team")
    if len(fixture_ids) != len(set(fixture_ids)):
        raise ValueError("official fixtures have duplicate fixture IDs")
    return dict(bootstrap), fixture_rows


def _source_by_name(world: GlobalWorld, name: str) -> WorldSource:
    for source in world.sources:
        if source.source_name == name:
            return source
    raise ValueError(f"GlobalWorld is missing required source: {name}")


def acquire_official_global_world(
    *,
    season: str,
    transport: HttpTransport,
    clock: Clock,
    store: ArtifactStore,
    freshness_seconds: int = 1800,
) -> SealedGlobalWorld:
    requests = (
        SourceRequest.create(
            source_name="official_fpl_bootstrap",
            url=FPL_BOOTSTRAP_URL,
            freshness_seconds=freshness_seconds,
            schema_name="official-fpl-bootstrap",
            schema_version="1",
        ),
        SourceRequest.create(
            source_name="official_fpl_fixtures",
            url=FPL_FIXTURES_URL,
            freshness_seconds=freshness_seconds,
            schema_name="official-fpl-fixtures",
            schema_version="1",
        ),
    )
    stored = tuple(
        capture_request(request, transport=transport, clock=clock, store=store)
        for request in requests
    )
    by_name = {row.capture.source_name: row for row in stored}
    bootstrap_capture = by_name["official_fpl_bootstrap"].capture
    fixtures_capture = by_name["official_fpl_fixtures"].capture
    bootstrap, fixtures = _validate_official_payloads(
        _decode_json(
            store.read_bytes(bootstrap_capture.body_artifact_id),
            source_name=bootstrap_capture.source_name,
        ),
        _decode_json(
            store.read_bytes(fixtures_capture.body_artifact_id),
            source_name=fixtures_capture.source_name,
        ),
    )

    sources = tuple(
        WorldSource(
            source_name=row.capture.source_name,
            artifact_id=row.capture.body_artifact_id,
            content_sha256=row.capture.body_sha256,
            schema_name=row.capture.schema_name,
            schema_version=row.capture.schema_version,
        )
        for row in stored
    )
    world = GlobalWorld.build(
        season=season,
        sources=sources,
        player_count=len(bootstrap["elements"]),
        team_count=len(bootstrap["teams"]),
        fixture_count=len(fixtures),
        event_count=len(bootstrap["events"]),
    )
    capture_manifests = tuple(
        sorted(
            (
                (row.capture.source_name, row.manifest_artifact_id)
                for row in stored
            ),
            key=lambda item: item[0],
        )
    )
    envelope = {
        "schema_name": SEALED_WORLD_SCHEMA_NAME,
        "schema_version": SEALED_WORLD_SCHEMA_VERSION,
        "global_world": world.as_dict(),
        "capture_manifests": [
            {"source_name": name, "artifact_id": artifact_id}
            for name, artifact_id in capture_manifests
        ],
    }
    manifest_ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=SEALED_WORLD_SCHEMA_NAME,
        schema_version=str(SEALED_WORLD_SCHEMA_VERSION),
    )
    return SealedGlobalWorld(
        world=world,
        manifest_artifact_id=manifest_ref.artifact_id,
        capture_manifest_artifact_ids=capture_manifests,
    )


def load_official_global_world(
    manifest_artifact_id: str,
    *,
    store: ArtifactStore,
) -> ReplayedGlobalWorld:
    """Replay a sealed world strictly from ArtifactStore. There is no transport argument."""

    envelope = _decode_json(
        store.read_bytes(manifest_artifact_id),
        source_name="sealed_global_world_manifest",
    )
    if not isinstance(envelope, dict):
        raise ValueError("sealed GlobalWorld manifest must be an object")
    if envelope.get("schema_name") != SEALED_WORLD_SCHEMA_NAME:
        raise ValueError("not an Apex sealed GlobalWorld manifest")
    if int(envelope.get("schema_version", -1)) != SEALED_WORLD_SCHEMA_VERSION:
        raise ValueError("unsupported sealed GlobalWorld schema_version")
    world_payload = envelope.get("global_world")
    capture_rows = envelope.get("capture_manifests")
    if not isinstance(world_payload, dict) or not isinstance(capture_rows, list):
        raise ValueError("sealed GlobalWorld manifest is incomplete")
    world = GlobalWorld.from_dict(dict(world_payload))

    captures: list[RawCapture] = []
    for row in capture_rows:
        if not isinstance(row, dict):
            raise ValueError("capture manifest reference must be an object")
        raw = _decode_json(
            store.read_bytes(str(row["artifact_id"])),
            source_name=f"capture_manifest:{row.get('source_name')}",
        )
        if not isinstance(raw, dict):
            raise ValueError("raw capture manifest must be an object")
        capture = RawCapture.from_dict(dict(raw))
        if capture.source_name != str(row["source_name"]):
            raise ValueError("capture manifest source-name mismatch")
        source = _source_by_name(world, capture.source_name)
        if source.artifact_id != capture.body_artifact_id:
            raise ValueError("capture body does not match sealed GlobalWorld source")
        body = store.read_bytes(capture.body_artifact_id)
        if len(body) != capture.body_size:
            raise ValueError("raw capture body size mismatch")
        captures.append(capture)

    by_name = {capture.source_name: capture for capture in captures}
    if set(by_name) != {source.source_name for source in world.sources}:
        raise ValueError("sealed GlobalWorld capture coverage is incomplete")
    bootstrap, fixtures = _validate_official_payloads(
        _decode_json(
            store.read_bytes(by_name["official_fpl_bootstrap"].body_artifact_id),
            source_name="official_fpl_bootstrap",
        ),
        _decode_json(
            store.read_bytes(by_name["official_fpl_fixtures"].body_artifact_id),
            source_name="official_fpl_fixtures",
        ),
    )
    if (
        len(bootstrap["elements"]) != world.player_count
        or len(bootstrap["teams"]) != world.team_count
        or len(bootstrap["events"]) != world.event_count
        or len(fixtures) != world.fixture_count
    ):
        raise ValueError("replayed source counts do not match GlobalWorld")
    return ReplayedGlobalWorld(
        world=world,
        bootstrap=bootstrap,
        fixtures=fixtures,
        captures=tuple(sorted(captures, key=lambda item: item.source_name)),
    )
