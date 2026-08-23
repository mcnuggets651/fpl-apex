from __future__ import annotations

from dataclasses import fields
from pathlib import Path

import pytest

from apex_fpl.control.manager_state_reconstruction import (
    ManagerStateResolutionStatus,
    PublicChipRecord,
    PublicTransferRecord,
    reconstruct_public_deadline_state,
)
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.identity import OfficialPlayerId, OfficialPlayerIdentity
from apex_fpl.core.manager_state import ManagerStateIntegrityError, ManagerStateScope


ROOT = Path(__file__).resolve().parents[1]
RULESET = load_ruleset(ROOT / "config/rules/2026-2027.yaml")
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
PRICES = (40, 40, 45, 45, 45, 45, 45, 50, 50, 50, 50, 50, 55, 55, 55)


def _artifact(char: str) -> str:
    return "sha256:" + char * 64


def _initial_players() -> dict[OfficialPlayerId, OfficialPlayerIdentity]:
    return {
        OfficialPlayerId(index + 1): OfficialPlayerIdentity(
            player_id=OfficialPlayerId(index + 1),
            team_id=index + 1,
            position=POSITIONS[index],
            price_tenths=PRICES[index],
            display_name=f"P{index + 1}",
        )
        for index in range(15)
    }


def _initial_ids() -> tuple[OfficialPlayerId, ...]:
    return tuple(_initial_players())


def _initial_prices() -> dict[OfficialPlayerId, int]:
    return {
        player_id: player.price_tenths
        for player_id, player in _initial_players().items()
    }


def _initial_bank() -> int:
    return 1000 - sum(PRICES)


def test_public_transfer_contract_uses_official_realised_sale_not_invented_market_price():
    names = {field.name for field in fields(PublicTransferRecord)}
    assert "realised_sale_tenths" in names
    assert "outgoing_market_price_tenths" not in names


