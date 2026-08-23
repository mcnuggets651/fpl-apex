"""Reconstruct V2 manager state exclusively from immutable sealed artifacts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import groupby
from typing import Any, Iterable

from apex_fpl.acquisition import (
    ReplayedManagerPublicData,
    load_official_global_world,
    load_official_manager_public_data,
)
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.initial_manager_basis import load_initial_manager_basis
from apex_fpl.control.manager_state_reconstruction import (
    ManagerStateResolution,
    ManagerStateResolutionStatus,
    PublicChipRecord,
    PublicTransferRecord,
    reconstruct_public_deadline_state,
)
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.identity import IdentityRegistry, OfficialPlayerId, OfficialPlayerIdentity
from apex_fpl.core.rules import RuleSet


HISTORICAL_LEDGER_SCHEMA_NAME = "apex-historical-manager-transfer-ledger"
HISTORICAL_LEDGER_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SealedManagerStateReconstruction:
    resolution: ManagerStateResolution
    historical_ledger_artifact_id: str | None


def _artifact_id(value: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"invalid artifact ID: {value!r}")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"invalid artifact digest: {value!r}") from exc
    return text


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be a nonnegative integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be a nonnegative integer") from exc
    if result < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return result


def _positive_int(value: object, *, label: str) -> int:
    result = _nonnegative_int(value, label=label)
    if result <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return result


def _parse_time(value: object) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Official transfer time is invalid: {value!r}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Official transfer time must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def _source_artifact(data: ReplayedManagerPublicData, source_name: str) -> str:
    for row in data.snapshot.sources:
        if row.source_name == source_name:
            return row.artifact_id
    raise ValueError(f"sealed manager snapshot is missing source {source_name}")


def _normalise_chip_name(value: object) -> str:
    text = str(value or "").casefold().replace("_", "").replace("-", "").strip()
    aliases = {
        "wildcard": "WILDCARD",
        "freehit": "FREE_HIT",
        "3xc": "TRIPLE_CAPTAIN",
        "triplecaptain": "TRIPLE_CAPTAIN",
        "bboost": "BENCH_BOOST",
        "benchboost": "BENCH_BOOST",
    }
    try:
        return aliases[text]
    except KeyError as exc:
        raise ValueError(f"unsupported Official FPL chip name: {value!r}") from exc


def _event_history(
    data: ReplayedManagerPublicData,
) -> tuple[dict[int, int], dict[int, int]]:
    target = data.snapshot.published_gameweek
    current = data.history.get("current")
    if not isinstance(current, list):
        raise ValueError("sealed manager history current rows are missing")
    counts: dict[int, int] = {}
    costs: dict[int, int] = {}
    for row in current:
        if not isinstance(row, dict):
            raise ValueError("sealed manager history row is invalid")
        gameweek = _positive_int(row.get("event"), label="history event")
        if gameweek > target:
            continue
        if gameweek in counts:
            raise ValueError(f"sealed manager history contains duplicate GW{gameweek} rows")
        counts[gameweek] = _nonnegative_int(
            row.get("event_transfers", 0),
            label=f"GW{gameweek} event_transfers",
        )
        costs[gameweek] = _nonnegative_int(
            row.get("event_transfers_cost", 0),
            label=f"GW{gameweek} event_transfers_cost",
        )

    entry_history = data.picks.get("entry_history")
    if not isinstance(entry_history, dict):
        raise ValueError("sealed target picks entry_history is missing")
    target_count = _nonnegative_int(
        entry_history.get("event_transfers", 0),
        label=f"GW{target} picks event_transfers",
    )
    target_cost = _nonnegative_int(
        entry_history.get("event_transfers_cost", 0),
        label=f"GW{target} picks event_transfers_cost",
    )
    if target in counts and (counts[target] != target_count or costs[target] != target_cost):
        raise ValueError(f"GW{target} history conflicts with target picks entry_history")
    counts[target] = target_count
    costs[target] = target_cost
    return counts, costs


def _chips(data: ReplayedManagerPublicData) -> tuple[PublicChipRecord, ...]:
    target = data.snapshot.published_gameweek
    source = _source_artifact(data, "official_fpl_entry_history")
    rows = data.history.get("chips")
    if not isinstance(rows, list):
        raise ValueError("sealed manager chip history is missing")
    by_gameweek: dict[int, PublicChipRecord] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("sealed manager chip row is invalid")
        gameweek = _positive_int(row.get("event"), label="chip event")
        if gameweek > target:
            raise ValueError("sealed manager chip history contains a future Gameweek")
        if gameweek in by_gameweek:
            raise ValueError(f"sealed manager chip history contains duplicate GW{gameweek} rows")
        by_gameweek[gameweek] = PublicChipRecord(
            chip=_normalise_chip_name(row.get("name")),
            gameweek=gameweek,
            source_artifact_id=source,
        )

    active = data.picks.get("active_chip")
    if active:
        target_chip = PublicChipRecord(
            chip=_normalise_chip_name(active),
            gameweek=target,
            source_artifact_id=_source_artifact(data, "official_fpl_entry_picks"),
        )
        existing = by_gameweek.get(target)
        if existing is not None and existing.chip != target_chip.chip:
            raise ValueError("history chip conflicts with target picks active_chip")
        by_gameweek[target] = target_chip
    return tuple(by_gameweek[gameweek] for gameweek in sorted(by_gameweek))


def _canonical_transfer_group(
    rows: list[tuple[int, dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Canonicalise same-timestamp disjoint batch rows without claiming chronology."""

    participants: list[int] = []
    for _, row in rows:
        participants.extend(
            [
                _positive_int(row.get("element_out"), label="transfer element_out"),
                _positive_int(row.get("element_in"), label="transfer element_in"),
            ]
        )
    if len(participants) != len(set(participants)):
        raise ValueError(
            "same-timestamp transfers have dependent player identities; exact chronology is ambiguous"
        )
    return [
        row
        for _, row in sorted(
            rows,
            key=lambda item: (
                -(
                    _positive_int(
                        item[1].get("element_out_cost"),
                        label="element_out_cost",
                    )
                    - _positive_int(
                        item[1].get("element_in_cost"),
                        label="element_in_cost",
                    )
                ),
                _positive_int(item[1].get("element_out"), label="element_out"),
                _positive_int(item[1].get("element_in"), label="element_in"),
                item[0],
            ),
        )
    ]


