"""Immutable self-addressing storage for exact V2 ManagerState truth."""

from __future__ import annotations

import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import ManagerStateId, RuleSetId
from apex_fpl.core.manager_state import (
    ChipUse,
    ManagerState,
    ManagerStateScope,
    OwnedPlayer,
    TransferLedgerEvent,
)


def _int(value: object, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be exact integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string")
    return value.strip()


def _rows(value: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def _strings(value: object, *, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(row, str) for row in value):
        raise ValueError(f"{label} must be an array of strings")
    return tuple(value)


def _owned(raw: dict[str, object]) -> OwnedPlayer:
    return OwnedPlayer(
        player_id=OfficialPlayerId(_int(raw.get("player_id"), label="owned player_id", minimum=1)),
        team_id=_int(raw.get("team_id"), label="owned team_id", minimum=1),
        position=_text(raw.get("position"), label="owned position"),
        purchase_basis_tenths=_int(
            raw.get("purchase_basis_tenths"), label="owned purchase basis", minimum=1
        ),
        current_price_tenths=_int(
            raw.get("current_price_tenths"), label="owned current price", minimum=1
        ),
        selling_price_tenths=_int(
            raw.get("selling_price_tenths"), label="owned selling price", minimum=1
        ),
    )


def _chip(raw: dict[str, object]) -> ChipUse:
    return ChipUse(
        chip=_text(raw.get("chip"), label="chip name"),
        gameweek=_int(raw.get("gameweek"), label="chip gameweek", minimum=1),
        set_number=_int(raw.get("set_number"), label="chip set", minimum=1),
        source_artifact_id=_text(raw.get("source_artifact_id"), label="chip source artifact"),
    )


def _transfer(raw: dict[str, object]) -> TransferLedgerEvent:
    return TransferLedgerEvent(
        event_id=_text(raw.get("event_id"), label="transfer event_id"),
        sequence=_int(raw.get("sequence"), label="transfer sequence", minimum=1),
        gameweek=_int(raw.get("gameweek"), label="transfer gameweek", minimum=1),
        outgoing_player_id=OfficialPlayerId(
            _int(raw.get("outgoing_player_id"), label="transfer outgoing player", minimum=1)
        ),
        incoming_player_id=OfficialPlayerId(
            _int(raw.get("incoming_player_id"), label="transfer incoming player", minimum=1)
        ),
        outgoing_purchase_basis_tenths=_int(
            raw.get("outgoing_purchase_basis_tenths"),
            label="transfer outgoing purchase basis",
            minimum=1,
        ),
        outgoing_current_price_tenths=_int(
            raw.get("outgoing_current_price_tenths"),
            label="transfer outgoing current price",
            minimum=1,
        ),
        realised_sale_tenths=_int(
            raw.get("realised_sale_tenths"), label="transfer realised sale", minimum=1
        ),
        incoming_purchase_tenths=_int(
            raw.get("incoming_purchase_tenths"), label="transfer incoming purchase", minimum=1
        ),
        bank_before_tenths=_int(
            raw.get("bank_before_tenths"), label="transfer bank before", minimum=0
        ),
        bank_after_tenths=_int(
            raw.get("bank_after_tenths"), label="transfer bank after", minimum=0
        ),
        free_transfers_before=_int(
            raw.get("free_transfers_before"), label="transfer FT before", minimum=0
        ),
        free_transfers_after=_int(
            raw.get("free_transfers_after"), label="transfer FT after", minimum=0
        ),
        hit_points=_int(raw.get("hit_points"), label="transfer hit points", minimum=0),
        mode=_text(raw.get("mode"), label="transfer mode"),
        source_artifact_id=_text(
            raw.get("source_artifact_id"), label="transfer source artifact"
        ),
    )


def store_manager_state(state: ManagerState, *, store: ArtifactStore) -> str:
    """Store semantic ManagerState bytes at exactly its ManagerStateId."""

    for artifact_id in state.provenance_artifact_ids:
        if not store.verify(artifact_id):
            raise ValueError("ManagerState provenance artifact is missing/corrupt")
    for row in state.chips_used:
        if not store.verify(row.source_artifact_id):
            raise ValueError("ManagerState chip source artifact is missing/corrupt")
    for row in state.transfer_ledger:
        if not store.verify(row.source_artifact_id):
            raise ValueError("ManagerState transfer source artifact is missing/corrupt")
    ref = store.put_bytes(
        canonical_json_bytes(state.semantic_payload()),
        media_type="application/json",
        schema_name="apex-manager-state",
        schema_version=str(state.schema_version),
    )
    if ref.artifact_id != str(state.manager_state_id):
        raise ValueError("ManagerState storage identity mismatch")
    return ref.artifact_id


def load_manager_state(
    manager_state_id: ManagerStateId | str,
    *,
    store: ArtifactStore,
) -> ManagerState:
    """Replay exact ManagerState semantic bytes and all retained source dependencies."""

    expected = ManagerStateId(str(manager_state_id))
    try:
        content = store.read_bytes(str(expected))
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError("ManagerState artifact failed integrity verification") from exc
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("ManagerState artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("ManagerState artifact must be JSON object")
    if raw.get("schema_name") != "apex-manager-state":
        raise ValueError("not an Apex ManagerState artifact")
    if canonical_json_bytes(raw) != content:
        raise ValueError("ManagerState artifact is not canonical JSON")
    state = ManagerState(
        season=_text(raw.get("season"), label="ManagerState season"),
        entry_id=_int(raw.get("entry_id"), label="ManagerState entry_id", minimum=1),
        gameweek=_int(raw.get("gameweek"), label="ManagerState gameweek", minimum=1),
        ruleset_id=RuleSetId(_text(raw.get("ruleset_id"), label="ManagerState ruleset_id")),
        scope=ManagerStateScope(_text(raw.get("scope"), label="ManagerState scope")),
        bank_tenths=_int(raw.get("bank_tenths"), label="ManagerState bank", minimum=0),
        free_transfers=_int(
            raw.get("free_transfers"), label="ManagerState free_transfers", minimum=0
        ),
        squad=tuple(_owned(row) for row in _rows(raw.get("squad"), label="ManagerState squad")),
        chips_used=tuple(
            _chip(row) for row in _rows(raw.get("chips_used"), label="ManagerState chips_used")
        ),
        transfer_ledger=tuple(
            _transfer(row)
            for row in _rows(raw.get("transfer_ledger"), label="ManagerState transfer_ledger")
        ),
        provenance_artifact_ids=_strings(
            raw.get("provenance_artifact_ids"), label="ManagerState provenance_artifact_ids"
        ),
        schema_version=_int(
            raw.get("schema_version"), label="ManagerState schema_version", minimum=1
        ),
    )
    if state.manager_state_id != expected:
        raise ValueError("ManagerState semantic identity mismatch")
    for artifact_id in state.provenance_artifact_ids:
        if not store.verify(artifact_id):
            raise ValueError("ManagerState provenance artifact is missing/corrupt")
    for row in state.chips_used:
        if not store.verify(row.source_artifact_id):
            raise ValueError("ManagerState chip source artifact is missing/corrupt")
    for row in state.transfer_ledger:
        if not store.verify(row.source_artifact_id):
            raise ValueError("ManagerState transfer source artifact is missing/corrupt")
    return state
