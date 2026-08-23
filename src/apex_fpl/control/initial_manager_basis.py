"""Build and replay the exact original purchase basis for an FPL entry.

An initial basis can only be certified from a GW1 manager picks snapshot plus an
Official FPL bootstrap that was actually captured before the first deadline. Current or
later player prices can never be substituted for this historical fact.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

from apex_fpl.acquisition import (
    load_official_global_world,
    load_official_manager_public_data,
)
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.identity import IdentityRegistry, OfficialPlayerId
from apex_fpl.core.ids import (
    GlobalWorldId,
    InitialManagerBasisId,
    ManagerPublicSnapshotId,
    RuleSetId,
)
from apex_fpl.core.rules import RuleSet


INITIAL_BASIS_SCHEMA_NAME = "apex-initial-manager-basis"
INITIAL_BASIS_SCHEMA_VERSION = 1


def _parse_aware(value: object, *, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{label} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


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


@dataclass(frozen=True, slots=True)
class InitialPurchaseBasis:
    player_id: OfficialPlayerId
    team_id: int
    position: str
    purchase_basis_tenths: int

    def __post_init__(self) -> None:
        if isinstance(self.team_id, bool) or not isinstance(self.team_id, int) or self.team_id <= 0:
            raise ValueError("initial basis team_id must be a positive integer")
        if self.position not in {"GK", "DEF", "MID", "FWD"}:
            raise ValueError(f"invalid initial basis position: {self.position!r}")
        if (
            isinstance(self.purchase_basis_tenths, bool)
            or not isinstance(self.purchase_basis_tenths, int)
            or self.purchase_basis_tenths <= 0
        ):
            raise ValueError("initial purchase basis must be positive integer tenths")

    def as_dict(self) -> dict[str, object]:
        return {
            "player_id": int(self.player_id),
            "team_id": self.team_id,
            "position": self.position,
            "purchase_basis_tenths": self.purchase_basis_tenths,
        }


@dataclass(frozen=True, slots=True)
class InitialManagerBasis:
    season: str
    entry_id: int
    ruleset_id: RuleSetId
    pre_gw1_global_world_id: GlobalWorldId
    gw1_manager_public_snapshot_id: ManagerPublicSnapshotId
    initial_bank_tenths: int
    players: tuple[InitialPurchaseBasis, ...]
    provenance_artifact_ids: tuple[str, ...]
    schema_version: int = INITIAL_BASIS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != INITIAL_BASIS_SCHEMA_VERSION:
            raise ValueError("unsupported InitialManagerBasis schema_version")
        if not self.season.strip():
            raise ValueError("initial manager basis season cannot be empty")
        if isinstance(self.entry_id, bool) or not isinstance(self.entry_id, int) or self.entry_id <= 0:
            raise ValueError("initial manager basis entry_id must be positive")
        if (
            isinstance(self.initial_bank_tenths, bool)
            or not isinstance(self.initial_bank_tenths, int)
            or self.initial_bank_tenths < 0
        ):
            raise ValueError("initial manager basis bank must be nonnegative integer tenths")
        players = tuple(sorted(self.players, key=lambda row: int(row.player_id)))
        if len(players) != 15 or len({row.player_id for row in players}) != 15:
            raise ValueError("initial manager basis requires exactly 15 unique players")
        provenance = tuple(sorted({_artifact_id(item) for item in self.provenance_artifact_ids}))
        if not provenance:
            raise ValueError("initial manager basis requires immutable provenance")
        object.__setattr__(self, "players", players)
        object.__setattr__(self, "provenance_artifact_ids", provenance)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": INITIAL_BASIS_SCHEMA_NAME,
            "schema_version": self.schema_version,
            "season": self.season,
            "entry_id": self.entry_id,
            "ruleset_id": str(self.ruleset_id),
            "pre_gw1_global_world_id": str(self.pre_gw1_global_world_id),
            "gw1_manager_public_snapshot_id": str(self.gw1_manager_public_snapshot_id),
            "initial_bank_tenths": self.initial_bank_tenths,
            "players": [row.as_dict() for row in self.players],
        }

    @property
    def basis_id(self) -> InitialManagerBasisId:
        return InitialManagerBasisId(canonical_sha256(self.semantic_payload()))

    def as_dict(self) -> dict[str, object]:
        payload = self.semantic_payload()
        payload["initial_manager_basis_id"] = str(self.basis_id)
        payload["provenance_artifact_ids"] = list(self.provenance_artifact_ids)
        return payload

    def purchase_prices(self) -> dict[OfficialPlayerId, int]:
        return {row.player_id: row.purchase_basis_tenths for row in self.players}

    def player_ids(self) -> tuple[OfficialPlayerId, ...]:
        return tuple(row.player_id for row in self.players)


@dataclass(frozen=True, slots=True)
class StoredInitialManagerBasis:
    basis: InitialManagerBasis
    artifact_id: str


def _first_deadline(bootstrap: dict[str, Any]) -> datetime:
    events = bootstrap.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("pre-GW1 bootstrap has no event deadlines")
    deadlines: list[datetime] = []
    for row in events:
        if not isinstance(row, dict) or not row.get("deadline_time"):
            continue
        deadlines.append(_parse_aware(row["deadline_time"], label="FPL deadline_time"))
    if not deadlines:
        raise ValueError("pre-GW1 bootstrap has no valid deadline_time")
    return min(deadlines)


def build_initial_manager_basis(
    *,
    pre_gw1_global_world_manifest_artifact_id: str,
    gw1_manager_public_manifest_artifact_id: str,
    ruleset: RuleSet,
    store: ArtifactStore,
) -> StoredInitialManagerBasis:
    """Create an immutable exact basis from retained pre-deadline and GW1 artifacts."""

    pre_world_manifest = _artifact_id(pre_gw1_global_world_manifest_artifact_id)
    gw1_manifest = _artifact_id(gw1_manager_public_manifest_artifact_id)
    pre_world = load_official_global_world(pre_world_manifest, store=store)
    gw1 = load_official_manager_public_data(gw1_manifest, store=store)

    if pre_world.world.season != ruleset.season:
        raise ValueError("pre-GW1 GlobalWorld season does not match RuleSet")
    if gw1.snapshot.published_gameweek != 1:
        raise ValueError("initial manager basis requires a sealed GW1 picks snapshot")

    deadline = _first_deadline(pre_world.bootstrap)
    bootstrap_capture = next(
        (row for row in pre_world.captures if row.source_name == "official_fpl_bootstrap"),
        None,
    )
    if bootstrap_capture is None:
        raise ValueError("pre-GW1 GlobalWorld is missing Official bootstrap capture")
    retrieved = _parse_aware(bootstrap_capture.retrieved_at, label="bootstrap retrieved_at")
    if retrieved >= deadline:
        raise ValueError(
            "initial purchase basis requires Official bootstrap captured before first deadline"
        )

    registry = IdentityRegistry.from_official_bootstrap(pre_world.bootstrap)
    pick_rows = gw1.picks.get("picks")
    if not isinstance(pick_rows, list) or len(pick_rows) != 15:
        raise ValueError("sealed GW1 manager snapshot does not contain 15 picks")
    players: list[InitialPurchaseBasis] = []
    for row in pick_rows:
        if not isinstance(row, dict):
            raise ValueError("sealed GW1 pick row is invalid")
        player_id = OfficialPlayerId(int(row["element"]))
        official = registry.get(player_id)
        if official is None:
            raise ValueError(f"GW1 pick {player_id} is absent from pre-GW1 Official bootstrap")
        players.append(
            InitialPurchaseBasis(
                player_id=player_id,
                team_id=official.team_id,
                position=official.position,
                purchase_basis_tenths=official.price_tenths,
            )
        )

    legality = ruleset.validate_squad(
        positions=(row.position for row in players),
        club_ids=(row.team_id for row in players),
        prices_tenths=(row.purchase_basis_tenths for row in players),
    )
    if legality:
        raise ValueError("GW1 initial squad is illegal under RuleSet: " + "; ".join(legality))
    initial_bank = ruleset.integer("FPL-SQUAD-BUDGET-TENTHS-001") - sum(
        row.purchase_basis_tenths for row in players
    )
    entry_history = gw1.picks.get("entry_history")
    if not isinstance(entry_history, dict):
        raise ValueError("sealed GW1 picks are missing entry_history")
    if entry_history.get("bank") is None:
        raise ValueError("sealed GW1 picks are missing Official bank")
    published_bank = int(entry_history["bank"])
    if published_bank != initial_bank:
        raise ValueError(
            f"pre-GW1 purchase basis bank {initial_bank} != Official GW1 bank {published_bank}"
        )

    basis = InitialManagerBasis(
        season=ruleset.season,
        entry_id=gw1.snapshot.entry_id,
        ruleset_id=ruleset.ruleset_id,
        pre_gw1_global_world_id=pre_world.world.world_id,
        gw1_manager_public_snapshot_id=gw1.snapshot.snapshot_id,
        initial_bank_tenths=initial_bank,
        players=tuple(players),
        provenance_artifact_ids=(pre_world_manifest, gw1_manifest),
    )
    ref = store.put_bytes(
        canonical_json_bytes(basis.as_dict()),
        media_type="application/json",
        schema_name=INITIAL_BASIS_SCHEMA_NAME,
        schema_version=str(INITIAL_BASIS_SCHEMA_VERSION),
    )
    return StoredInitialManagerBasis(basis=basis, artifact_id=ref.artifact_id)


def load_initial_manager_basis(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> InitialManagerBasis:
    """Replay a sealed initial manager basis without network or clock access."""

    raw = store.read_bytes(_artifact_id(artifact_id))
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("initial manager basis artifact is not UTF-8 JSON") from exc
    if not isinstance(payload, dict) or payload.get("schema_name") != INITIAL_BASIS_SCHEMA_NAME:
        raise ValueError("not an Apex initial manager basis artifact")
    rows = payload.get("players")
    provenance = payload.get("provenance_artifact_ids")
    if not isinstance(rows, list) or not isinstance(provenance, list):
        raise ValueError("initial manager basis artifact is incomplete")
    basis = InitialManagerBasis(
        season=str(payload["season"]),
        entry_id=int(payload["entry_id"]),
        ruleset_id=RuleSetId(str(payload["ruleset_id"])),
        pre_gw1_global_world_id=GlobalWorldId(str(payload["pre_gw1_global_world_id"])),
        gw1_manager_public_snapshot_id=ManagerPublicSnapshotId(
            str(payload["gw1_manager_public_snapshot_id"])
        ),
        initial_bank_tenths=int(payload["initial_bank_tenths"]),
        players=tuple(
            InitialPurchaseBasis(
                player_id=OfficialPlayerId(int(row["player_id"])),
                team_id=int(row["team_id"]),
                position=str(row["position"]),
                purchase_basis_tenths=int(row["purchase_basis_tenths"]),
            )
            for row in rows
            if isinstance(row, dict)
        ),
        provenance_artifact_ids=tuple(str(item) for item in provenance),
        schema_version=int(payload.get("schema_version", -1)),
    )
    declared = payload.get("initial_manager_basis_id")
    if declared is not None and str(declared) != str(basis.basis_id):
        raise ValueError("initial manager basis semantic identity mismatch")
    return basis
