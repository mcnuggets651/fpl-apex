"""Immutable full-state override adapter for exact current manager state.

Apex V2 does not accept partial manual team-state patches. An override is stored
byte-for-byte in ArtifactStore, must be attributable/scoped/expiring, and must contain
a complete ManagerState that passes the active RuleSet before it can become
CURRENT_EXACT.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import RuleSetId
from apex_fpl.core.manager_state import (
    ChipUse,
    ManagerState,
    ManagerStateIntegrityError,
    ManagerStateScope,
    OwnedPlayer,
    TransferLedgerEvent,
)
from apex_fpl.core.rules import RuleSet


OVERRIDE_SCHEMA_NAME = "apex-manager-state-override"
OVERRIDE_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class StoredManagerStateOverride:
    state: ManagerState
    override_artifact_id: str
    author: str
    reason: str
    created_at: str
    expires_at: str


def _int(value: object, *, label: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ManagerStateIntegrityError(f"{label} must be an integer >= {minimum}")
    return value


def _aware(value: object, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManagerStateIntegrityError(f"override {label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ManagerStateIntegrityError(f"override {label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _object(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ManagerStateIntegrityError(f"{label} must be an object")
    return dict(value)


def _list(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ManagerStateIntegrityError(f"{label} must be an array")
    return list(value)


def _owned(row: object) -> OwnedPlayer:
    item = _object(row, label="squad row")
    required = {
        "player_id",
        "team_id",
        "position",
        "purchase_basis_tenths",
        "current_price_tenths",
        "selling_price_tenths",
    }
    missing = sorted(required - set(item))
    if missing:
        raise ManagerStateIntegrityError(f"squad row missing fields: {missing}")
    return OwnedPlayer(
        player_id=OfficialPlayerId(_int(item["player_id"], label="player_id", minimum=1)),
        team_id=_int(item["team_id"], label="team_id", minimum=1),
        position=str(item["position"]),
        purchase_basis_tenths=_int(
            item["purchase_basis_tenths"],
            label="purchase_basis_tenths",
            minimum=1,
        ),
        current_price_tenths=_int(
            item["current_price_tenths"],
            label="current_price_tenths",
            minimum=1,
        ),
        selling_price_tenths=_int(
            item["selling_price_tenths"],
            label="selling_price_tenths",
            minimum=1,
        ),
    )


def _chip(row: object) -> ChipUse:
    item = _object(row, label="chip row")
    return ChipUse(
        chip=str(item["chip"]),
        gameweek=_int(item["gameweek"], label="chip gameweek", minimum=1),
        set_number=_int(item["set_number"], label="chip set_number", minimum=1),
        source_artifact_id=str(item["source_artifact_id"]),
    )


def _transfer(row: object) -> TransferLedgerEvent:
    item = _object(row, label="transfer ledger row")
    return TransferLedgerEvent(
        event_id=str(item["event_id"]),
        sequence=_int(item["sequence"], label="transfer sequence", minimum=1),
        gameweek=_int(item["gameweek"], label="transfer gameweek", minimum=1),
        outgoing_player_id=OfficialPlayerId(
            _int(item["outgoing_player_id"], label="outgoing_player_id", minimum=1)
        ),
        incoming_player_id=OfficialPlayerId(
            _int(item["incoming_player_id"], label="incoming_player_id", minimum=1)
        ),
        outgoing_purchase_basis_tenths=_int(
            item["outgoing_purchase_basis_tenths"],
            label="outgoing_purchase_basis_tenths",
            minimum=1,
        ),
        outgoing_current_price_tenths=_int(
            item["outgoing_current_price_tenths"],
            label="outgoing_current_price_tenths",
            minimum=1,
        ),
        realised_sale_tenths=_int(
            item["realised_sale_tenths"],
            label="realised_sale_tenths",
            minimum=1,
        ),
        incoming_purchase_tenths=_int(
            item["incoming_purchase_tenths"],
            label="incoming_purchase_tenths",
            minimum=1,
        ),
        bank_before_tenths=_int(
            item["bank_before_tenths"],
            label="bank_before_tenths",
        ),
        bank_after_tenths=_int(
            item["bank_after_tenths"],
            label="bank_after_tenths",
        ),
        free_transfers_before=_int(
            item["free_transfers_before"],
            label="free_transfers_before",
        ),
        free_transfers_after=_int(
            item["free_transfers_after"],
            label="free_transfers_after",
        ),
        hit_points=_int(item["hit_points"], label="hit_points"),
        mode=str(item["mode"]),
        source_artifact_id=str(item["source_artifact_id"]),
    )


def store_and_load_manager_state_override(
    content: bytes,
    *,
    store: ArtifactStore,
    ruleset: RuleSet,
    observed_at: datetime,
) -> StoredManagerStateOverride:
    """Store immutable bytes, parse a complete override and certify current exact state."""

    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ManagerStateIntegrityError("observed_at must be timezone-aware")
    ref = store.put_bytes(
        content,
        media_type="application/json",
        schema_name=OVERRIDE_SCHEMA_NAME,
        schema_version=str(OVERRIDE_SCHEMA_VERSION),
    )
    try:
        payload = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManagerStateIntegrityError("manager-state override must be UTF-8 JSON") from exc
    root = _object(payload, label="manager-state override")
    if root.get("schema_name") != OVERRIDE_SCHEMA_NAME:
        raise ManagerStateIntegrityError("manager-state override schema_name mismatch")
    if _int(root.get("schema_version"), label="schema_version", minimum=1) != OVERRIDE_SCHEMA_VERSION:
        raise ManagerStateIntegrityError("unsupported manager-state override schema_version")

    meta = _object(root.get("metadata"), label="override metadata")
    author = str(meta.get("author") or "").strip()
    reason = str(meta.get("reason") or "").strip()
    if not author or not reason:
        raise ManagerStateIntegrityError("override metadata requires author and reason")
    created = _aware(meta.get("created_at"), label="created_at")
    expires = _aware(meta.get("expires_at"), label="expires_at")
    observed = observed_at.astimezone(timezone.utc)
    if not (created <= observed <= expires):
        raise ManagerStateIntegrityError("manager-state override is outside its validity window")

    state_payload = _object(root.get("state"), label="override state")
    required_state = {
        "season",
        "entry_id",
        "gameweek",
        "ruleset_id",
        "bank_tenths",
        "free_transfers",
        "squad",
        "chips_used",
        "transfer_ledger",
        "source_artifact_ids",
    }
    missing = sorted(required_state - set(state_payload))
    if missing:
        raise ManagerStateIntegrityError(f"override state missing fields: {missing}")
    if str(state_payload["ruleset_id"]) != str(ruleset.ruleset_id):
        raise ManagerStateIntegrityError("override RuleSetId does not match active RuleSet")

    source_ids = tuple(str(item).strip() for item in _list(
        state_payload["source_artifact_ids"],
        label="source_artifact_ids",
    ))
    if not source_ids or any(not item for item in source_ids):
        raise ManagerStateIntegrityError("override requires underlying source artifact IDs")

    state = ManagerState(
        season=str(state_payload["season"]),
        entry_id=_int(state_payload["entry_id"], label="entry_id", minimum=1),
        gameweek=_int(state_payload["gameweek"], label="gameweek", minimum=1),
        ruleset_id=RuleSetId(str(state_payload["ruleset_id"])),
        scope=ManagerStateScope.CURRENT_EXACT,
        bank_tenths=_int(state_payload["bank_tenths"], label="bank_tenths"),
        free_transfers=_int(state_payload["free_transfers"], label="free_transfers"),
        squad=tuple(_owned(row) for row in _list(state_payload["squad"], label="squad")),
        chips_used=tuple(
            _chip(row) for row in _list(state_payload["chips_used"], label="chips_used")
        ),
        transfer_ledger=tuple(
            _transfer(row)
            for row in _list(state_payload["transfer_ledger"], label="transfer_ledger")
        ),
        provenance_artifact_ids=source_ids + (ref.artifact_id,),
    )
    state.require_decision_safe(ruleset=ruleset)
    return StoredManagerStateOverride(
        state=state,
        override_artifact_id=ref.artifact_id,
        author=author,
        reason=reason,
        created_at=created.isoformat(),
        expires_at=expires.isoformat(),
    )
