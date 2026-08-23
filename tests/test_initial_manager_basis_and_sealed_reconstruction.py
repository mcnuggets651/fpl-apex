from __future__ import annotations

from datetime import datetime, timezone
import inspect
import json
from pathlib import Path

import pytest

from apex_fpl.acquisition import (
    FPL_API_BASE,
    FPL_BOOTSTRAP_URL,
    FPL_FIXTURES_URL,
    HttpResponse,
    acquire_official_global_world,
    acquire_official_manager_public_data,
)
from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.initial_manager_basis import (
    build_initial_manager_basis,
    load_initial_manager_basis,
)
from apex_fpl.control.manager_state_from_seals import reconstruct_manager_state_from_seals
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.manager_state import ManagerStateScope


ROOT = Path(__file__).resolve().parents[1]
RULESET = load_ruleset(ROOT / "config/rules/2026-2027.yaml")
ENTRY_ID = 63984
POSITIONS = (
    "GK",
    "GK",
    "DEF",
    "DEF",
    "DEF",
    "DEF",
    "DEF",
    "MID",
    "MID",
    "MID",
    "MID",
    "MID",
    "FWD",
    "FWD",
    "FWD",
)
ELEMENT_TYPES = {"GK": 1, "DEF": 2, "MID": 3, "FWD": 4}
PRICES = (40, 40, 45, 45, 45, 45, 45, 50, 50, 50, 50, 50, 55, 55, 55)
INITIAL_BANK = 1000 - sum(PRICES)
DEADLINE = "2026-08-21T17:30:00Z"


def _bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _bootstrap(*, p8_price: int = 50, include_new_mid: bool = False) -> dict[str, object]:
    players = []
    for index, (position, price) in enumerate(zip(POSITIONS, PRICES, strict=True), start=1):
        if index == 8:
            price = p8_price
        players.append(
            {
                "id": index,
                "element_type": ELEMENT_TYPES[position],
                "team": index,
                "now_cost": price,
                "web_name": f"P{index}",
            }
        )
    teams = [{"id": index, "name": f"T{index}"} for index in range(1, 16)]
    if include_new_mid:
        players.append(
            {
                "id": 101,
                "element_type": 3,
                "team": 16,
                "now_cost": 50,
                "web_name": "New MID",
            }
        )
        teams.append({"id": 16, "name": "T16"})
    return {
        "elements": players,
        "teams": teams,
        "events": [
            {"id": 1, "deadline_time": DEADLINE},
            {"id": 2, "deadline_time": "2026-08-28T17:30:00Z"},
        ],
    }


def _picks(ids: list[int], *, gameweek: int, bank: int, transfers: int, cost: int) -> dict[str, object]:
    return {
        "picks": [
            {
                "element": player_id,
                "position": position,
                "is_captain": position == 1,
                "is_vice_captain": position == 2,
            }
            for position, player_id in enumerate(ids, start=1)
        ],
        "entry_history": {
            "event": gameweek,
            "bank": bank,
            "event_transfers": transfers,
            "event_transfers_cost": cost,
            "value": 1000,
        },
        "active_chip": None,
    }


def _manager_payloads(
    *,
    gameweek: int,
    ids: list[int],
    bank: int,
    history: list[dict[str, int]],
    transfers: list[dict[str, object]],
) -> dict[str, bytes]:
    base = f"{FPL_API_BASE}/entry/{ENTRY_ID}"
    return {
        f"{base}/": _bytes({"id": ENTRY_ID, "name": "Apex"}),
        f"{base}/history/": _bytes({"current": history, "chips": []}),
        f"{base}/transfers/": _bytes(transfers),
        f"{base}/event/{gameweek}/picks/": _bytes(
            _picks(
                ids,
                gameweek=gameweek,
                bank=bank,
                transfers=history[-1]["event_transfers"],
                cost=history[-1]["event_transfers_cost"],
            )
        ),
    }


class FixedClock:
    def __init__(self, stamp: datetime):
        self.stamp = stamp

    def now(self) -> datetime:
        return self.stamp


