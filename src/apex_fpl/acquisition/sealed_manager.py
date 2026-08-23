"""Acquire, seal and replay manager-specific Official FPL public data.

Manager-specific entry data is deliberately excluded from manager-neutral ``GlobalWorld``.
Every Official response used for manager-state reconstruction is retained byte-for-byte
through the common V2 RawCapture/ArtifactStore boundary. Semantic snapshot identity
uses source-content identities, entry and target Gameweek; retrieval time remains audit
metadata on RawCapture and therefore does not create false semantic differences.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Iterable

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.ids import ManagerPublicSnapshotId

from .contracts import Clock, HttpTransport, RawCapture, SourceRequest
from .sealed_world import capture_request


FPL_API_BASE = "https://fantasy.premierleague.com/api"
SEALED_MANAGER_SCHEMA_NAME = "apex-sealed-manager-public-data"
SEALED_MANAGER_SCHEMA_VERSION = 1
EXPECTED_MANAGER_SOURCES = frozenset(
    {
        "official_fpl_entry_summary",
        "official_fpl_entry_history",
        "official_fpl_entry_transfers",
        "official_fpl_entry_picks",
    }
)


@dataclass(frozen=True, slots=True)
class ManagerPublicSource:
    source_name: str
    artifact_id: str
    content_sha256: str
    schema_name: str
    schema_version: str

    def __post_init__(self) -> None:
        if (
            not self.source_name.strip()
            or not self.schema_name.strip()
            or not self.schema_version.strip()
        ):
            raise ValueError("manager public source metadata cannot be empty")
        algorithm, separator, digest = self.artifact_id.partition(":")
        if algorithm != "sha256" or not separator or len(digest) != 64:
            raise ValueError(
                "manager public source artifact_id must be sha256 content identity"
            )
        try:
            int(digest, 16)
        except ValueError as exc:
            raise ValueError("manager public source artifact digest is invalid") from exc
        if self.content_sha256 != digest:
            raise ValueError("manager public source digest must match artifact_id")

    def as_dict(self) -> dict[str, str]:
        return {
            "source_name": self.source_name,
            "artifact_id": self.artifact_id,
            "content_sha256": self.content_sha256,
            "schema_name": self.schema_name,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ManagerPublicSource":
        return cls(
            source_name=str(payload["source_name"]),
            artifact_id=str(payload["artifact_id"]),
            content_sha256=str(payload["content_sha256"]),
            schema_name=str(payload["schema_name"]),
            schema_version=str(payload["schema_version"]),
        )


@dataclass(frozen=True, slots=True)
class ManagerPublicSnapshot:
    entry_id: int
    published_gameweek: int
    sources: tuple[ManagerPublicSource, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported ManagerPublicSnapshot schema_version")
        for label, value in (
            ("entry_id", self.entry_id),
            ("published_gameweek", self.published_gameweek),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{label} must be a positive integer")
        sources = tuple(sorted(self.sources, key=lambda row: row.source_name))
        names = [row.source_name for row in sources]
        if len(names) != 4 or len(set(names)) != 4:
            raise ValueError(
                "manager public snapshot requires exactly four unique sources"
            )
        if set(names) != EXPECTED_MANAGER_SOURCES:
            raise ValueError("manager public snapshot source coverage is incomplete")
        object.__setattr__(self, "sources", sources)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-manager-public-snapshot",
            "schema_version": self.schema_version,
            "entry_id": self.entry_id,
            "published_gameweek": self.published_gameweek,
            "sources": [row.as_dict() for row in self.sources],
        }

    @property
    def snapshot_id(self) -> ManagerPublicSnapshotId:
        return ManagerPublicSnapshotId(canonical_sha256(self.semantic_payload()))

    def as_dict(self) -> dict[str, object]:
        payload = self.semantic_payload()
        payload["manager_public_snapshot_id"] = str(self.snapshot_id)
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ManagerPublicSnapshot":
        if payload.get("schema_name") != "apex-manager-public-snapshot":
            raise ValueError("not an Apex manager public snapshot")
        rows = payload.get("sources")
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError("manager public snapshot sources must be object rows")
        snapshot = cls(
            entry_id=_exact_positive_int(payload.get("entry_id"), label="entry_id"),
            published_gameweek=_exact_positive_int(
                payload.get("published_gameweek"),
                label="published_gameweek",
            ),
            sources=tuple(ManagerPublicSource.from_dict(dict(row)) for row in rows),
            schema_version=_exact_positive_int(
                payload.get("schema_version"),
                label="schema_version",
            ),
        )
        declared = payload.get("manager_public_snapshot_id")
        if declared is not None and str(declared) != str(snapshot.snapshot_id):
            raise ValueError("manager public snapshot semantic identity mismatch")
        return snapshot


@dataclass(frozen=True, slots=True)
class SealedManagerPublicData:
    snapshot: ManagerPublicSnapshot
    manifest_artifact_id: str
    capture_manifest_artifact_ids: tuple[tuple[str, str], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "manager_public_snapshot_id": str(self.snapshot.snapshot_id),
            "manifest_artifact_id": self.manifest_artifact_id,
            "capture_manifest_artifact_ids": [
                [name, artifact_id]
                for name, artifact_id in self.capture_manifest_artifact_ids
            ],
        }


@dataclass(frozen=True, slots=True)
class ReplayedManagerPublicData:
    snapshot: ManagerPublicSnapshot
    summary: dict[str, Any]
    history: dict[str, Any]
    transfers: list[dict[str, Any]]
    picks: dict[str, Any]
    captures: tuple[RawCapture, ...]


def _exact_int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _exact_positive_int(value: object, *, label: str) -> int:
    return _exact_int(value, label=label, minimum=1)


def _decode_json(content: bytes, *, source_name: str) -> Any:
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{source_name} raw capture is not valid UTF-8 JSON") from exc


def _validate_manager_payloads(
    *,
    entry_id: int,
    published_gameweek: int,
    summary: object,
    history: object,
    transfers: object,
    picks: object,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if not isinstance(summary, dict):
        raise ValueError("Official FPL entry summary must be an object")
    if summary.get("id") is not None:
        summary_id = _exact_positive_int(summary["id"], label="entry summary id")
        if summary_id != entry_id:
            raise ValueError(
                "Official FPL entry summary ID does not match requested entry"
            )

    if not isinstance(history, dict):
        raise ValueError("Official FPL entry history must be an object")
    current = history.get("current")
    chips = history.get("chips")
    if not isinstance(current, list) or not isinstance(chips, list):
        raise ValueError(
            "Official FPL entry history requires current and chips arrays"
        )
    current_events: set[int] = set()
    history_by_event: dict[int, dict[str, Any]] = {}
    for row in current:
        if not isinstance(row, dict):
            raise ValueError(
                "Official FPL entry history current row must be an object"
            )
        event = _exact_positive_int(row.get("event"), label="entry history event")
        if event in current_events:
            raise ValueError("Official FPL entry history has duplicate Gameweek rows")
        current_events.add(event)
        history_by_event[event] = dict(row)
        for field in ("event_transfers", "event_transfers_cost", "bank"):
            if row.get(field) is not None:
                _exact_int(
                    row[field],
                    label=f"entry history {field}",
                )

    chip_events: set[int] = set()
    for row in chips:
        if not isinstance(row, dict):
            raise ValueError("Official FPL chip history row must be an object")
        event = _exact_positive_int(row.get("event"), label="chip history event")
        if event in chip_events:
            raise ValueError("Official FPL chip history has duplicate Gameweek rows")
        chip_events.add(event)
        if not str(row.get("name") or "").strip():
            raise ValueError("Official FPL chip history row requires a chip name")

    if not isinstance(transfers, list):
        raise ValueError("Official FPL transfer history must be an array")
    transfer_rows: list[dict[str, Any]] = []
    for row in transfers:
        if not isinstance(row, dict):
            raise ValueError("Official FPL transfer history row must be an object")
        item = dict(row)
        for field in (
            "element_in",
            "element_out",
            "element_in_cost",
            "element_out_cost",
            "event",
        ):
            _exact_positive_int(item.get(field), label=f"transfer {field}")
        if item["element_in"] == item["element_out"]:
            raise ValueError(
                "Official FPL transfer row cannot buy and sell the same player"
            )
        if item.get("entry") is not None:
            transfer_entry = _exact_positive_int(
                item["entry"],
                label="transfer entry",
            )
            if transfer_entry != entry_id:
                raise ValueError(
                    "Official FPL transfer row entry does not match requested entry"
                )
        if not str(item.get("time") or "").strip():
            raise ValueError("Official FPL transfer row requires time provenance")
        transfer_rows.append(item)

    if not isinstance(picks, dict):
        raise ValueError("Official FPL picks payload must be an object")
    pick_rows = picks.get("picks")
    entry_history = picks.get("entry_history")
    if not isinstance(pick_rows, list) or len(pick_rows) != 15:
        raise ValueError("Official FPL picks payload must contain exactly 15 picks")
    if not isinstance(entry_history, dict):
        raise ValueError("Official FPL picks payload requires entry_history")
    player_ids: list[int] = []
    positions: list[int] = []
    captain_ids: list[int] = []
    vice_ids: list[int] = []
    for row in pick_rows:
        if not isinstance(row, dict):
            raise ValueError("Official FPL pick row must be an object")
        player_id = _exact_positive_int(row.get("element"), label="pick element")
        position = _exact_positive_int(row.get("position"), label="pick position")
        player_ids.append(player_id)
        positions.append(position)
        if row.get("is_captain") is True:
            captain_ids.append(player_id)
        if row.get("is_vice_captain") is True:
            vice_ids.append(player_id)
    if len(set(player_ids)) != 15:
        raise ValueError("Official FPL picks contain duplicate player IDs")
    if set(positions) != set(range(1, 16)):
        raise ValueError("Official FPL picks positions must cover 1..15 exactly")
    if (
        len(captain_ids) != 1
        or len(vice_ids) != 1
        or captain_ids[0] == vice_ids[0]
    ):
        raise ValueError("Official FPL picks require distinct captain and vice-captain")
    for field in ("bank", "event_transfers", "event_transfers_cost"):
        if entry_history.get(field) is not None:
            _exact_int(
                entry_history[field],
                label=f"picks entry_history {field}",
            )
    if entry_history.get("event") is not None:
        event = _exact_positive_int(
            entry_history["event"],
            label="picks entry_history event",
        )
        if event != published_gameweek:
            raise ValueError("Official FPL picks entry_history Gameweek mismatch")

    target_history = history_by_event.get(published_gameweek)
    if target_history is not None:
        for field in ("event_transfers", "event_transfers_cost", "bank"):
            left = target_history.get(field)
            right = entry_history.get(field)
            if left is not None and right is not None and left != right:
                raise ValueError(
                    f"Official FPL target history {field} conflicts with picks entry_history"
                )

    return dict(summary), dict(history), transfer_rows, dict(picks)


def _requests(
    entry_id: int,
    published_gameweek: int,
    freshness_seconds: int,
) -> tuple[SourceRequest, ...]:
    base = f"{FPL_API_BASE}/entry/{entry_id}"
    return (
        SourceRequest.create(
            source_name="official_fpl_entry_summary",
            url=f"{base}/",
            freshness_seconds=freshness_seconds,
            schema_name="official-fpl-entry-summary",
            schema_version="1",
        ),
        SourceRequest.create(
            source_name="official_fpl_entry_history",
            url=f"{base}/history/",
            freshness_seconds=freshness_seconds,
            schema_name="official-fpl-entry-history",
            schema_version="1",
        ),
        SourceRequest.create(
            source_name="official_fpl_entry_transfers",
            url=f"{base}/transfers/",
            freshness_seconds=freshness_seconds,
            schema_name="official-fpl-entry-transfers",
            schema_version="1",
        ),
        SourceRequest.create(
            source_name="official_fpl_entry_picks",
            url=f"{base}/event/{published_gameweek}/picks/",
            freshness_seconds=freshness_seconds,
            schema_name="official-fpl-entry-picks",
            schema_version="1",
        ),
    )


def _snapshot_from_captures(
    *,
    entry_id: int,
    published_gameweek: int,
    captures: Iterable[RawCapture],
) -> ManagerPublicSnapshot:
    return ManagerPublicSnapshot(
        entry_id=entry_id,
        published_gameweek=published_gameweek,
        sources=tuple(
            ManagerPublicSource(
                source_name=row.source_name,
                artifact_id=row.body_artifact_id,
                content_sha256=row.body_sha256,
                schema_name=row.schema_name,
                schema_version=row.schema_version,
            )
            for row in captures
        ),
    )


def _payloads_from_bodies(
    bodies: dict[str, bytes],
    *,
    entry_id: int,
    published_gameweek: int,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    return _validate_manager_payloads(
        entry_id=entry_id,
        published_gameweek=published_gameweek,
        summary=_decode_json(
            bodies["official_fpl_entry_summary"],
            source_name="official_fpl_entry_summary",
        ),
        history=_decode_json(
            bodies["official_fpl_entry_history"],
            source_name="official_fpl_entry_history",
        ),
        transfers=_decode_json(
            bodies["official_fpl_entry_transfers"],
            source_name="official_fpl_entry_transfers",
        ),
        picks=_decode_json(
            bodies["official_fpl_entry_picks"],
            source_name="official_fpl_entry_picks",
        ),
    )


def acquire_official_manager_public_data(
    *,
    entry_id: int,
    published_gameweek: int,
    transport: HttpTransport,
    clock: Clock,
    store: ArtifactStore,
    freshness_seconds: int = 300,
) -> SealedManagerPublicData:
    """Capture and seal all Official FPL public surfaces used for manager state."""

    _exact_positive_int(entry_id, label="entry_id")
    _exact_positive_int(published_gameweek, label="published_gameweek")
    if (
        isinstance(freshness_seconds, bool)
        or not isinstance(freshness_seconds, int)
        or freshness_seconds < 0
    ):
        raise ValueError("freshness_seconds must be a nonnegative integer")

    stored = tuple(
        capture_request(
            request,
            transport=transport,
            clock=clock,
            store=store,
        )
        for request in _requests(entry_id, published_gameweek, freshness_seconds)
    )
    by_name = {row.capture.source_name: row for row in stored}
    if set(by_name) != EXPECTED_MANAGER_SOURCES or len(by_name) != len(stored):
        raise ValueError("manager acquisition did not produce exact required source set")
    bodies = {
        name: store.read_bytes(row.capture.body_artifact_id)
        for name, row in by_name.items()
    }
    _payloads_from_bodies(
        bodies,
        entry_id=entry_id,
        published_gameweek=published_gameweek,
    )

    snapshot = _snapshot_from_captures(
        entry_id=entry_id,
        published_gameweek=published_gameweek,
        captures=(row.capture for row in stored),
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
        "schema_name": SEALED_MANAGER_SCHEMA_NAME,
        "schema_version": SEALED_MANAGER_SCHEMA_VERSION,
        "manager_public_snapshot": snapshot.as_dict(),
        "capture_manifests": [
            {"source_name": name, "artifact_id": artifact_id}
            for name, artifact_id in capture_manifests
        ],
    }
    manifest_ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=SEALED_MANAGER_SCHEMA_NAME,
        schema_version=str(SEALED_MANAGER_SCHEMA_VERSION),
    )
    return SealedManagerPublicData(
        snapshot=snapshot,
        manifest_artifact_id=manifest_ref.artifact_id,
        capture_manifest_artifact_ids=capture_manifests,
    )


def load_official_manager_public_data(
    manifest_artifact_id: str,
    *,
    store: ArtifactStore,
) -> ReplayedManagerPublicData:
    """Replay a manager public snapshot strictly from ArtifactStore."""

    envelope = _decode_json(
        store.read_bytes(manifest_artifact_id),
        source_name="sealed_manager_public_manifest",
    )
    if not isinstance(envelope, dict):
        raise ValueError("sealed manager public manifest must be an object")
    if envelope.get("schema_name") != SEALED_MANAGER_SCHEMA_NAME:
        raise ValueError("not an Apex sealed manager public manifest")
    if envelope.get("schema_version") != SEALED_MANAGER_SCHEMA_VERSION:
        raise ValueError("unsupported sealed manager public schema_version")
    snapshot_payload = envelope.get("manager_public_snapshot")
    capture_rows = envelope.get("capture_manifests")
    if not isinstance(snapshot_payload, dict) or not isinstance(capture_rows, list):
        raise ValueError("sealed manager public manifest is incomplete")
    snapshot = ManagerPublicSnapshot.from_dict(dict(snapshot_payload))

    captures: list[RawCapture] = []
    bodies: dict[str, bytes] = {}
    capture_names: set[str] = set()
    for row in capture_rows:
        if not isinstance(row, dict):
            raise ValueError("manager capture manifest reference must be an object")
        source_name = str(row.get("source_name") or "")
        if not source_name or source_name in capture_names:
            raise ValueError("manager capture manifest source names must be unique")
        capture_names.add(source_name)
        capture_manifest_id = str(row.get("artifact_id") or "")
        raw = _decode_json(
            store.read_bytes(capture_manifest_id),
            source_name=f"capture_manifest:{source_name}",
        )
        if not isinstance(raw, dict):
            raise ValueError("manager raw capture manifest must be an object")
        capture = RawCapture.from_dict(dict(raw))
        if capture.source_name != source_name:
            raise ValueError("manager capture manifest source-name mismatch")
        body = store.read_bytes(capture.body_artifact_id)
        if len(body) != capture.body_size:
            raise ValueError(
                f"manager raw capture body size mismatch for {source_name}: "
                f"{len(body)} != {capture.body_size}"
            )
        bodies[source_name] = body
        captures.append(capture)

    if capture_names != EXPECTED_MANAGER_SOURCES:
        raise ValueError("sealed manager capture coverage is incomplete")
    replayed_snapshot = _snapshot_from_captures(
        entry_id=snapshot.entry_id,
        published_gameweek=snapshot.published_gameweek,
        captures=captures,
    )
    if replayed_snapshot.snapshot_id != snapshot.snapshot_id:
        raise ValueError(
            "replayed manager source bytes do not match sealed semantic snapshot"
        )

    summary, history, transfers, picks = _payloads_from_bodies(
        bodies,
        entry_id=snapshot.entry_id,
        published_gameweek=snapshot.published_gameweek,
    )
    return ReplayedManagerPublicData(
        snapshot=snapshot,
        summary=summary,
        history=history,
        transfers=transfers,
        picks=picks,
        captures=tuple(sorted(captures, key=lambda item: item.source_name)),
    )
