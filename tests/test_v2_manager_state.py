from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from apex_fpl.control.artifact_store import FileSystemArtifactStore
from apex_fpl.control.manager_state_override import store_and_load_manager_state_override
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.identity import OfficialPlayerId, OfficialPlayerIdentity
from apex_fpl.core.manager_state import (
    CurrentStateAttestation,
    ManagerState,
    ManagerStateIntegrityError,
    ManagerStateScope,
    apply_permanent_transfer,
    advance_deadline,
    attest_deadline_snapshot_current,
    calculate_selling_price_tenths,
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
PRICES = (40, 40, 45, 45, 45, 45, 45, 50, 50, 50, 50, 50, 55, 55, 55)


def _artifact(seed: str) -> str:
    return "sha256:" + (seed.encode("utf-8").hex() + "0" * 64)[:64]


def _identities() -> tuple[OfficialPlayerIdentity, ...]:
    return tuple(
        OfficialPlayerIdentity(
            player_id=OfficialPlayerId(index + 1),
            team_id=index + 1,
            position=POSITIONS[index],
            price_tenths=PRICES[index],
            display_name=f"P{index + 1}",
        )
        for index in range(15)
    )


def _state(
    *,
    scope: ManagerStateScope = ManagerStateScope.CURRENT_EXACT,
    free_transfers: int = 1,
    bank_tenths: int = 20,
) -> ManagerState:
    squad = tuple(
        owned_player_from_official(
            player,
            purchase_basis_tenths=player.price_tenths,
            current_price_tenths=player.price_tenths,
            ruleset=RULESET,
        )
        for player in _identities()
    )
    return ManagerState(
        season="2026-2027",
        entry_id=63984,
        gameweek=2,
        ruleset_id=RULESET.ruleset_id,
        scope=scope,
        bank_tenths=bank_tenths,
        free_transfers=free_transfers,
        squad=squad,
        provenance_artifact_ids=(_artifact("seed"),),
    )


def test_selling_price_boundaries_are_exact_integer_tenths():
    assert calculate_selling_price_tenths(50, 49, ruleset=RULESET) == 49
    assert calculate_selling_price_tenths(50, 50, ruleset=RULESET) == 50
    assert calculate_selling_price_tenths(50, 51, ruleset=RULESET) == 50
    assert calculate_selling_price_tenths(50, 52, ruleset=RULESET) == 51
    assert calculate_selling_price_tenths(50, 53, ruleset=RULESET) == 51
    assert calculate_selling_price_tenths(50, 54, ruleset=RULESET) == 52


def test_current_exact_state_accepts_zero_free_transfers_and_rejects_unproven_scope():
    state = _state(free_transfers=0)
    assert state.require_decision_safe(ruleset=RULESET) is state

    snapshot = _state(scope=ManagerStateScope.DEADLINE_SNAPSHOT)
    with pytest.raises(ManagerStateIntegrityError, match="not current exact"):
        snapshot.require_decision_safe(ruleset=RULESET)


def test_manager_state_id_changes_with_financial_state_and_price_surface():
    state = _state()
    changed_bank = _state(bank_tenths=21)
    assert changed_bank.manager_state_id != state.manager_state_id

    repriced = reprice_manager_state(
        state,
        current_prices_tenths={
            row.player_id: row.current_price_tenths
            + (4 if int(row.player_id) == 8 else 0)
            for row in state.squad
        },
        ruleset=RULESET,
        source_artifact_id=_artifact("prices"),
    )
    assert repriced.manager_state_id != state.manager_state_id
    player = repriced.player(OfficialPlayerId(8))
    assert player.purchase_basis_tenths == 50
    assert player.current_price_tenths == 54
    assert player.selling_price_tenths == 52


def test_normal_transfers_consume_ft_then_charge_exact_hit_once():
    state = _state(free_transfers=1, bank_tenths=20)
    incoming_mid = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(101),
        team_id=16,
        position="MID",
        price_tenths=50,
        display_name="New MID",
    )
    first = apply_permanent_transfer(
        state,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player=incoming_mid,
        ruleset=RULESET,
        event_id="gw2-1",
        source_artifact_id=_artifact("tx1"),
    )
    assert first.event.hit_points == 0
    assert first.state.free_transfers == 0

    second_mid = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(102),
        team_id=17,
        position="MID",
        price_tenths=50,
        display_name="Second MID",
    )
    second = apply_permanent_transfer(
        first.state,
        outgoing_player_id=OfficialPlayerId(9),
        incoming_player=second_mid,
        ruleset=RULESET,
        event_id="gw2-2",
        source_artifact_id=_artifact("tx2"),
    )
    assert second.event.hit_points == 4
    assert second.state.free_transfers == 0
    assert [event.hit_points for event in second.state.transfer_ledger] == [0, 4]


