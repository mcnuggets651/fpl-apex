from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from apex_fpl.acquisition import (
    FPL_BOOTSTRAP_URL,
    FPL_FIXTURES_URL,
    HttpResponse,
    NetworkAfterSealError,
    SealedTransport,
    acquire_official_global_world,
    load_official_global_world,
)
from apex_fpl.control.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore


BOOTSTRAP = {
    "elements": [
        {"id": 1, "element_type": 3, "team": 1, "now_cost": 55},
        {"id": 2, "element_type": 4, "team": 2, "now_cost": 70},
    ],
    "teams": [{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}],
    "events": [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}],
}
FIXTURES = [{"id": 10, "team_h": 1, "team_a": 2, "event": 1}]


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


class FixedClock:
    def __init__(self, stamp: datetime):
        self.stamp = stamp

    def now(self) -> datetime:
        return self.stamp


class FakeTransport:
    def __init__(self, bootstrap: object = BOOTSTRAP, fixtures: object = FIXTURES):
        self.payloads = {
            FPL_BOOTSTRAP_URL: _bytes(bootstrap),
            FPL_FIXTURES_URL: _bytes(fixtures),
        }
        self.calls: list[str] = []

    def get(self, url: str, *, params: dict[str, str]) -> HttpResponse:
        assert params == {}
        self.calls.append(url)
        return HttpResponse(
            status_code=200,
            body=self.payloads[url],
            headers={"Content-Type": "application/json", "ETag": '"fixture"'},
        )


def test_same_source_bytes_produce_same_world_across_different_acquisition_runs(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 18, tzinfo=timezone.utc)),
        store=store,
    )
    second = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 19, tzinfo=timezone.utc)),
        store=store,
    )

    assert first.world.world_id == second.world.world_id
    assert first.manifest_artifact_id != second.manifest_artifact_id
    replay_first = load_official_global_world(first.manifest_artifact_id, store=store)
    replay_second = load_official_global_world(second.manifest_artifact_id, store=store)
    assert replay_first.world.world_id == replay_second.world.world_id
    assert {capture.capture_id for capture in replay_first.captures} != {
        capture.capture_id for capture in replay_second.captures
    }


def test_capture_manifest_retains_request_retrieval_freshness_and_raw_digest(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    sealed = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
        store=store,
        freshness_seconds=900,
    )
    manifest_id = dict(sealed.capture_manifest_artifact_ids)["official_fpl_bootstrap"]
    payload = json.loads(store.read_bytes(manifest_id))

    assert payload["source_name"] == "official_fpl_bootstrap"
    assert payload["request"]["method"] == "GET"
    assert payload["request"]["url"] == FPL_BOOTSTRAP_URL
    assert payload["retrieved_at"] == "2026-08-23T20:00:00+00:00"
    assert payload["freshness_seconds"] == 900
    assert payload["body_artifact_id"] == "sha256:" + payload["body_sha256"]
    assert store.verify(payload["body_artifact_id"]) is True
    assert store.verify(manifest_id) is True


def test_replay_requires_no_transport_and_sealed_transport_rejects_network(tmp_path: Path):
    transport = FakeTransport()
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    sealed = acquire_official_global_world(
        season="2026-2027",
        transport=transport,
        clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
        store=store,
    )
    assert transport.calls == [FPL_BOOTSTRAP_URL, FPL_FIXTURES_URL]

    replay = load_official_global_world(sealed.manifest_artifact_id, store=store)
    assert replay.bootstrap == BOOTSTRAP
    assert replay.fixtures == FIXTURES
    assert transport.calls == [FPL_BOOTSTRAP_URL, FPL_FIXTURES_URL]
    with pytest.raises(NetworkAfterSealError):
        SealedTransport().get("https://example.invalid", params={})


def test_global_world_contract_is_manager_neutral(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    sealed = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
        store=store,
    )
    payload = json.dumps(sealed.world.as_dict(), sort_keys=True).casefold()
    assert "entry_id" not in payload
    assert "fpl_entry" not in payload
    assert "manager_state" not in payload
    assert "selling_price" not in payload
    assert sealed.world.player_count == 2
    assert sealed.world.team_count == 2
    assert sealed.world.fixture_count == 1
    assert sealed.world.event_count == 1


def test_corrupted_raw_capture_is_detected_during_replay(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    sealed = acquire_official_global_world(
        season="2026-2027",
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
        store=store,
    )
    source = next(
        row for row in sealed.world.sources if row.source_name == "official_fpl_bootstrap"
    )
    digest = source.content_sha256
    object_path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    object_path.write_bytes(b"corrupt")

    with pytest.raises(ArtifactIntegrityError):
        load_official_global_world(sealed.manifest_artifact_id, store=store)


def test_invalid_official_identity_is_rejected_before_world_seal(tmp_path: Path):
    invalid = dict(BOOTSTRAP)
    invalid["elements"] = [{"id": 1, "element_type": 3, "team": 99, "now_cost": 55}]
    with pytest.raises(ValueError, match="invalid team"):
        acquire_official_global_world(
            season="2026-2027",
            transport=FakeTransport(bootstrap=invalid),
            clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
            store=FileSystemArtifactStore(tmp_path / "artifacts"),
        )