def _transfers(data: ReplayedManagerPublicData) -> tuple[PublicTransferRecord, ...]:
    target = data.snapshot.published_gameweek
    source = _source_artifact(data, "official_fpl_entry_transfers")
    parsed: list[tuple[int, datetime, dict[str, Any]]] = []
    for index, raw in enumerate(data.transfers):
        row = dict(raw)
        gameweek = _positive_int(row.get("event"), label="transfer event")
        if gameweek > target:
            raise ValueError("sealed public transfer history contains post-snapshot transfers")
        parsed.append((index, _parse_time(row.get("time")), row))

    ordered: list[dict[str, Any]] = []
    for _, same_time in groupby(
        sorted(parsed, key=lambda item: (item[1], item[0])),
        key=lambda item: item[1],
    ):
        group = [(index, row) for index, _, row in same_time]
        ordered.extend(_canonical_transfer_group(group))

    result: list[PublicTransferRecord] = []
    per_gw_sequence: dict[int, int] = {}
    for row in ordered:
        gameweek = _positive_int(row.get("event"), label="transfer event")
        per_gw_sequence[gameweek] = per_gw_sequence.get(gameweek, 0) + 1
        identity_payload = {
            "entry": _positive_int(
                row.get("entry", data.snapshot.entry_id),
                label="transfer entry",
            ),
            "event": gameweek,
            "time": str(row.get("time")),
            "element_out": _positive_int(
                row.get("element_out"),
                label="transfer element_out",
            ),
            "element_in": _positive_int(
                row.get("element_in"),
                label="transfer element_in",
            ),
            "element_out_cost": _positive_int(
                row.get("element_out_cost"),
                label="element_out_cost",
            ),
            "element_in_cost": _positive_int(
                row.get("element_in_cost"),
                label="element_in_cost",
            ),
        }
        if identity_payload["entry"] != data.snapshot.entry_id:
            raise ValueError("Official transfer row entry does not match sealed manager entry")
        transfer_id = canonical_sha256(
            {
                "schema_name": "apex-official-transfer-receipt",
                "schema_version": 1,
                **identity_payload,
            }
        )
        result.append(
            PublicTransferRecord(
                transfer_id=transfer_id,
                gameweek=gameweek,
                sequence=per_gw_sequence[gameweek],
                outgoing_player_id=OfficialPlayerId(identity_payload["element_out"]),
                incoming_player_id=OfficialPlayerId(identity_payload["element_in"]),
                realised_sale_tenths=identity_payload["element_out_cost"],
                incoming_purchase_tenths=identity_payload["element_in_cost"],
                source_artifact_id=source,
            )
        )
    return tuple(result)


