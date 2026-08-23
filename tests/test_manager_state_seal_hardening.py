from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from apex_fpl.acquisition.contracts import HttpResponse, RawCapture, SourceRequest
from apex_fpl.acquisition.sealed_manager import (
    SEALED_MANAGER_SCHEMA_NAME,
    SEALED_MANAGER_SCHEMA_VERSION,
    ManagerPublicSnapshot,
    ManagerPublicSource,
    ReplayedManagerPublicData,
    load_official_manager_public_data,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.initial_manager_basis import (
    INITIAL_BASIS_SCHEMA_NAME,
    INITIAL_BASIS_SCHEMA_VERSION,
    InitialManagerBasis,
    InitialPurchaseBasis,
    load_initial_manager_basis,
)
from apex_fpl.control.manager_state_from_seals import _chips, _event_history
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import GlobalWorldId, ManagerPublicSnapshotId


ROOT = Path(__file__).resolve().parents[1]
RULESET = load_ruleset(ROOT / "config/rules/2026-2027.yaml")


def _artifact(char: str) -> str:
    return "sha256:" + char * 64


def _snapshot() -> ManagerPublicSnapshot:
    names = (
        "official_fpl_entry_summary",
        "official_fpl_entry_history",
        "official_fpl_entry_transfers",
        "official_fpl_entry_picks",
    )
    sources = tuple(
        ManagerPublicSource(
            source_name=name,
            artifact_id=_artifact(str(index)),
            content_sha256=str(index) * 64,
            schema_name=name,
            schema_version="1",
        )
        for index, name in enumerate(names, start=1)
    )
    return ManagerPublicSnapshot(entry_id=63984, published_gameweek=2, sources=sources)


def _replayed(
    *,
    history: dict[str, object],
    picks: dict[str, object],
) -> ReplayedManagerPublicData:
    return ReplayedManagerPublicData(
        snapshot=_snapshot(),
        summary={"id": 63984},
        history=history,
        transfers=[],
        picks=picks,
        captures=(),
    )


def test_duplicate_sealed_chip_history_fails_closed_instead_of_last_row_wins():
    data = _replayed(
        history={
            "current": [
                {"event": 1, "event_transfers": 0, "event_transfers_cost": 0},
                {"event": 2, "event_transfers": 0, "event_transfers_cost": 0},
            ],
            "chips": [
                {"event": 1, "name": "3xc"},
                {"event": 1, "name": "bboost"},
            ],
        },
        picks={
            "entry_history": {
                "event": 2,
                "event_transfers": 0,
                "event_transfers_cost": 0,
            },
            "active_chip": None,
        },
    )
    with pytest.raises(ValueError, match="duplicate GW1"):
        _chips(data)


def test_target_history_row_must_reconcile_with_target_picks_entry_history():
    data = _replayed(
        history={
            "current": [
                {"event": 1, "event_transfers": 0, "event_transfers_cost": 0},
                {"event": 2, "event_transfers": 1, "event_transfers_cost": 0},
            ],
            "chips": [],
        },
        picks={
            "entry_history": {
                "event": 2,
                "event_transfers": 2,
                "event_transfers_cost": 4,
            },
            "active_chip": None,
        },
    )
    with pytest.raises(ValueError, match="history conflicts"):
        _event_history(data)


def test_initial_basis_cannot_launder_unrelated_but_valid_artifact_hashes(
    tmp_path: Path,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    unrelated_a = store.put_bytes(b'{"schema_name":"unrelated-a"}')
    unrelated_b = store.put_bytes(b'{"schema_name":"unrelated-b"}')
    players = tuple(
        InitialPurchaseBasis(
            player_id=OfficialPlayerId(index),
            team_id=index,
            position=(
                "GK"
                if index <= 2
                else "DEF"
                if index <= 7
                else "MID"
                if index <= 12
                else "FWD"
            ),
            purchase_basis_tenths=40,
        )
        for index in range(1, 16)
    )
    basis = InitialManagerBasis(
        season="2026-2027",
        entry_id=63984,
        ruleset_id=RULESET.ruleset_id,
        pre_gw1_global_world_id=GlobalWorldId("claimed-world"),
        gw1_manager_public_snapshot_id=ManagerPublicSnapshotId("claimed-manager"),
        initial_bank_tenths=400,
        players=players,
        provenance_artifact_ids=(unrelated_a.artifact_id, unrelated_b.artifact_id),
    )
    ref = store.put_bytes(
        canonical_json_bytes(basis.as_dict()),
        media_type="application/json",
        schema_name=INITIAL_BASIS_SCHEMA_NAME,
        schema_version=str(INITIAL_BASIS_SCHEMA_VERSION),
    )
    with pytest.raises(
        ValueError,
        match="unexpected initial manager basis provenance schema",
    ):
        load_initial_manager_basis(ref.artifact_id, store=store)


def _manager_bodies() -> dict[str, bytes]:
    picks = {
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
            "event": 1,
            "bank": 0,
            "event_transfers": 0,
            "event_transfers_cost": 0,
        },
        "active_chip": None,
    }
    payloads: dict[str, object] = {
        "official_fpl_entry_summary": {"id": 63984, "name": "Apex"},
        "official_fpl_entry_history": {
            "current": [
                {
                    "event": 1,
                    "bank": 0,
                    "event_transfers": 0,
                    "event_transfers_cost": 0,
                }
            ],
            "chips": [],
        },
        "official_fpl_entry_transfers": [],
        "official_fpl_entry_picks": picks,
    }
    return {
        name: json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        for name, value in payloads.items()
    }


def test_sealed_manager_replay_rejects_self_consistent_manifest_with_wrong_body_size(
    tmp_path: Path,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    bodies = _manager_bodies()
    captures: list[RawCapture] = []
    capture_manifest_refs: list[tuple[str, str]] = []
    stamp = datetime(2026, 8, 23, 20, tzinfo=timezone.utc)
    for index, (source_name, body) in enumerate(sorted(bodies.items())):
        body_ref = store.put_bytes(body)
        request = SourceRequest.create(
            source_name=source_name,
            url=f"https://fantasy.premierleague.com/api/test/{source_name}",
            schema_name=source_name,
            schema_version="1",
        )
        response = HttpResponse(
            status_code=200,
            body=body,
            headers={"Content-Type": "application/json"},
        )
        declared_size = len(body) + 1 if index == 0 else len(body)
        capture = RawCapture.create(
            request=request,
            retrieved_at=stamp,
            response=response,
            body_artifact_id=body_ref.artifact_id,
            body_sha256=body_ref.digest,
            body_size=declared_size,
        )
        manifest_ref = store.put_bytes(
            canonical_json_bytes(capture.as_dict()),
            media_type="application/json",
            schema_name="apex-raw-capture",
            schema_version="1",
        )
        captures.append(capture)
        capture_manifest_refs.append((source_name, manifest_ref.artifact_id))

    snapshot = ManagerPublicSnapshot(
        entry_id=63984,
        published_gameweek=1,
        sources=tuple(
            ManagerPublicSource(
                source_name=capture.source_name,
                artifact_id=capture.body_artifact_id,
                content_sha256=capture.body_sha256,
                schema_name=capture.schema_name,
                schema_version=capture.schema_version,
            )
            for capture in captures
        ),
    )
    envelope = {
        "schema_name": SEALED_MANAGER_SCHEMA_NAME,
        "schema_version": SEALED_MANAGER_SCHEMA_VERSION,
        "manager_public_snapshot": snapshot.as_dict(),
        "capture_manifests": [
            {"source_name": name, "artifact_id": artifact_id}
            for name, artifact_id in capture_manifest_refs
        ],
    }
    sealed_ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name=SEALED_MANAGER_SCHEMA_NAME,
        schema_version=str(SEALED_MANAGER_SCHEMA_VERSION),
    )
    with pytest.raises(ValueError, match="body size mismatch"):
        load_official_manager_public_data(sealed_ref.artifact_id, store=store)