class MapTransport:
    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads
        self.calls: list[str] = []

    def get(self, url: str, *, params: dict[str, str]) -> HttpResponse:
        assert params == {}
        self.calls.append(url)
        return HttpResponse(
            status_code=200,
            body=self.payloads[url],
            headers={"Content-Type": "application/json"},
        )


def _seal_world(
    store: FileSystemArtifactStore,
    *,
    stamp: datetime,
    bootstrap: dict[str, object],
):
    return acquire_official_global_world(
        season="2026-2027",
        transport=MapTransport(
            {
                FPL_BOOTSTRAP_URL: _bytes(bootstrap),
                FPL_FIXTURES_URL: _bytes([]),
            }
        ),
        clock=FixedClock(stamp),
        store=store,
    )


def _seal_manager(
    store: FileSystemArtifactStore,
    *,
    stamp: datetime,
    gameweek: int,
    ids: list[int],
    bank: int,
    history: list[dict[str, int]],
    transfers: list[dict[str, object]],
):
    return acquire_official_manager_public_data(
        entry_id=ENTRY_ID,
        published_gameweek=gameweek,
        transport=MapTransport(
            _manager_payloads(
                gameweek=gameweek,
                ids=ids,
                bank=bank,
                history=history,
                transfers=transfers,
            )
        ),
        clock=FixedClock(stamp),
        store=store,
    )