def _current_identities(
    bootstrap: dict[str, Any],
    player_ids: Iterable[OfficialPlayerId],
) -> dict[OfficialPlayerId, OfficialPlayerIdentity]:
    registry = IdentityRegistry.from_official_bootstrap(bootstrap)
    result: dict[OfficialPlayerId, OfficialPlayerIdentity] = {}
    for player_id in player_ids:
        player = registry.get(player_id)
        if player is None:
            raise ValueError(
                f"current sealed Official bootstrap is missing player {player_id}"
            )
        result[player_id] = player
    return result


def reconstruct_manager_state_from_seals(
    *,
    current_global_world_manifest_artifact_id: str,
    current_manager_public_manifest_artifact_id: str,
    initial_manager_basis_artifact_id: str,
    ruleset: RuleSet,
    store: ArtifactStore,
) -> SealedManagerStateReconstruction:
    """Build an exact public deadline state without V1 cache/files/network access."""

    world_manifest = _artifact_id(current_global_world_manifest_artifact_id)
    manager_manifest = _artifact_id(current_manager_public_manifest_artifact_id)
    basis_artifact = _artifact_id(initial_manager_basis_artifact_id)
    world = load_official_global_world(world_manifest, store=store)
    manager = load_official_manager_public_data(manager_manifest, store=store)
    basis = load_initial_manager_basis(basis_artifact, store=store)

    if world.world.season != ruleset.season or basis.season != ruleset.season:
        raise ValueError("sealed manager reconstruction season does not match RuleSet")
    if basis.ruleset_id != ruleset.ruleset_id:
        raise ValueError("initial manager basis RuleSetId does not match active RuleSet")
    if manager.snapshot.entry_id != basis.entry_id:
        raise ValueError("current manager snapshot entry does not match initial basis")

    pick_rows = manager.picks.get("picks")
    if not isinstance(pick_rows, list) or len(pick_rows) != 15:
        raise ValueError("sealed current manager picks are incomplete")
    published_ids = tuple(
        OfficialPlayerId(_positive_int(row.get("element"), label="pick element"))
        for row in pick_rows
        if isinstance(row, dict)
    )
    if len(published_ids) != 15:
        raise ValueError("sealed current manager picks contain invalid rows")
    current_official = _current_identities(world.bootstrap, published_ids)
    counts, costs = _event_history(manager)
    chips = _chips(manager)
    transfers = _transfers(manager)
    entry_history = manager.picks.get("entry_history")
    if not isinstance(entry_history, dict) or entry_history.get("bank") is None:
        raise ValueError("sealed current manager picks are missing Official bank")
    bank = _nonnegative_int(entry_history["bank"], label="published bank")

    source_ids = tuple(row.artifact_id for row in manager.snapshot.sources)
    evidence = (
        world_manifest,
        manager_manifest,
        basis_artifact,
        *basis.provenance_artifact_ids,
        *source_ids,
    )
    resolution = reconstruct_public_deadline_state(
        season=ruleset.season,
        entry_id=manager.snapshot.entry_id,
        published_gameweek=manager.snapshot.published_gameweek,
        published_squad_ids=published_ids,
        published_bank_tenths=bank,
        current_official=current_official,
        initial_squad_ids=basis.player_ids(),
        initial_purchase_prices_tenths=basis.purchase_prices(),
        transfers=transfers,
        event_transfer_counts=counts,
        event_transfer_costs=costs,
        chips=chips,
        ruleset=ruleset,
        provenance_artifact_ids=evidence,
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    if resolution.status is not ManagerStateResolutionStatus.EXACT_DEADLINE_SNAPSHOT:
        return SealedManagerStateReconstruction(resolution, None)
    if resolution.state is None or resolution.historical_ledger is None:
        raise ValueError("exact reconstruction omitted state or historical ledger")

    ledger_ref = store.put_bytes(
        canonical_json_bytes(resolution.historical_ledger.semantic_payload()),
        media_type="application/json",
        schema_name=HISTORICAL_LEDGER_SCHEMA_NAME,
        schema_version=str(HISTORICAL_LEDGER_SCHEMA_VERSION),
    )
    state = replace(
        resolution.state,
        provenance_artifact_ids=resolution.state.provenance_artifact_ids
        + (ledger_ref.artifact_id,),
    )
    errors = state.validation_errors(ruleset=ruleset)
    if errors:
        raise ValueError(
            "sealed reconstructed manager state failed validation: "
            + "; ".join(errors)
        )
    resolution = replace(
        resolution,
        state=state,
        evidence=tuple(sorted(set(resolution.evidence + (ledger_ref.artifact_id,)))),
    )
    return SealedManagerStateReconstruction(resolution, ledger_ref.artifact_id)
