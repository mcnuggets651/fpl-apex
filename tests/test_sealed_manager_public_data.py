from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
from pathlib import Path

import pytest

from apex_fpl.acquisition import (
    FPL_API_BASE,
    HttpResponse,
    acquire_official_manager_public_data,
    load_official_manager_public_data,
)
from apex_fpl.control.artifact_store import ArtifactIntegrityError, FileSystemArtifactStore


ENTRY_ID = 63984
GW = 1
SUMMARY = {"id": ENTRY_ID, "name": "Apex", "player_first_name": "Test"}
HISTORY = {
    "current": [
        {
            "event": GW,
            "event_transfers": 0,
            "event_transfers_cost": 0,
            "bank": 245,
        }
    ],
    "chips": [],
}
TRANSFERS: list[dict[str, object]] = []
PICKS = {
    "picks": [
        {
            "element": index,
            "position": index,
            "is_captain": index == 1,
            "is_vice_captain": index == 2,
        }
        for index in range(1, 16)
    ],
    "entry_history": {
        "event": GW,
        "bank": 245,
        "event_transfers": 0,
        "event_transfers_cost": 0,
        "value": 1000,
    },
    "active_chip": None,
}


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _urls(entry_id: int = ENTRY_ID, gameweek: int = GW) -> dict[str, bytes]:
    base = f"{FPL_API_BASE}/entry/{entry_id}"
    return {
        f"{base}/": _bytes(SUMMARY),
        f"{base}/history/": _bytes(HISTORY),
        f"{base}/transfers/": _bytes(TRANSFERS),
        f"{base}/event/{gameweek}/picks/": _bytes(PICKS),
    }


class FixedClock:
    def __init__(self, stamp: datetime):
        self.stamp = stamp

    def now(self) -> datetime:
        return self.stamp


class FakeTransport:
    def __init__(self, payloads: dict[str, bytes] | None = None):
        self.payloads = payloads or _urls()
        self.calls: list[str] = []

    def get(self, url: str, *, params: dict[str, str]) -> HttpResponse:
        assert params == {}
        self.calls.append(url)
        return HttpResponse(
            status_code=200,
            body=self.payloads[url],
            headers={"Content-Type": "application/json", "ETag": '"manager-fixture"'},
        )


def test_same_manager_source_bytes_have_same_semantic_snapshot_across_capture_times(
    tmp_path: Path,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first = acquire_official_manager_public_data(
        entry_id=ENTRY_ID,
        published_gameweek=GW,
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
        store=store,
    )
    second = acquire_official_manager_public_data(
        entry_id=ENTRY_ID,
        published_gameweek=GW,
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 21, tzinfo=timezone.utc)),
        store=store,
    )

    assert first.snapshot.snapshot_id == second.snapshot.snapshot_id
    assert first.manifest_artifact_id != second.manifest_artifact_id
    replay_first = load_official_manager_public_data(first.manifest_artifact_id, store=store)
    replay_second = load_official_manager_public_data(second.manifest_artifact_id, store=store)
    assert replay_first.snapshot.snapshot_id == replay_second.snapshot.snapshot_id
    assert {capture.capture_id for capture in replay_first.captures} != {
        capture.capture_id for capture in replay_second.captures
    }