def test_initial_basis_requires_real_pre_deadline_bootstrap_and_replays_offline(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    world = _seal_world(
        store,
        stamp=datetime(2026, 8, 21, 16, tzinfo=timezone.utc),
        bootstrap=_bootstrap(),
    )
    gw1 = _seal_manager(
        store,
        stamp=datetime(2026, 8, 21, 18, tzinfo=timezone.utc),
        gameweek=1,
        ids=list(range(1, 16)),
        bank=INITIAL_BANK,
        history=[{"event": 1, "event_transfers": 0, "event_transfers_cost": 0, "bank": INITIAL_BANK}],
        transfers=[],
    )
    stored = build_initial_manager_basis(
        pre_gw1_global_world_manifest_artifact_id=world.manifest_artifact_id,
        gw1_manager_public_manifest_artifact_id=gw1.manifest_artifact_id,
        ruleset=RULESET,
        store=store,
    )
    assert store.verify(stored.artifact_id)
    assert stored.basis.initial_bank_tenths == INITIAL_BANK
    assert stored.basis.purchase_prices()[OfficialPlayerId(8)] == 50
    replay = load_initial_manager_basis(stored.artifact_id, store=store)
    assert replay.basis_id == stored.basis.basis_id
    assert replay.player_ids() == stored.basis.player_ids()


def test_post_deadline_bootstrap_cannot_be_mislabeled_as_initial_purchase_basis(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    world = _seal_world(
        store,
        stamp=datetime(2026, 8, 21, 18, tzinfo=timezone.utc),
        bootstrap=_bootstrap(p8_price=54),
    )
    gw1 = _seal_manager(
        store,
        stamp=datetime(2026, 8, 21, 18, 5, tzinfo=timezone.utc),
        gameweek=1,
        ids=list(range(1, 16)),
        bank=INITIAL_BANK,
        history=[{"event": 1, "event_transfers": 0, "event_transfers_cost": 0, "bank": INITIAL_BANK}],
        transfers=[],
    )
    with pytest.raises(ValueError, match="captured before first deadline"):
        build_initial_manager_basis(
            pre_gw1_global_world_manifest_artifact_id=world.manifest_artifact_id,
            gw1_manager_public_manifest_artifact_id=gw1.manifest_artifact_id,
            ruleset=RULESET,
            store=store,
        )


def test_initial_basis_rejects_bank_that_does_not_reconcile_to_pre_gw1_prices(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    world = _seal_world(
        store,
        stamp=datetime(2026, 8, 21, 16, tzinfo=timezone.utc),
        bootstrap=_bootstrap(),
    )
    gw1 = _seal_manager(
        store,
        stamp=datetime(2026, 8, 21, 18, tzinfo=timezone.utc),
        gameweek=1,
        ids=list(range(1, 16)),
        bank=INITIAL_BANK + 1,
        history=[{"event": 1, "event_transfers": 0, "event_transfers_cost": 0, "bank": INITIAL_BANK + 1}],
        transfers=[],
    )
    with pytest.raises(ValueError, match="Official GW1 bank"):
        build_initial_manager_basis(
            pre_gw1_global_world_manifest_artifact_id=world.manifest_artifact_id,
            gw1_manager_public_manifest_artifact_id=gw1.manifest_artifact_id,
            ruleset=RULESET,
            store=store,
        )


def test_sealed_gw2_reconstruction_uses_official_sale_receipt_and_current_price_surface(
    tmp_path: Path,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    pre_world = _seal_world(
        store,
        stamp=datetime(2026, 8, 21, 16, tzinfo=timezone.utc),
        bootstrap=_bootstrap(),
    )
    gw1 = _seal_manager(
        store,
        stamp=datetime(2026, 8, 21, 18, tzinfo=timezone.utc),
        gameweek=1,
        ids=list(range(1, 16)),
        bank=INITIAL_BANK,
        history=[{"event": 1, "event_transfers": 0, "event_transfers_cost": 0, "bank": INITIAL_BANK}],
        transfers=[],
    )
    basis = build_initial_manager_basis(
        pre_gw1_global_world_manifest_artifact_id=pre_world.manifest_artifact_id,
        gw1_manager_public_manifest_artifact_id=gw1.manifest_artifact_id,
        ruleset=RULESET,
        store=store,
    )

    current_world = _seal_world(
        store,
        stamp=datetime(2026, 8, 28, 18, tzinfo=timezone.utc),
        bootstrap=_bootstrap(p8_price=52, include_new_mid=True),
    )
    ids = [101 if player_id == 8 else player_id for player_id in range(1, 16)]
    transfer_rows = [
        {
            "element_in": 101,
            "element_in_cost": 50,
            "element_out": 8,
            "element_out_cost": 51,
            "entry": ENTRY_ID,
            "event": 2,
            "time": "2026-08-25T12:00:00Z",
        }
    ]
    current_manager = _seal_manager(
        store,
        stamp=datetime(2026, 8, 28, 18, 1, tzinfo=timezone.utc),
        gameweek=2,
        ids=ids,
        bank=INITIAL_BANK + 1,
        history=[
            {"event": 1, "event_transfers": 0, "event_transfers_cost": 0, "bank": INITIAL_BANK},
            {"event": 2, "event_transfers": 1, "event_transfers_cost": 0, "bank": INITIAL_BANK + 1},
        ],
        transfers=transfer_rows,
    )
    rebuilt = reconstruct_manager_state_from_seals(
        current_global_world_manifest_artifact_id=current_world.manifest_artifact_id,
        current_manager_public_manifest_artifact_id=current_manager.manifest_artifact_id,
        initial_manager_basis_artifact_id=basis.artifact_id,
        ruleset=RULESET,
        store=store,
    )

    assert rebuilt.resolution.exact_deadline_snapshot
    assert rebuilt.resolution.state is not None
    assert rebuilt.resolution.historical_ledger is not None
    assert rebuilt.resolution.state.scope is ManagerStateScope.DEADLINE_SNAPSHOT
    assert rebuilt.resolution.state.bank_tenths == INITIAL_BANK + 1
    assert rebuilt.resolution.state.player(OfficialPlayerId(101)).purchase_basis_tenths == 50
    receipt = rebuilt.resolution.historical_ledger.receipts[0]
    assert receipt.realised_sale_tenths == 51
    assert receipt.outgoing_purchase_basis_tenths == 50
    assert rebuilt.resolution.state.transfer_ledger == ()
    assert rebuilt.historical_ledger_artifact_id is not None
    assert store.verify(rebuilt.historical_ledger_artifact_id)
    assert rebuilt.historical_ledger_artifact_id in rebuilt.resolution.state.provenance_artifact_ids


def test_basis_and_sealed_reconstruction_replay_apis_have_no_transport_or_clock_ports():
    basis_parameters = inspect.signature(load_initial_manager_basis).parameters
    reconstruct_parameters = inspect.signature(reconstruct_manager_state_from_seals).parameters
    assert set(basis_parameters) == {"artifact_id", "store"}
    assert "transport" not in reconstruct_parameters
    assert "clock" not in reconstruct_parameters