def test_no_transfer_public_gw1_reconstructs_exact_deadline_snapshot_not_current_state():
    players = _initial_players()
    resolution = reconstruct_public_deadline_state(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=1,
        published_squad_ids=_initial_ids(),
        published_bank_tenths=_initial_bank(),
        current_official=players,
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=(),
        event_transfer_counts={1: 0},
        event_transfer_costs={1: 0},
        chips=(),
        ruleset=RULESET,
        provenance_artifact_ids=(_artifact("a"), _artifact("b")),
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    assert resolution.status is ManagerStateResolutionStatus.EXACT_DEADLINE_SNAPSHOT
    assert resolution.exact_deadline_snapshot
    assert resolution.state is not None
    assert resolution.historical_ledger is not None
    assert resolution.historical_ledger.receipts == ()
    assert resolution.state.scope is ManagerStateScope.DEADLINE_SNAPSHOT
    assert resolution.state.gameweek == 2
    assert resolution.state.free_transfers == 1
    assert resolution.state.bank_tenths == _initial_bank()
    assert resolution.state.transfer_ledger == ()
    with pytest.raises(ManagerStateIntegrityError, match="not current exact"):
        resolution.state.require_decision_safe(ruleset=RULESET)


def test_public_transfer_reconstructs_basis_official_sale_bank_and_next_ft_exactly():
    current = _initial_players()
    del current[OfficialPlayerId(8)]
    current[OfficialPlayerId(101)] = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(101),
        team_id=16,
        position="MID",
        price_tenths=50,
        display_name="New MID",
    )
    published_ids = tuple(
        OfficialPlayerId(101) if player_id == OfficialPlayerId(8) else player_id
        for player_id in _initial_ids()
    )
    transfer = PublicTransferRecord(
        transfer_id="gw2-t1",
        gameweek=2,
        sequence=1,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player_id=OfficialPlayerId(101),
        realised_sale_tenths=51,
        incoming_purchase_tenths=50,
        source_artifact_id=_artifact("c"),
    )
    resolution = reconstruct_public_deadline_state(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=2,
        published_squad_ids=published_ids,
        published_bank_tenths=_initial_bank() + 1,
        current_official=current,
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=(transfer,),
        event_transfer_counts={1: 0, 2: 1},
        event_transfer_costs={1: 0, 2: 0},
        chips=(),
        ruleset=RULESET,
        provenance_artifact_ids=(_artifact("d"), _artifact("e"), _artifact("c")),
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    assert resolution.exact_deadline_snapshot
    assert resolution.state is not None
    assert resolution.historical_ledger is not None
    assert resolution.state.gameweek == 3
    assert resolution.state.free_transfers == 1
    assert resolution.state.bank_tenths == _initial_bank() + 1
    assert resolution.state.player(OfficialPlayerId(101)).purchase_basis_tenths == 50
    receipt = resolution.historical_ledger.receipts[0]
    assert receipt.realised_sale_tenths == 51
    assert receipt.hit_points == 0
    assert receipt.outgoing_purchase_basis_tenths == 50
    assert resolution.state.transfer_ledger == ()


def test_public_sell_and_rebuy_resets_basis_and_records_exact_hit():
    current = _initial_players()
    current[OfficialPlayerId(8)] = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(8),
        team_id=8,
        position="MID",
        price_tenths=54,
        display_name="P8",
    )
    transfers = (
        PublicTransferRecord(
            transfer_id="gw2-sell",
            gameweek=2,
            sequence=1,
            outgoing_player_id=OfficialPlayerId(8),
            incoming_player_id=OfficialPlayerId(101),
            realised_sale_tenths=52,
            incoming_purchase_tenths=50,
            source_artifact_id=_artifact("f"),
        ),
        PublicTransferRecord(
            transfer_id="gw2-rebuy",
            gameweek=2,
            sequence=2,
            outgoing_player_id=OfficialPlayerId(101),
            incoming_player_id=OfficialPlayerId(8),
            realised_sale_tenths=50,
            incoming_purchase_tenths=54,
            source_artifact_id=_artifact("1"),
        ),
    )
    resolution = reconstruct_public_deadline_state(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=2,
        published_squad_ids=_initial_ids(),
        published_bank_tenths=_initial_bank() - 2,
        current_official=current,
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=transfers,
        event_transfer_counts={1: 0, 2: 2},
        event_transfer_costs={1: 0, 2: 4},
        chips=(),
        ruleset=RULESET,
        provenance_artifact_ids=(
            _artifact("2"),
            _artifact("3"),
            _artifact("f"),
            _artifact("1"),
        ),
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    assert resolution.exact_deadline_snapshot
    assert resolution.state is not None
    assert resolution.historical_ledger is not None
    owned = resolution.state.player(OfficialPlayerId(8))
    assert owned.purchase_basis_tenths == 54
    assert owned.selling_price_tenths == 54
    assert [row.hit_points for row in resolution.historical_ledger.receipts] == [0, 4]
    assert resolution.state.free_transfers == 1


def test_incomplete_initial_capture_or_transfer_history_blocks_state_construction():
    common = dict(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=1,
        published_squad_ids=_initial_ids(),
        published_bank_tenths=_initial_bank(),
        current_official=_initial_players(),
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=(),
        event_transfer_counts={1: 0},
        event_transfer_costs={1: 0},
        chips=(),
        ruleset=RULESET,
        provenance_artifact_ids=(_artifact("4"),),
    )
    no_prices = reconstruct_public_deadline_state(
        **common,
        transfer_history_complete=True,
        initial_price_capture_complete=False,
    )
    assert no_prices.status is ManagerStateResolutionStatus.INCOMPLETE
    assert no_prices.state is None
    assert any("pre-GW1" in blocker for blocker in no_prices.blockers)

    no_history = reconstruct_public_deadline_state(
        **common,
        transfer_history_complete=False,
        initial_price_capture_complete=True,
    )
    assert no_history.status is ManagerStateResolutionStatus.INCOMPLETE
    assert no_history.state is None
    assert any("transfer history" in blocker for blocker in no_history.blockers)


def test_missing_transfer_row_and_bank_mismatch_fail_closed():
    current = _initial_players()
    missing_row = reconstruct_public_deadline_state(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=2,
        published_squad_ids=_initial_ids(),
        published_bank_tenths=_initial_bank(),
        current_official=current,
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=(),
        event_transfer_counts={1: 0, 2: 1},
        event_transfer_costs={1: 0, 2: 0},
        chips=(),
        ruleset=RULESET,
        provenance_artifact_ids=(_artifact("5"),),
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    assert missing_row.status is ManagerStateResolutionStatus.INCOMPLETE
    assert any("receipt rows" in blocker for blocker in missing_row.blockers)

    bad_bank = reconstruct_public_deadline_state(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=1,
        published_squad_ids=_initial_ids(),
        published_bank_tenths=_initial_bank() + 1,
        current_official=current,
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=(),
        event_transfer_counts={1: 0},
        event_transfer_costs={1: 0},
        chips=(),
        ruleset=RULESET,
        provenance_artifact_ids=(_artifact("6"),),
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    assert bad_bank.status is ManagerStateResolutionStatus.INVALID
    assert any("bank" in blocker for blocker in bad_bank.blockers)


def test_public_transfer_cost_mismatch_and_future_chip_fail_closed():
    current = _initial_players()
    transfers = (
        PublicTransferRecord(
            transfer_id="gw2-t1",
            gameweek=2,
            sequence=1,
            outgoing_player_id=OfficialPlayerId(8),
            incoming_player_id=OfficialPlayerId(101),
            realised_sale_tenths=50,
            incoming_purchase_tenths=50,
            source_artifact_id=_artifact("7"),
        ),
        PublicTransferRecord(
            transfer_id="gw2-t2",
            gameweek=2,
            sequence=2,
            outgoing_player_id=OfficialPlayerId(9),
            incoming_player_id=OfficialPlayerId(102),
            realised_sale_tenths=50,
            incoming_purchase_tenths=50,
            source_artifact_id=_artifact("8"),
        ),
    )
    current.pop(OfficialPlayerId(8))
    current.pop(OfficialPlayerId(9))
    current[OfficialPlayerId(101)] = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(101),
        team_id=16,
        position="MID",
        price_tenths=50,
        display_name="N1",
    )
    current[OfficialPlayerId(102)] = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(102),
        team_id=17,
        position="MID",
        price_tenths=50,
        display_name="N2",
    )
    published_ids = tuple(
        OfficialPlayerId(101)
        if item == OfficialPlayerId(8)
        else OfficialPlayerId(102)
        if item == OfficialPlayerId(9)
        else item
        for item in _initial_ids()
    )
    bad_cost = reconstruct_public_deadline_state(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=2,
        published_squad_ids=published_ids,
        published_bank_tenths=_initial_bank(),
        current_official=current,
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=transfers,
        event_transfer_counts={1: 0, 2: 2},
        event_transfer_costs={1: 0, 2: 0},
        chips=(),
        ruleset=RULESET,
        provenance_artifact_ids=(_artifact("9"), _artifact("7"), _artifact("8")),
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    assert bad_cost.status is ManagerStateResolutionStatus.INVALID
    assert any("event_transfers_cost" in blocker for blocker in bad_cost.blockers)

    future_chip = reconstruct_public_deadline_state(
        season="2026-2027",
        entry_id=63984,
        published_gameweek=1,
        published_squad_ids=_initial_ids(),
        published_bank_tenths=_initial_bank(),
        current_official=_initial_players(),
        initial_squad_ids=_initial_ids(),
        initial_purchase_prices_tenths=_initial_prices(),
        transfers=(),
        event_transfer_counts={1: 0},
        event_transfer_costs={1: 0},
        chips=(
            PublicChipRecord(
                chip="BENCH_BOOST",
                gameweek=2,
                source_artifact_id=_artifact("a"),
            ),
        ),
        ruleset=RULESET,
        provenance_artifact_ids=(_artifact("b"),),
        transfer_history_complete=True,
        initial_price_capture_complete=True,
    )
    assert future_chip.status is ManagerStateResolutionStatus.INVALID
    assert any("future Gameweek" in blocker for blocker in future_chip.blockers)