def test_wildcard_permanent_transfers_preserve_ft_and_never_charge_hit():
    state = _state(free_transfers=4)
    incoming = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(103),
        team_id=16,
        position="MID",
        price_tenths=50,
        display_name="Wildcard MID",
    )
    transition = apply_permanent_transfer(
        state,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player=incoming,
        ruleset=RULESET,
        event_id="wc-1",
        source_artifact_id=_artifact("wc"),
        wildcard_active=True,
    )
    assert transition.event.mode == "WILDCARD"
    assert transition.event.hit_points == 0
    assert transition.state.free_transfers == 4


def test_rebuy_resets_purchase_basis_and_future_selling_price():
    state = reprice_manager_state(
        _state(free_transfers=1, bank_tenths=20),
        current_prices_tenths={
            row.player_id: row.current_price_tenths
            + (4 if int(row.player_id) == 8 else 0)
            for row in _state().squad
        },
        ruleset=RULESET,
        source_artifact_id=_artifact("rise"),
    )
    replacement = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(104),
        team_id=16,
        position="MID",
        price_tenths=50,
        display_name="Replacement",
    )
    sold = apply_permanent_transfer(
        state,
        outgoing_player_id=OfficialPlayerId(8),
        incoming_player=replacement,
        ruleset=RULESET,
        event_id="sell-original",
        source_artifact_id=_artifact("sell"),
    )
    assert sold.event.realised_sale_tenths == 52

    rebuy_identity = OfficialPlayerIdentity(
        player_id=OfficialPlayerId(8),
        team_id=8,
        position="MID",
        price_tenths=54,
        display_name="P8",
    )
    rebought = apply_permanent_transfer(
        sold.state,
        outgoing_player_id=OfficialPlayerId(104),
        incoming_player=rebuy_identity,
        ruleset=RULESET,
        event_id="rebuy-original",
        source_artifact_id=_artifact("rebuy"),
    )
    owned = rebought.state.player(OfficialPlayerId(8))
    assert owned.purchase_basis_tenths == 54
    assert owned.current_price_tenths == 54
    assert owned.selling_price_tenths == 54


def test_deadline_ft_transition_rolls_normally_but_wc_and_fh_preserve_bank():
    normal = advance_deadline(
        _state(free_transfers=4),
        ruleset=RULESET,
        source_artifact_id=_artifact("normal-deadline"),
    )
    assert normal.gameweek == 3
    assert normal.free_transfers == 5

    wildcard = advance_deadline(
        _state(free_transfers=4),
        ruleset=RULESET,
        source_artifact_id=_artifact("wc-deadline"),
        active_chip="WILDCARD",
    )
    assert wildcard.free_transfers == 4
    assert wildcard.chips_used[-1].chip == "WILDCARD"

    free_hit = advance_deadline(
        _state(free_transfers=4),
        ruleset=RULESET,
        source_artifact_id=_artifact("fh-deadline"),
        active_chip="FREE_HIT",
    )
    assert free_hit.free_transfers == 4
    assert free_hit.player_ids == _state(free_transfers=4).player_ids


def test_deadline_snapshot_needs_scoped_unexpired_attestation_to_become_current():
    snapshot = _state(scope=ManagerStateScope.DEADLINE_SNAPSHOT)
    attestation = CurrentStateAttestation(
        author="manager",
        created_at="2026-08-23T20:00:00+00:00",
        expires_at="2026-08-23T22:00:00+00:00",
        gameweek=2,
        confirms_no_unrecorded_transfers=True,
        source_artifact_id=_artifact("attestation"),
    )
    current = attest_deadline_snapshot_current(
        snapshot,
        attestation=attestation,
        observed_at="2026-08-23T21:00:00+00:00",
        ruleset=RULESET,
    )
    assert current.scope is ManagerStateScope.CURRENT_EXACT
    current.require_decision_safe(ruleset=RULESET)

    with pytest.raises(ManagerStateIntegrityError, match="not valid"):
        attest_deadline_snapshot_current(
            snapshot,
            attestation=attestation,
            observed_at="2026-08-24T00:00:00+00:00",
            ruleset=RULESET,
        )


