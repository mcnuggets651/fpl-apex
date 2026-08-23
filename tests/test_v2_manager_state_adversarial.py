from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.identity import OfficialPlayerId, OfficialPlayerIdentity
from apex_fpl.core.manager_state import (
    ManagerState,
    ManagerStateIntegrityError,
    ManagerStateScope,
    TransferLedgerEvent,
    advance_deadline,
    apply_permanent_transfer,
    owned_player_from_official,
    reprice_manager_state,
)


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


def _artifact(char: str) -> str:
    return "sha256:" + char * 64


def _state(*, free_transfers: int = 1) -> ManagerState:
    players = tuple(
        OfficialPlayerIdentity(
            player_id=OfficialPlayerId(index + 1),
            team_id=index + 1,
            position=POSITIONS[index],
            price_tenths=40 + index,
            display_name=f"P{index + 1}",
        )
        for index in range(15)
    )
    squad = tuple(
        owned_player_from_official(
            player,
            purchase_basis_tenths=player.price_tenths,
            current_price_tenths=player.price_tenths,
            ruleset=RULESET,
        )
        for player in players
    )
    return ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=RULESET.ruleset_id,
        scope=ManagerStateScope.CURRENT_EXACT,
        bank_tenths=50,
        free_transfers=free_transfers,
        squad=squad,
        provenance_artifact_ids=(_artifact("a"),),
    )


def test_existing_team_market_value_may_exceed_100m_without_becoming_illegal():
    state = _state()
    repriced = reprice_manager_state(
        state,
        current_prices_tenths={
            row.player_id: row.current_price_tenths + 40 for row in state.squad
        },
        ruleset=RULESET,
        source_artifact_id=_artifact("b"),
    )
    assert sum(row.current_price_tenths for row in repriced.squad) > 1000
    repriced.require_decision_safe(ruleset=RULESET)


def test_initial_squad_validation_still_enforces_100m_by_default():
    state = _state()
    errors = RULESET.validate_squad(
        positions=(row.position for row in state.squad),
        club_ids=(row.team_id for row in state.squad),
        prices_tenths=(100 for _ in state.squad),
    )
    assert "squad exceeds official budget" in errors


def test_tampered_transfer_ledger_bank_hit_and_selling_values_fail_closed():
    state = _state(free_transfers=0)
    incoming = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(101),
        team_id=16,
        position="MID",
        price_tenths=47,
        display_name="Incoming",
    )
    transition = apply_permanent_transfer(
        state,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player=incoming,
        ruleset=RULESET,
        event_id="t1",
        source_artifact_id=_artifact("c"),
    )
    event = transition.event

    bad_bank = replace(event, bank_after_tenths=event.bank_after_tenths + 1)
    state_bad_bank = replace(
        transition.state,
        bank_tenths=bad_bank.bank_after_tenths,
        transfer_ledger=(bad_bank,),
    )
    with pytest.raises(ManagerStateIntegrityError, match="bank equation"):
        state_bad_bank.require_decision_safe(ruleset=RULESET)

    bad_hit = replace(event, hit_points=0)
    state_bad_hit = replace(transition.state, transfer_ledger=(bad_hit,))
    with pytest.raises(ManagerStateIntegrityError, match="hit"):
        state_bad_hit.require_decision_safe(ruleset=RULESET)

    bad_sale = replace(event, realised_sale_tenths=event.realised_sale_tenths + 1)
    state_bad_sale = replace(
        transition.state,
        bank_tenths=transition.state.bank_tenths + 1,
        transfer_ledger=(bad_sale,),
    )
    with pytest.raises(ManagerStateIntegrityError, match="realised sale"):
        state_bad_sale.require_decision_safe(ruleset=RULESET)


def test_transfer_ledger_sequence_and_financial_chain_are_enforced():
    state = _state(free_transfers=2)
    first = apply_permanent_transfer(
        state,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player=OfficialPlayerIdentity(
            player_id=OfficialPlayerId(101),
            team_id=16,
            position="MID",
            price_tenths=47,
            display_name="A",
        ),
        ruleset=RULESET,
        event_id="t1",
        source_artifact_id=_artifact("d"),
    )
    second = apply_permanent_transfer(
        first.state,
        outgoing_player_id=OfficialPlayerId(9),
        incoming_player=OfficialPlayerIdentity(
            player_id=OfficialPlayerId(102),
            team_id=17,
            position="MID",
            price_tenths=48,
            display_name="B",
        ),
        ruleset=RULESET,
        event_id="t2",
        source_artifact_id=_artifact("e"),
    )
    broken_second = replace(
        second.event,
        bank_before_tenths=second.event.bank_before_tenths + 1,
        bank_after_tenths=second.event.bank_after_tenths + 1,
    )
    broken = replace(
        second.state,
        bank_tenths=broken_second.bank_after_tenths,
        transfer_ledger=(first.event, broken_second),
    )
    with pytest.raises(ManagerStateIntegrityError, match="bank discontinuity"):
        broken.require_decision_safe(ruleset=RULESET)


def test_wildcard_cannot_retroactively_erase_normal_transfer_history():
    state = _state(free_transfers=1)
    normal = apply_permanent_transfer(
        state,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player=OfficialPlayerIdentity(
            player_id=OfficialPlayerId(101),
            team_id=16,
            position="MID",
            price_tenths=47,
            display_name="A",
        ),
        ruleset=RULESET,
        event_id="normal",
        source_artifact_id=_artifact("f"),
    )
    with pytest.raises(ManagerStateIntegrityError, match="retroactively"):
        apply_permanent_transfer(
            normal.state,
            outgoing_player_id=OfficialPlayerId(9),
            incoming_player=OfficialPlayerIdentity(
                player_id=OfficialPlayerId(102),
                team_id=17,
                position="MID",
                price_tenths=48,
                display_name="B",
            ),
            ruleset=RULESET,
            event_id="wc-late",
            source_artifact_id=_artifact("1"),
            wildcard_active=True,
        )
    with pytest.raises(ManagerStateIntegrityError, match="Wildcard cannot certify"):
        advance_deadline(
            normal.state,
            ruleset=RULESET,
            source_artifact_id=_artifact("2"),
            active_chip="WILDCARD",
        )


def test_free_hit_rejects_permanent_transfer_events_in_same_window():
    state = _state(free_transfers=1)
    normal = apply_permanent_transfer(
        state,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player=OfficialPlayerIdentity(
            player_id=OfficialPlayerId(101),
            team_id=16,
            position="MID",
            price_tenths=47,
            display_name="A",
        ),
        ruleset=RULESET,
        event_id="normal",
        source_artifact_id=_artifact("3"),
    )
    with pytest.raises(ManagerStateIntegrityError, match="temporary squad"):
        advance_deadline(
            normal.state,
            ruleset=RULESET,
            source_artifact_id=_artifact("4"),
            active_chip="FREE_HIT",
        )


def test_transfer_event_with_invalid_artifact_provenance_is_rejected():
    with pytest.raises(ManagerStateIntegrityError, match="artifact"):
        TransferLedgerEvent(
            event_id="bad",
            sequence=1,
            gameweek=2,
            outgoing_player_id=OfficialPlayerId(1),
            incoming_player_id=OfficialPlayerId(2),
            outgoing_purchase_basis_tenths=40,
            outgoing_current_price_tenths=40,
            realised_sale_tenths=40,
            incoming_purchase_tenths=40,
            bank_before_tenths=0,
            bank_after_tenths=0,
            free_transfers_before=1,
            free_transfers_after=0,
            hit_points=0,
            mode="NORMAL",
            source_artifact_id="not-an-artifact",
        )