def test_manager_acquisition_retains_all_four_raw_official_surfaces_and_replays_offline(
    tmp_path: Path,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    transport = FakeTransport()
    sealed = acquire_official_manager_public_data(
        entry_id=ENTRY_ID,
        published_gameweek=GW,
        transport=transport,
        clock=FixedClock(datetime(2026, 8, 23, 21, tzinfo=timezone.utc)),
        store=store,
        freshness_seconds=120,
    )
    assert transport.calls == list(_urls())
    assert {name for name, _ in sealed.capture_manifest_artifact_ids} == {
        "official_fpl_entry_summary",
        "official_fpl_entry_history",
        "official_fpl_entry_transfers",
        "official_fpl_entry_picks",
    }
    for _, manifest_id in sealed.capture_manifest_artifact_ids:
        payload = json.loads(store.read_bytes(manifest_id))
        assert payload["freshness_seconds"] == 120
        assert payload["body_artifact_id"] == "sha256:" + payload["body_sha256"]
        assert store.verify(payload["body_artifact_id"])

    replay = load_official_manager_public_data(sealed.manifest_artifact_id, store=store)
    assert replay.summary == SUMMARY
    assert replay.history == HISTORY
    assert replay.transfers == TRANSFERS
    assert replay.picks == PICKS
    assert transport.calls == list(_urls())


def test_manager_replay_api_exposes_no_network_or_clock_port():
    parameters = inspect.signature(load_official_manager_public_data).parameters
    assert set(parameters) == {"manifest_artifact_id", "store"}
    assert "transport" not in parameters
    assert "clock" not in parameters


def test_manager_snapshot_identity_changes_when_official_source_bytes_change(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    first = acquire_official_manager_public_data(
        entry_id=ENTRY_ID,
        published_gameweek=GW,
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
        store=store,
    )
    changed = _urls()
    changed_summary = dict(SUMMARY, name="Apex changed")
    changed[f"{FPL_API_BASE}/entry/{ENTRY_ID}/"] = _bytes(changed_summary)
    second = acquire_official_manager_public_data(
        entry_id=ENTRY_ID,
        published_gameweek=GW,
        transport=FakeTransport(changed),
        clock=FixedClock(datetime(2026, 8, 23, 20, tzinfo=timezone.utc)),
        store=store,
    )
    assert first.snapshot.snapshot_id != second.snapshot.snapshot_id


def test_invalid_public_picks_are_rejected_before_manager_seal(tmp_path: Path):
    invalid = dict(PICKS)
    rows = [dict(row) for row in PICKS["picks"]]
    rows[14]["element"] = 1
    invalid["picks"] = rows
    payloads = _urls()
    payloads[f"{FPL_API_BASE}/entry/{ENTRY_ID}/event/{GW}/picks/"] = _bytes(invalid)

    with pytest.raises(ValueError, match="duplicate player IDs"):
        acquire_official_manager_public_data(
            entry_id=ENTRY_ID,
            published_gameweek=GW,
            transport=FakeTransport(payloads),
            clock=FixedClock(datetime(2026, 8, 23, 21, tzinfo=timezone.utc)),
            store=FileSystemArtifactStore(tmp_path / "artifacts"),
        )


def test_manager_entry_or_gameweek_mismatch_is_rejected_before_seal(tmp_path: Path):
    wrong_summary = dict(SUMMARY, id=ENTRY_ID + 1)
    payloads = _urls()
    payloads[f"{FPL_API_BASE}/entry/{ENTRY_ID}/"] = _bytes(wrong_summary)
    with pytest.raises(ValueError, match="summary ID"):
        acquire_official_manager_public_data(
            entry_id=ENTRY_ID,
            published_gameweek=GW,
            transport=FakeTransport(payloads),
            clock=FixedClock(datetime(2026, 8, 23, 21, tzinfo=timezone.utc)),
            store=FileSystemArtifactStore(tmp_path / "entry-artifacts"),
        )

    wrong_picks = dict(PICKS)
    wrong_picks["entry_history"] = dict(PICKS["entry_history"], event=GW + 1)
    payloads = _urls()
    payloads[f"{FPL_API_BASE}/entry/{ENTRY_ID}/event/{GW}/picks/"] = _bytes(wrong_picks)
    with pytest.raises(ValueError, match="Gameweek mismatch"):
        acquire_official_manager_public_data(
            entry_id=ENTRY_ID,
            published_gameweek=GW,
            transport=FakeTransport(payloads),
            clock=FixedClock(datetime(2026, 8, 23, 21, tzinfo=timezone.utc)),
            store=FileSystemArtifactStore(tmp_path / "gw-artifacts"),
        )


def test_corrupted_manager_raw_capture_is_detected_during_replay(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    sealed = acquire_official_manager_public_data(
        entry_id=ENTRY_ID,
        published_gameweek=GW,
        transport=FakeTransport(),
        clock=FixedClock(datetime(2026, 8, 23, 21, tzinfo=timezone.utc)),
        store=store,
    )
    source = next(
        row
        for row in sealed.snapshot.sources
        if row.source_name == "official_fpl_entry_history"
    )
    digest = source.content_sha256
    path = tmp_path / "artifacts" / "objects" / "sha256" / digest[:2] / digest
    path.write_bytes(b"corrupt")

    with pytest.raises(ArtifactIntegrityError):
        load_official_manager_public_data(sealed.manifest_artifact_id, store=store)