def _stored_evidence(store: FileSystemArtifactStore) -> tuple[str, str]:
    official = store.put_bytes(
        b"official-current-state",
        schema_name="fixture-official",
        schema_version="1",
    )
    ledger = store.put_bytes(
        b"complete-private-ledger",
        schema_name="fixture-ledger",
        schema_version="1",
    )
    return official.artifact_id, ledger.artifact_id


def _override_payload(
    state: ManagerState,
    *,
    source_artifact_ids: tuple[str, ...],
) -> dict[str, object]:
    return {
        "schema_name": "apex-manager-state-override",
        "schema_version": 1,
        "metadata": {
            "author": "manager",
            "reason": "record private post-deadline state exactly",
            "created_at": "2026-08-23T20:00:00+00:00",
            "expires_at": "2026-08-23T22:00:00+00:00",
            "current_state_confirmed": True,
        },
        "state": {
            "season": state.season,
            "entry_id": state.entry_id,
            "gameweek": state.gameweek,
            "ruleset_id": str(state.ruleset_id),
            "bank_tenths": state.bank_tenths,
            "free_transfers": state.free_transfers,
            "squad": [row.as_dict() for row in state.squad],
            "chips_used": [row.as_dict() for row in state.chips_used],
            "transfer_ledger": [row.as_dict() for row in state.transfer_ledger],
            "transfer_ledger_complete": True,
            "source_artifact_ids": list(source_artifact_ids),
        },
    }


def test_full_override_is_immutable_provenance_and_partial_override_fails(
    tmp_path: Path,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    source_ids = _stored_evidence(store)
    payload = _override_payload(_state(), source_artifact_ids=source_ids)
    content = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    loaded = store_and_load_manager_state_override(
        content,
        store=store,
        ruleset=RULESET,
        observed_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
    )
    assert store.verify(loaded.override_artifact_id)
    assert loaded.override_artifact_id in loaded.state.provenance_artifact_ids
    loaded.state.require_decision_safe(ruleset=RULESET)

    partial = _override_payload(_state(), source_artifact_ids=source_ids)
    del partial["state"]["squad"][0]["selling_price_tenths"]
    with pytest.raises(ManagerStateIntegrityError, match="missing fields"):
        store_and_load_manager_state_override(
            json.dumps(partial).encode(),
            store=store,
            ruleset=RULESET,
            observed_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
        )


def test_override_with_wrong_selling_price_or_expiry_fails_closed(tmp_path: Path):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    source_ids = _stored_evidence(store)
    wrong = _override_payload(_state(), source_artifact_ids=source_ids)
    wrong["state"]["squad"][7]["selling_price_tenths"] += 1
    with pytest.raises(ManagerStateIntegrityError, match="selling price"):
        store_and_load_manager_state_override(
            json.dumps(wrong).encode(),
            store=store,
            ruleset=RULESET,
            observed_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
        )

    expired = _override_payload(_state(), source_artifact_ids=source_ids)
    expired["metadata"]["expires_at"] = "2026-08-23T20:30:00+00:00"
    with pytest.raises(ManagerStateIntegrityError, match="validity window"):
        store_and_load_manager_state_override(
            json.dumps(expired).encode(),
            store=store,
            ruleset=RULESET,
            observed_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
        )


def test_override_requires_complete_ledger_current_confirmation_and_real_sources(
    tmp_path: Path,
):
    store = FileSystemArtifactStore(tmp_path / "artifacts")
    source_ids = _stored_evidence(store)

    incomplete = _override_payload(_state(), source_artifact_ids=source_ids)
    incomplete["state"]["transfer_ledger_complete"] = False
    with pytest.raises(ManagerStateIntegrityError, match="transfer_ledger_complete"):
        store_and_load_manager_state_override(
            json.dumps(incomplete).encode(),
            store=store,
            ruleset=RULESET,
            observed_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
        )

    unconfirmed = _override_payload(_state(), source_artifact_ids=source_ids)
    unconfirmed["metadata"]["current_state_confirmed"] = False
    with pytest.raises(ManagerStateIntegrityError, match="current_state_confirmed"):
        store_and_load_manager_state_override(
            json.dumps(unconfirmed).encode(),
            store=store,
            ruleset=RULESET,
            observed_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
        )

    missing_source = _override_payload(
        _state(),
        source_artifact_ids=("sha256:" + "f" * 64,),
    )
    with pytest.raises(ManagerStateIntegrityError, match="missing or corrupt"):
        store_and_load_manager_state_override(
            json.dumps(missing_source).encode(),
            store=store,
            ruleset=RULESET,
            observed_at=datetime(2026, 8, 23, 21, tzinfo=timezone.utc),
        )
