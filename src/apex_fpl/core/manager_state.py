"""Exact manager state and FPL financial transitions for Apex V2.

All money is integer tenths of a million pounds. This module is dependency-free and
contains no network or wall-clock reads. A structurally complete manager state can be
an exact current state or an exact historical/deadline snapshot; only CURRENT_EXACT is
decision-safe for a live in-season action.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable, Mapping

from .canonical import canonical_sha256
from .identity import OfficialPlayerId, OfficialPlayerIdentity
from .ids import ManagerStateId, RuleSetId
from .rules import RuleSet


class ManagerStateIntegrityError(ValueError):
    """Raised when manager state cannot support exact FPL legality."""


class ManagerStateScope(str, Enum):
    CURRENT_EXACT = "CURRENT_EXACT"
    DEADLINE_SNAPSHOT = "DEADLINE_SNAPSHOT"
    REPLAY_EXACT = "REPLAY_EXACT"


@dataclass(frozen=True, slots=True)
class OwnedPlayer:
    player_id: OfficialPlayerId
    team_id: int
    position: str
    purchase_basis_tenths: int
    current_price_tenths: int
    selling_price_tenths: int

    def __post_init__(self) -> None:
        if isinstance(self.team_id, bool) or not isinstance(self.team_id, int) or self.team_id <= 0:
            raise ManagerStateIntegrityError("owned player team_id must be a positive integer")
        if self.position not in {"GK", "DEF", "MID", "FWD"}:
            raise ManagerStateIntegrityError(f"invalid owned-player position: {self.position!r}")
        for name in (
            "purchase_basis_tenths",
            "current_price_tenths",
            "selling_price_tenths",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ManagerStateIntegrityError(f"{name} must be a positive integer")

    def as_dict(self) -> dict[str, object]:
        return {
            "player_id": int(self.player_id),
            "team_id": self.team_id,
            "position": self.position,
            "purchase_basis_tenths": self.purchase_basis_tenths,
            "current_price_tenths": self.current_price_tenths,
            "selling_price_tenths": self.selling_price_tenths,
        }


@dataclass(frozen=True, slots=True)
class ChipUse:
    chip: str
    gameweek: int
    set_number: int
    source_artifact_id: str

    def __post_init__(self) -> None:
        if self.chip not in {"WILDCARD", "FREE_HIT", "TRIPLE_CAPTAIN", "BENCH_BOOST"}:
            raise ManagerStateIntegrityError(f"unknown chip: {self.chip!r}")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ManagerStateIntegrityError("chip gameweek must be a positive integer")
        if self.set_number not in {1, 2}:
            raise ManagerStateIntegrityError("chip set_number must be 1 or 2")
        if not self.source_artifact_id.strip():
            raise ManagerStateIntegrityError("chip use requires source artifact provenance")

    def as_dict(self) -> dict[str, object]:
        return {
            "chip": self.chip,
            "gameweek": self.gameweek,
            "set_number": self.set_number,
            "source_artifact_id": self.source_artifact_id,
        }


@dataclass(frozen=True, slots=True)
class TransferLedgerEvent:
    event_id: str
    sequence: int
    gameweek: int
    outgoing_player_id: OfficialPlayerId
    incoming_player_id: OfficialPlayerId
    outgoing_purchase_basis_tenths: int
    outgoing_current_price_tenths: int
    realised_sale_tenths: int
    incoming_purchase_tenths: int
    bank_before_tenths: int
    bank_after_tenths: int
    free_transfers_before: int
    free_transfers_after: int
    hit_points: int
    mode: str
    source_artifact_id: str

    def __post_init__(self) -> None:
        if not self.event_id.strip() or not self.source_artifact_id.strip():
            raise ManagerStateIntegrityError("transfer event requires ID and source provenance")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence <= 0:
            raise ManagerStateIntegrityError("transfer sequence must be a positive integer")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ManagerStateIntegrityError("transfer gameweek must be a positive integer")
        if self.outgoing_player_id == self.incoming_player_id:
            raise ManagerStateIntegrityError("transfer must replace a player with a different player")
        for name in (
            "outgoing_purchase_basis_tenths",
            "outgoing_current_price_tenths",
            "realised_sale_tenths",
            "incoming_purchase_tenths",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ManagerStateIntegrityError(f"{name} must be a positive integer")
        for name in ("bank_before_tenths", "bank_after_tenths", "free_transfers_before", "free_transfers_after", "hit_points"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ManagerStateIntegrityError(f"{name} must be a nonnegative integer")
        if self.mode not in {"NORMAL", "WILDCARD"}:
            raise ManagerStateIntegrityError(f"unsupported permanent-transfer mode: {self.mode}")

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "sequence": self.sequence,
            "gameweek": self.gameweek,
            "outgoing_player_id": int(self.outgoing_player_id),
            "incoming_player_id": int(self.incoming_player_id),
            "outgoing_purchase_basis_tenths": self.outgoing_purchase_basis_tenths,
            "outgoing_current_price_tenths": self.outgoing_current_price_tenths,
            "realised_sale_tenths": self.realised_sale_tenths,
            "incoming_purchase_tenths": self.incoming_purchase_tenths,
            "bank_before_tenths": self.bank_before_tenths,
            "bank_after_tenths": self.bank_after_tenths,
            "free_transfers_before": self.free_transfers_before,
            "free_transfers_after": self.free_transfers_after,
            "hit_points": self.hit_points,
            "mode": self.mode,
            "source_artifact_id": self.source_artifact_id,
        }


@dataclass(frozen=True, slots=True)
class CurrentStateAttestation:
    author: str
    created_at: str
    expires_at: str
    gameweek: int
    confirms_no_unrecorded_transfers: bool
    source_artifact_id: str

    def __post_init__(self) -> None:
        if not self.author.strip() or not self.source_artifact_id.strip():
            raise ManagerStateIntegrityError("current-state attestation requires author/provenance")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ManagerStateIntegrityError("attestation gameweek must be a positive integer")
        _parse_aware_time(self.created_at, label="created_at")
        _parse_aware_time(self.expires_at, label="expires_at")
        if not self.confirms_no_unrecorded_transfers:
            raise ManagerStateIntegrityError(
                "attestation must explicitly confirm no unrecorded transfers"
            )

    @property
    def attestation_id(self) -> str:
        return canonical_sha256(self.as_dict())

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_name": "apex-current-manager-state-attestation",
            "schema_version": 1,
            "author": self.author,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "gameweek": self.gameweek,
            "confirms_no_unrecorded_transfers": self.confirms_no_unrecorded_transfers,
            "source_artifact_id": self.source_artifact_id,
        }

    def valid_at(self, observed_at: str) -> bool:
        observed = _parse_aware_time(observed_at, label="observed_at")
        created = _parse_aware_time(self.created_at, label="created_at")
        expires = _parse_aware_time(self.expires_at, label="expires_at")
        return created <= observed <= expires


def _parse_aware_time(value: str, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ManagerStateIntegrityError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ManagerStateIntegrityError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    if not text:
        raise ManagerStateIntegrityError("provenance artifact ID cannot be empty")
    return text


def calculate_selling_price_tenths(
    purchase_basis_tenths: int,
    current_price_tenths: int,
    *,
    ruleset: RuleSet,
) -> int:
    """Return exact realised FPL selling value in integer tenths.

    Price falls pass through in full. On a rise, every governed purchase-price rise
    step realises the governed profit step; for 2026/27 that is £0.1 per £0.2 rise.
    """

    for name, value in (
        ("purchase_basis_tenths", purchase_basis_tenths),
        ("current_price_tenths", current_price_tenths),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ManagerStateIntegrityError(f"{name} must be a positive integer")
    if current_price_tenths <= purchase_basis_tenths:
        if ruleset.value("FPL-SELLING-PRICE-LOSS-PASSTHROUGH-001") is not True:
            raise ManagerStateIntegrityError("RuleSet does not define loss passthrough")
        return current_price_tenths
    step = ruleset.mapping("FPL-SELLING-PRICE-PROFIT-STEP-001")
    rise = int(step["purchase_price_rise_tenths"])
    profit = int(step["selling_profit_tenths"])
    if rise <= 0 or profit <= 0:
        raise ManagerStateIntegrityError("invalid RuleSet selling-price step")
    return purchase_basis_tenths + ((current_price_tenths - purchase_basis_tenths) // rise) * profit


def owned_player_from_official(
    player: OfficialPlayerIdentity,
    *,
    purchase_basis_tenths: int,
    current_price_tenths: int | None,
    ruleset: RuleSet,
) -> OwnedPlayer:
    current = player.price_tenths if current_price_tenths is None else current_price_tenths
    selling = calculate_selling_price_tenths(
        purchase_basis_tenths,
        current,
        ruleset=ruleset,
    )
    return OwnedPlayer(
        player_id=player.player_id,
        team_id=player.team_id,
        position=player.position,
        purchase_basis_tenths=purchase_basis_tenths,
        current_price_tenths=current,
        selling_price_tenths=selling,
    )


@dataclass(frozen=True, slots=True)
class ManagerState:
    season: str
    entry_id: int
    gameweek: int
    ruleset_id: RuleSetId
    scope: ManagerStateScope
    bank_tenths: int
    free_transfers: int
    squad: tuple[OwnedPlayer, ...]
    chips_used: tuple[ChipUse, ...] = ()
    transfer_ledger: tuple[TransferLedgerEvent, ...] = ()
    provenance_artifact_ids: tuple[str, ...] = ()
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ManagerStateIntegrityError("unsupported ManagerState schema_version")
        if not self.season.strip():
            raise ManagerStateIntegrityError("manager state season cannot be empty")
        if isinstance(self.entry_id, bool) or not isinstance(self.entry_id, int) or self.entry_id <= 0:
            raise ManagerStateIntegrityError("entry_id must be a positive integer")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
            raise ManagerStateIntegrityError("gameweek must be a positive integer")
        if isinstance(self.bank_tenths, bool) or not isinstance(self.bank_tenths, int) or self.bank_tenths < 0:
            raise ManagerStateIntegrityError("bank_tenths must be a nonnegative integer")
        if isinstance(self.free_transfers, bool) or not isinstance(self.free_transfers, int) or self.free_transfers < 0:
            raise ManagerStateIntegrityError("free_transfers must be a nonnegative integer")
        squad = tuple(sorted(self.squad, key=lambda row: int(row.player_id)))
        if len(squad) != 15 or len({row.player_id for row in squad}) != 15:
            raise ManagerStateIntegrityError("manager state requires exactly 15 unique players")
        ledger = tuple(self.transfer_ledger)
        sequences = [event.sequence for event in ledger]
        event_ids = [event.event_id for event in ledger]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ManagerStateIntegrityError("transfer ledger sequence must be unique and increasing")
        if len(event_ids) != len(set(event_ids)):
            raise ManagerStateIntegrityError("transfer ledger event IDs must be unique")
        if any(event.gameweek > self.gameweek for event in ledger):
            raise ManagerStateIntegrityError("transfer ledger cannot contain a future Gameweek")
        if any(
            ledger[index].gameweek > ledger[index + 1].gameweek
            for index in range(len(ledger) - 1)
        ):
            raise ManagerStateIntegrityError("transfer ledger must be chronological")
        provenance = tuple(sorted({_artifact_id(item) for item in self.provenance_artifact_ids}))
        if not provenance:
            raise ManagerStateIntegrityError("manager state requires immutable provenance")
        object.__setattr__(self, "squad", squad)
        object.__setattr__(self, "chips_used", tuple(sorted(self.chips_used, key=lambda row: (row.gameweek, row.chip))))
        object.__setattr__(self, "transfer_ledger", ledger)
        object.__setattr__(self, "provenance_artifact_ids", provenance)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-manager-state",
            "schema_version": self.schema_version,
            "season": self.season,
            "entry_id": self.entry_id,
            "gameweek": self.gameweek,
            "ruleset_id": str(self.ruleset_id),
            "scope": self.scope.value,
            "bank_tenths": self.bank_tenths,
            "free_transfers": self.free_transfers,
            "squad": [row.as_dict() for row in self.squad],
            "chips_used": [row.as_dict() for row in self.chips_used],
            "transfer_ledger": [row.as_dict() for row in self.transfer_ledger],
            "provenance_artifact_ids": list(self.provenance_artifact_ids),
        }

    @property
    def manager_state_id(self) -> ManagerStateId:
        return ManagerStateId(canonical_sha256(self.semantic_payload()))

    @property
    def player_ids(self) -> tuple[OfficialPlayerId, ...]:
        return tuple(row.player_id for row in self.squad)

    def player(self, player_id: OfficialPlayerId) -> OwnedPlayer:
        for row in self.squad:
            if row.player_id == player_id:
                return row
        raise ManagerStateIntegrityError(f"player {player_id} is not in the current permanent squad")

    def validation_errors(self, *, ruleset: RuleSet) -> tuple[str, ...]:
        errors: list[str] = []
        if self.ruleset_id != ruleset.ruleset_id:
            errors.append("manager state RuleSetId does not match active RuleSet")
        max_ft = ruleset.integer("FPL-FREE-TRANSFER-BANK-MAX-001")
        if self.free_transfers > max_ft:
            errors.append(f"free transfers {self.free_transfers} exceed RuleSet maximum {max_ft}")
        errors.extend(
            ruleset.validate_squad(
                positions=(row.position for row in self.squad),
                club_ids=(row.team_id for row in self.squad),
                prices_tenths=(row.current_price_tenths for row in self.squad),
            )
        )
        for row in self.squad:
            expected = calculate_selling_price_tenths(
                row.purchase_basis_tenths,
                row.current_price_tenths,
                ruleset=ruleset,
            )
            if row.selling_price_tenths != expected:
                errors.append(
                    f"player {row.player_id} selling price {row.selling_price_tenths} != exact {expected}"
                )
        errors.extend(_validate_chip_ledger(self.chips_used, ruleset=ruleset))
        return tuple(errors)

    @property
    def decision_safe_scope(self) -> bool:
        return self.scope is ManagerStateScope.CURRENT_EXACT

    def require_decision_safe(self, *, ruleset: RuleSet) -> "ManagerState":
        errors = list(self.validation_errors(ruleset=ruleset))
        if not self.decision_safe_scope:
            errors.append(
                f"manager state scope {self.scope.value} is not current exact state"
            )
        if errors:
            raise ManagerStateIntegrityError("; ".join(errors))
        return self


def _chip_set_for_gameweek(gameweek: int, *, ruleset: RuleSet) -> int:
    first_half_last = ruleset.integer("FPL-CHIP-FIRST-SET-LAST-GW-001")
    second_half_first = ruleset.integer("FPL-CHIP-SECOND-SET-FIRST-GW-001")
    if gameweek <= first_half_last:
        return 1
    if gameweek >= second_half_first:
        return 2
    raise ManagerStateIntegrityError(f"gameweek {gameweek} is outside configured chip halves")


def _validate_chip_ledger(chips: Iterable[ChipUse], *, ruleset: RuleSet) -> tuple[str, ...]:
    rows = tuple(chips)
    errors: list[str] = []
    seen_gw: set[int] = set()
    seen_chip_set: set[tuple[str, int]] = set()
    for row in rows:
        expected_set = _chip_set_for_gameweek(row.gameweek, ruleset=ruleset)
        if row.set_number != expected_set:
            errors.append(
                f"chip {row.chip} GW{row.gameweek} has set {row.set_number}; expected {expected_set}"
            )
        if row.gameweek in seen_gw:
            errors.append(f"multiple chips used in GW{row.gameweek}")
        seen_gw.add(row.gameweek)
        key = (row.chip, row.set_number)
        if key in seen_chip_set:
            errors.append(f"chip {row.chip} used twice in set {row.set_number}")
        seen_chip_set.add(key)
        disallowed_rule = {
            "FREE_HIT": "FPL-FREE-HIT-DISALLOWED-GWS-001",
            "WILDCARD": "FPL-WILDCARD-DISALLOWED-GWS-001",
        }.get(row.chip)
        if disallowed_rule is not None and row.gameweek in ruleset.value(disallowed_rule):
            errors.append(f"chip {row.chip} is disallowed in GW{row.gameweek}")
    free_hits = {row.gameweek for row in rows if row.chip == "FREE_HIT"}
    boundary = ruleset.mapping("FPL-FREE-HIT-CROSS-HALF-CONSECUTIVE-001")
    if boundary.get("allowed") is False:
        pair = {int(boundary["first_half_gw"]), int(boundary["second_half_gw"])}
        if pair.issubset(free_hits):
            errors.append("Free Hit cannot be used in both GW19 and GW20")
    return tuple(errors)


def reprice_manager_state(
    state: ManagerState,
    *,
    current_prices_tenths: Mapping[OfficialPlayerId, int],
    ruleset: RuleSet,
    source_artifact_id: str,
) -> ManagerState:
    """Mark all 15 owned players to one complete Official-FPL price surface."""

    state.require_decision_safe(ruleset=ruleset) if state.scope is ManagerStateScope.CURRENT_EXACT else None
    owned_ids = set(state.player_ids)
    supplied_ids = set(current_prices_tenths)
    missing = sorted(int(item) for item in owned_ids - supplied_ids)
    if missing:
        raise ManagerStateIntegrityError(f"current price surface is missing owned player IDs: {missing}")
    updated: list[OwnedPlayer] = []
    for row in state.squad:
        current = current_prices_tenths[row.player_id]
        if isinstance(current, bool) or not isinstance(current, int) or current <= 0:
            raise ManagerStateIntegrityError(
                f"current Official price for {row.player_id} must be positive integer tenths"
            )
        updated.append(
            replace(
                row,
                current_price_tenths=current,
                selling_price_tenths=calculate_selling_price_tenths(
                    row.purchase_basis_tenths,
                    current,
                    ruleset=ruleset,
                ),
            )
        )
    return replace(
        state,
        squad=tuple(updated),
        provenance_artifact_ids=state.provenance_artifact_ids + (_artifact_id(source_artifact_id),),
    )


@dataclass(frozen=True, slots=True)
class TransferTransition:
    state: ManagerState
    event: TransferLedgerEvent


def apply_permanent_transfer(
    state: ManagerState,
    *,
    outgoing_player_id: OfficialPlayerId,
    incoming_player: OfficialPlayerIdentity,
    ruleset: RuleSet,
    event_id: str,
    source_artifact_id: str,
    wildcard_active: bool = False,
) -> TransferTransition:
    """Apply one permanent transfer using exact bank, basis, selling value and FT state.

    Free Hit is intentionally not a permanent transfer mode. Wildcard transfers are
    permanent, cost no hit and preserve banked free transfers.
    """

    state.require_decision_safe(ruleset=ruleset)
    outgoing = state.player(outgoing_player_id)
    if incoming_player.player_id in set(state.player_ids):
        raise ManagerStateIntegrityError("incoming player is already owned")
    if ruleset.value("FPL-TRANSFER-SAME-POSITION-001") is True and incoming_player.position != outgoing.position:
        raise ManagerStateIntegrityError(
            f"transfer position mismatch: {outgoing.position} -> {incoming_player.position}"
        )
    realised_sale = calculate_selling_price_tenths(
        outgoing.purchase_basis_tenths,
        outgoing.current_price_tenths,
        ruleset=ruleset,
    )
    if realised_sale != outgoing.selling_price_tenths:
        raise ManagerStateIntegrityError("outgoing player's selling value is not exact")
    incoming_price = incoming_player.price_tenths
    bank_after = state.bank_tenths + realised_sale - incoming_price
    if bank_after < 0:
        raise ManagerStateIntegrityError("transfer would create negative bank")

    if wildcard_active:
        mode = "WILDCARD"
        free_after = state.free_transfers
        hit_points = 0
    else:
        mode = "NORMAL"
        free_after = max(0, state.free_transfers - 1)
        hit_points = (
            0
            if state.free_transfers > 0
            else ruleset.integer("FPL-EXTRA-TRANSFER-HIT-POINTS-001")
        )

    incoming_owned = owned_player_from_official(
        incoming_player,
        purchase_basis_tenths=incoming_price,
        current_price_tenths=incoming_price,
        ruleset=ruleset,
    )
    new_squad = tuple(
        incoming_owned if row.player_id == outgoing_player_id else row
        for row in state.squad
    )
    legality = ruleset.validate_squad(
        positions=(row.position for row in new_squad),
        club_ids=(row.team_id for row in new_squad),
        prices_tenths=(row.current_price_tenths for row in new_squad),
    )
    if legality:
        raise ManagerStateIntegrityError("illegal post-transfer squad: " + "; ".join(legality))

    sequence = state.transfer_ledger[-1].sequence + 1 if state.transfer_ledger else 1
    event = TransferLedgerEvent(
        event_id=event_id,
        sequence=sequence,
        gameweek=state.gameweek,
        outgoing_player_id=outgoing.player_id,
        incoming_player_id=incoming_player.player_id,
        outgoing_purchase_basis_tenths=outgoing.purchase_basis_tenths,
        outgoing_current_price_tenths=outgoing.current_price_tenths,
        realised_sale_tenths=realised_sale,
        incoming_purchase_tenths=incoming_price,
        bank_before_tenths=state.bank_tenths,
        bank_after_tenths=bank_after,
        free_transfers_before=state.free_transfers,
        free_transfers_after=free_after,
        hit_points=hit_points,
        mode=mode,
        source_artifact_id=_artifact_id(source_artifact_id),
    )
    next_state = replace(
        state,
        bank_tenths=bank_after,
        free_transfers=free_after,
        squad=new_squad,
        transfer_ledger=state.transfer_ledger + (event,),
        provenance_artifact_ids=state.provenance_artifact_ids + (event.source_artifact_id,),
    )
    next_state.require_decision_safe(ruleset=ruleset)
    return TransferTransition(state=next_state, event=event)


def advance_deadline(
    state: ManagerState,
    *,
    ruleset: RuleSet,
    source_artifact_id: str,
    active_chip: str | None = None,
) -> ManagerState:
    """Advance the permanent manager state to the next Gameweek deadline state."""

    state.require_decision_safe(ruleset=ruleset)
    chip = active_chip.upper() if active_chip else None
    allowed = {"WILDCARD", "FREE_HIT", "TRIPLE_CAPTAIN", "BENCH_BOOST"}
    if chip is not None and chip not in allowed:
        raise ManagerStateIntegrityError(f"unknown active chip: {active_chip!r}")

    chips = state.chips_used
    if chip is not None:
        chip_use = ChipUse(
            chip=chip,
            gameweek=state.gameweek,
            set_number=_chip_set_for_gameweek(state.gameweek, ruleset=ruleset),
            source_artifact_id=_artifact_id(source_artifact_id),
        )
        candidate = chips + (chip_use,)
        chip_errors = _validate_chip_ledger(candidate, ruleset=ruleset)
        if chip_errors:
            raise ManagerStateIntegrityError("; ".join(chip_errors))
        chips = candidate

    preserves = False
    if chip == "WILDCARD":
        preserves = ruleset.value("FPL-WILDCARD-PRESERVES-BANKED-TRANSFERS-001") is True
    elif chip == "FREE_HIT":
        preserves = ruleset.value("FPL-FREE-HIT-PRESERVES-BANKED-TRANSFERS-001") is True
    if preserves:
        next_ft = state.free_transfers
    else:
        next_ft = min(
            ruleset.integer("FPL-FREE-TRANSFER-BANK-MAX-001"),
            state.free_transfers + ruleset.integer("FPL-FREE-TRANSFER-GRANT-001"),
        )
    result = replace(
        state,
        gameweek=state.gameweek + 1,
        free_transfers=next_ft,
        chips_used=chips,
        provenance_artifact_ids=state.provenance_artifact_ids + (_artifact_id(source_artifact_id),),
    )
    result.require_decision_safe(ruleset=ruleset)
    return result


def attest_deadline_snapshot_current(
    state: ManagerState,
    *,
    attestation: CurrentStateAttestation,
    observed_at: str,
    ruleset: RuleSet,
) -> ManagerState:
    """Promote an exact deadline snapshot only with scoped, immutable current-state attestation."""

    if state.scope is not ManagerStateScope.DEADLINE_SNAPSHOT:
        raise ManagerStateIntegrityError("only a deadline snapshot can be attested current")
    if attestation.gameweek != state.gameweek:
        raise ManagerStateIntegrityError("attestation Gameweek does not match manager state")
    if not attestation.valid_at(observed_at):
        raise ManagerStateIntegrityError("current-state attestation is not valid at observation time")
    result = replace(
        state,
        scope=ManagerStateScope.CURRENT_EXACT,
        provenance_artifact_ids=state.provenance_artifact_ids
        + (attestation.source_artifact_id, attestation.attestation_id),
    )
    result.require_decision_safe(ruleset=ruleset)
    return result
