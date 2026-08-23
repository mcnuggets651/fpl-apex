"""Fail-closed reconstruction of exact public FPL deadline manager state.

Official FPL's public transfer endpoint exposes the *realised sale price* as
``element_out_cost``. It does not expose the player's market price at the instant of a
historical transfer. V2 therefore never fabricates a historical market price merely to
re-run the selling-price formula.

Historical public transactions are reconstructed as authoritative sale receipts. Live
transitions remain in ``core.manager_state.TransferLedgerEvent``, where Apex has an
exact current Official price and can prove the RuleSet selling formula directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping

from apex_fpl.core.canonical import canonical_sha256
from apex_fpl.core.identity import OfficialPlayerId, OfficialPlayerIdentity
from apex_fpl.core.manager_state import (
    ChipUse,
    ManagerState,
    ManagerStateIntegrityError,
    ManagerStateScope,
    owned_player_from_official,
)
from apex_fpl.core.rules import RuleSet


class ManagerStateResolutionStatus(str, Enum):
    EXACT_DEADLINE_SNAPSHOT = "EXACT_DEADLINE_SNAPSHOT"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"invalid provenance artifact ID: {value!r}")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"invalid provenance artifact digest: {value!r}") from exc
    return text


@dataclass(frozen=True, slots=True)
class PublicTransferRecord:
    """One Official FPL public transfer transaction.

    ``realised_sale_tenths`` maps directly to Official FPL ``element_out_cost``.
    No historical market price is inferred from this value.
    """

    transfer_id: str
    gameweek: int
    sequence: int
    outgoing_player_id: OfficialPlayerId
    incoming_player_id: OfficialPlayerId
    realised_sale_tenths: int
    incoming_purchase_tenths: int
    source_artifact_id: str

    def __post_init__(self) -> None:
        if not self.transfer_id.strip():
            raise ValueError("public transfer requires an ID")
        _artifact_id(self.source_artifact_id)
        for name in ("gameweek", "sequence"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"public transfer {name} must be a positive integer")
        for name in ("realised_sale_tenths", "incoming_purchase_tenths"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"public transfer {name} must be a positive integer")
        if self.outgoing_player_id == self.incoming_player_id:
            raise ValueError("public transfer outgoing/incoming IDs must differ")


@dataclass(frozen=True, slots=True)
class PublicChipRecord:
    chip: str
    gameweek: int
    source_artifact_id: str

    def __post_init__(self) -> None:
        chip = self.chip.upper()
        if chip not in {"WILDCARD", "FREE_HIT", "TRIPLE_CAPTAIN", "BENCH_BOOST"}:
            raise ValueError(f"unsupported public chip: {self.chip!r}")
        if (
            isinstance(self.gameweek, bool)
            or not isinstance(self.gameweek, int)
            or self.gameweek <= 0
        ):
            raise ValueError("public chip gameweek must be a positive integer")
        _artifact_id(self.source_artifact_id)
        object.__setattr__(self, "chip", chip)


@dataclass(frozen=True, slots=True)
class HistoricalTransferReceipt:
    """Reconciled historical transaction without an invented market-price field."""

    transfer_id: str
    sequence: int
    gameweek: int
    outgoing_player_id: OfficialPlayerId
    incoming_player_id: OfficialPlayerId
    outgoing_purchase_basis_tenths: int
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
        if self.mode not in {"NORMAL", "WILDCARD"}:
            raise ValueError(f"unsupported historical transfer mode: {self.mode}")
        _artifact_id(self.source_artifact_id)

    def as_dict(self) -> dict[str, object]:
        return {
            "transfer_id": self.transfer_id,
            "sequence": self.sequence,
            "gameweek": self.gameweek,
            "outgoing_player_id": int(self.outgoing_player_id),
            "incoming_player_id": int(self.incoming_player_id),
            "outgoing_purchase_basis_tenths": self.outgoing_purchase_basis_tenths,
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
class HistoricalTransferLedger:
    entry_id: int
    through_gameweek: int
    initial_bank_tenths: int
    final_bank_tenths: int
    receipts: tuple[HistoricalTransferReceipt, ...]

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-historical-manager-transfer-ledger",
            "schema_version": 1,
            "entry_id": self.entry_id,
            "through_gameweek": self.through_gameweek,
            "initial_bank_tenths": self.initial_bank_tenths,
            "final_bank_tenths": self.final_bank_tenths,
            "receipts": [row.as_dict() for row in self.receipts],
        }

    @property
    def ledger_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ManagerStateResolution:
    status: ManagerStateResolutionStatus
    state: ManagerState | None
    blockers: tuple[str, ...]
    evidence: tuple[str, ...]
    historical_ledger: HistoricalTransferLedger | None = None

    @property
    def exact_deadline_snapshot(self) -> bool:
        return (
            self.status is ManagerStateResolutionStatus.EXACT_DEADLINE_SNAPSHOT
            and self.state is not None
            and self.historical_ledger is not None
        )


def _chip_map(chips: Iterable[PublicChipRecord]) -> dict[int, str]:
    result: dict[int, str] = {}
    for row in chips:
        if row.gameweek in result:
            raise ManagerStateIntegrityError(f"multiple public chips in GW{row.gameweek}")
        result[row.gameweek] = row.chip
    return result


def _chip_set(gameweek: int, *, ruleset: RuleSet) -> int:
    return 1 if gameweek <= ruleset.integer("FPL-CHIP-FIRST-SET-LAST-GW-001") else 2


def _validated_history_value(
    values: Mapping[int, int],
    *,
    gameweek: int,
    label: str,
) -> int:
    value = values.get(gameweek)
    if value is None:
        raise ManagerStateIntegrityError(f"public {label} missing for GW{gameweek}")
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ManagerStateIntegrityError(f"public {label} for GW{gameweek} is invalid")
    return value


def _advance_ft(
    free_transfers: int,
    *,
    transfers: int,
    chip: str | None,
    ruleset: RuleSet,
) -> int:
    if chip == "WILDCARD" and ruleset.value(
        "FPL-WILDCARD-PRESERVES-BANKED-TRANSFERS-001"
    ) is True:
        return free_transfers
    if chip == "FREE_HIT" and ruleset.value(
        "FPL-FREE-HIT-PRESERVES-BANKED-TRANSFERS-001"
    ) is True:
        return free_transfers
    remaining = max(0, free_transfers - transfers)
    return min(
        ruleset.integer("FPL-FREE-TRANSFER-BANK-MAX-001"),
        remaining + ruleset.integer("FPL-FREE-TRANSFER-GRANT-001"),
    )


def derive_next_window_free_transfers(
    *,
    published_gameweek: int,
    event_transfer_counts: Mapping[int, int],
    chips: Iterable[PublicChipRecord],
    ruleset: RuleSet,
) -> int:
    """Replay public per-GW transfer counts to FT available after published GW."""

    if published_gameweek <= 0:
        raise ManagerStateIntegrityError("published_gameweek must be positive")
    chip_by_gw = _chip_map(chips)
    if any(gameweek > published_gameweek for gameweek in chip_by_gw):
        raise ManagerStateIntegrityError("public chip history contains a future Gameweek")
    free_transfers = 0
    for gameweek in range(1, published_gameweek + 1):
        transfers = _validated_history_value(
            event_transfer_counts,
            gameweek=gameweek,
            label="event transfer count",
        )
        free_transfers = _advance_ft(
            free_transfers,
            transfers=transfers,
            chip=chip_by_gw.get(gameweek),
            ruleset=ruleset,
        )
    return free_transfers


def reconstruct_public_deadline_state(
    *,
    season: str,
    entry_id: int,
    published_gameweek: int,
    published_squad_ids: Iterable[OfficialPlayerId],
    published_bank_tenths: int,
    current_official: Mapping[OfficialPlayerId, OfficialPlayerIdentity],
    initial_squad_ids: Iterable[OfficialPlayerId],
    initial_purchase_prices_tenths: Mapping[OfficialPlayerId, int],
    transfers: Iterable[PublicTransferRecord],
    event_transfer_counts: Mapping[int, int],
    event_transfer_costs: Mapping[int, int],
    chips: Iterable[PublicChipRecord],
    ruleset: RuleSet,
    provenance_artifact_ids: Iterable[str],
    transfer_history_complete: bool,
    initial_price_capture_complete: bool,
) -> ManagerStateResolution:
    """Reconstruct exact public deadline state using Official realised sale receipts."""

    blockers: list[str] = []
    try:
        evidence = tuple(sorted({_artifact_id(str(item)) for item in provenance_artifact_ids}))
    except ValueError as exc:
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            (str(exc),),
            (),
        )
    if not transfer_history_complete:
        blockers.append("public transfer history is not proven complete")
    if not initial_price_capture_complete:
        blockers.append("pre-GW1 Official price capture is not proven complete")
    if (
        isinstance(published_bank_tenths, bool)
        or not isinstance(published_bank_tenths, int)
        or published_bank_tenths < 0
    ):
        blockers.append("published bank must be a nonnegative integer in tenths")
    initial_ids = tuple(initial_squad_ids)
    published_ids = tuple(published_squad_ids)
    if len(initial_ids) != 15 or len(set(initial_ids)) != 15:
        blockers.append("initial published squad is not exactly 15 unique Official IDs")
    if len(published_ids) != 15 or len(set(published_ids)) != 15:
        blockers.append("latest published squad is not exactly 15 unique Official IDs")
    missing_initial_prices = sorted(
        int(player_id)
        for player_id in set(initial_ids) - set(initial_purchase_prices_tenths)
    )
    if missing_initial_prices:
        blockers.append(
            f"initial purchase basis missing for player IDs: {missing_initial_prices}"
        )
    missing_current = sorted(
        int(player_id) for player_id in set(published_ids) - set(current_official)
    )
    if missing_current:
        blockers.append(
            f"current Official identities/prices missing for owned IDs: {missing_current}"
        )
    if not evidence:
        blockers.append("manager-state reconstruction has no immutable provenance")
    if blockers:
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INCOMPLETE,
            None,
            tuple(blockers),
            evidence,
        )

    chip_rows = tuple(chips)
    try:
        chip_by_gw = _chip_map(chip_rows)
    except ManagerStateIntegrityError as exc:
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            (str(exc),),
            evidence,
        )
    if any(gameweek > published_gameweek for gameweek in chip_by_gw):
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            ("public chip history contains a future Gameweek",),
            evidence,
        )

    transfer_rows = tuple(sorted(transfers, key=lambda row: (row.gameweek, row.sequence)))
    if len({row.transfer_id for row in transfer_rows}) != len(transfer_rows):
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            ("public transfer IDs are not unique",),
            evidence,
        )
    if len({(row.gameweek, row.sequence) for row in transfer_rows}) != len(transfer_rows):
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            ("public transfer chronology sequence is not unique",),
            evidence,
        )
    if any(row.gameweek > published_gameweek for row in transfer_rows):
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            ("public transfer history contains post-snapshot transfers",),
            evidence,
        )

    rows_per_gw: dict[int, int] = {}
    for row in transfer_rows:
        rows_per_gw[row.gameweek] = rows_per_gw.get(row.gameweek, 0) + 1
    for gameweek in range(1, published_gameweek + 1):
        try:
            expected = _validated_history_value(
                event_transfer_counts,
                gameweek=gameweek,
                label="event transfer count",
            )
            _validated_history_value(
                event_transfer_costs,
                gameweek=gameweek,
                label="event transfer cost",
            )
        except ManagerStateIntegrityError as exc:
            blockers.append(str(exc))
            continue
        if chip_by_gw.get(gameweek) == "FREE_HIT":
            if rows_per_gw.get(gameweek, 0):
                blockers.append(
                    f"GW{gameweek} Free Hit has transfer rows whose permanent semantics are unverified"
                )
            continue
        if rows_per_gw.get(gameweek, 0) != expected:
            blockers.append(
                f"GW{gameweek} transfer receipt rows {rows_per_gw.get(gameweek, 0)} "
                f"!= public event_transfers {expected}"
            )
    if blockers:
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INCOMPLETE,
            None,
            tuple(blockers),
            evidence,
        )

    ownership_basis: dict[OfficialPlayerId, int] = {}
    for player_id in initial_ids:
        basis = initial_purchase_prices_tenths[player_id]
        if isinstance(basis, bool) or not isinstance(basis, int) or basis <= 0:
            return ManagerStateResolution(
                ManagerStateResolutionStatus.INVALID,
                None,
                (f"initial purchase basis for player {player_id} is invalid",),
                evidence,
            )
        ownership_basis[player_id] = basis
    initial_cost = sum(ownership_basis.values())
    initial_bank = ruleset.integer("FPL-SQUAD-BUDGET-TENTHS-001") - initial_cost
    if initial_bank < 0:
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            ("initial squad purchase cost exceeded RuleSet budget",),
            evidence,
        )

    free_before_gw = 0
    bank = initial_bank
    receipts: list[HistoricalTransferReceipt] = []
    sequence = 0
    by_gw: dict[int, list[PublicTransferRecord]] = {}
    for row in transfer_rows:
        by_gw.setdefault(row.gameweek, []).append(row)

    for gameweek in range(1, published_gameweek + 1):
        chip = chip_by_gw.get(gameweek)
        if chip == "FREE_HIT" and by_gw.get(gameweek):
            return ManagerStateResolution(
                ManagerStateResolutionStatus.INCOMPLETE,
                None,
                (f"GW{gameweek} Free Hit transfer rows cannot mutate permanent state",),
                evidence,
            )
        free_remaining = free_before_gw
        for row in by_gw.get(gameweek, []):
            if row.outgoing_player_id not in ownership_basis:
                return ManagerStateResolution(
                    ManagerStateResolutionStatus.INVALID,
                    None,
                    (f"transfer {row.transfer_id} sells a player not owned",),
                    evidence,
                )
            if row.incoming_player_id in ownership_basis:
                return ManagerStateResolution(
                    ManagerStateResolutionStatus.INVALID,
                    None,
                    (f"transfer {row.transfer_id} buys an already-owned player",),
                    evidence,
                )
            basis = ownership_basis[row.outgoing_player_id]
            bank_after = bank + row.realised_sale_tenths - row.incoming_purchase_tenths
            if bank_after < 0:
                return ManagerStateResolution(
                    ManagerStateResolutionStatus.INVALID,
                    None,
                    (f"transfer {row.transfer_id} creates negative bank",),
                    evidence,
                )
            wildcard = chip == "WILDCARD"
            if wildcard:
                free_after = free_remaining
                hit_points = 0
                mode = "WILDCARD"
            else:
                free_after = max(0, free_remaining - 1)
                hit_points = (
                    0
                    if free_remaining > 0
                    else ruleset.integer("FPL-EXTRA-TRANSFER-HIT-POINTS-001")
                )
                mode = "NORMAL"
            sequence += 1
            receipts.append(
                HistoricalTransferReceipt(
                    transfer_id=row.transfer_id,
                    sequence=sequence,
                    gameweek=gameweek,
                    outgoing_player_id=row.outgoing_player_id,
                    incoming_player_id=row.incoming_player_id,
                    outgoing_purchase_basis_tenths=basis,
                    realised_sale_tenths=row.realised_sale_tenths,
                    incoming_purchase_tenths=row.incoming_purchase_tenths,
                    bank_before_tenths=bank,
                    bank_after_tenths=bank_after,
                    free_transfers_before=free_remaining,
                    free_transfers_after=free_after,
                    hit_points=hit_points,
                    mode=mode,
                    source_artifact_id=row.source_artifact_id,
                )
            )
            del ownership_basis[row.outgoing_player_id]
            ownership_basis[row.incoming_player_id] = row.incoming_purchase_tenths
            bank = bank_after
            free_remaining = free_after

        official_cost = event_transfer_costs[gameweek]
        derived_cost = sum(
            receipt.hit_points for receipt in receipts if receipt.gameweek == gameweek
        )
        if derived_cost != official_cost:
            return ManagerStateResolution(
                ManagerStateResolutionStatus.INVALID,
                None,
                (
                    f"GW{gameweek} reconstructed transfer cost {derived_cost} "
                    f"!= public event_transfers_cost {official_cost}",
                ),
                evidence,
            )
        free_before_gw = _advance_ft(
            free_before_gw,
            transfers=event_transfer_counts[gameweek],
            chip=chip,
            ruleset=ruleset,
        )

    if set(ownership_basis) != set(published_ids):
        missing = sorted(int(item) for item in set(published_ids) - set(ownership_basis))
        extra = sorted(int(item) for item in set(ownership_basis) - set(published_ids))
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            (
                "reconstructed ownership does not match published picks; "
                f"missing={missing} extra={extra}",
            ),
            evidence,
        )
    if bank != published_bank_tenths:
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            (f"reconstructed bank {bank} != published bank {published_bank_tenths}",),
            evidence,
        )

    ledger = HistoricalTransferLedger(
        entry_id=entry_id,
        through_gameweek=published_gameweek,
        initial_bank_tenths=initial_bank,
        final_bank_tenths=bank,
        receipts=tuple(receipts),
    )
    try:
        next_ft = derive_next_window_free_transfers(
            published_gameweek=published_gameweek,
            event_transfer_counts=event_transfer_counts,
            chips=chip_rows,
            ruleset=ruleset,
        )
        owned = tuple(
            owned_player_from_official(
                current_official[player_id],
                purchase_basis_tenths=ownership_basis[player_id],
                current_price_tenths=current_official[player_id].price_tenths,
                ruleset=ruleset,
            )
            for player_id in published_ids
        )
        chip_uses = tuple(
            ChipUse(
                chip=row.chip,
                gameweek=row.gameweek,
                set_number=_chip_set(row.gameweek, ruleset=ruleset),
                source_artifact_id=row.source_artifact_id,
            )
            for row in chip_rows
        )
        state = ManagerState(
            season=season,
            entry_id=entry_id,
            gameweek=published_gameweek + 1,
            ruleset_id=ruleset.ruleset_id,
            scope=ManagerStateScope.DEADLINE_SNAPSHOT,
            bank_tenths=published_bank_tenths,
            free_transfers=next_ft,
            squad=owned,
            chips_used=chip_uses,
            transfer_ledger=(),
            provenance_artifact_ids=evidence,
        )
        errors = state.validation_errors(ruleset=ruleset)
        if errors:
            raise ManagerStateIntegrityError("; ".join(errors))
    except (KeyError, TypeError, ValueError, ManagerStateIntegrityError) as exc:
        return ManagerStateResolution(
            ManagerStateResolutionStatus.INVALID,
            None,
            (str(exc),),
            evidence,
        )
    return ManagerStateResolution(
        ManagerStateResolutionStatus.EXACT_DEADLINE_SNAPSHOT,
        state,
        (),
        evidence,
        ledger,
    )
