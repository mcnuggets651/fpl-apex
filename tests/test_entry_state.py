from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from apex_fpl.data.entry import (
    OfficialEntryClient,
    PublicEntryState,
    derive_next_free_transfers,
)
from apex_fpl.services.team_state import _public_selling_prices, _selling_price


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads

    def get_json(self, url, key, force=False, params=None):
        for needle, payload in self.payloads.items():
            if needle in url:
                if isinstance(payload, Exception):
                    raise payload
                return payload
        raise RuntimeError(f"unexpected URL: {url}")


def test_free_transfer_roll_replays_history():
    history = {
        "current": [
            {"event": 1, "event_transfers": 0},
            {"event": 2, "event_transfers": 1},
            {"event": 3, "event_transfers": 0},
        ],
        "chips": [],
    }
    # GW1 awards the first FT for GW2; use it in GW2; roll once after GW3.
    assert derive_next_free_transfers(history, 3) == 2


def test_wildcard_preserves_banked_transfers():
    history = {
        "current": [
            {"event": 1, "event_transfers": 0},
            {"event": 2, "event_transfers": 0},
            {"event": 3, "event_transfers": 8},
        ],
        "chips": [{"event": 3, "name": "wildcard"}],
    }
    assert derive_next_free_transfers(history, 3) == 2


def test_gw1_awards_one_free_transfer_for_gw2():
    history = {"current": [{"event": 1, "event_transfers": 0}], "chips": []}
    assert derive_next_free_transfers(history, 1) == 1


def test_2025_26_gw16_afcon_top_up_is_season_specific():
    history = {
        "current": [
            {"event": gw, "event_transfers": 1}
            for gw in range(1, 16)
        ],
        "chips": [],
    }
    assert derive_next_free_transfers(history, 15, season="2025-26") == 5
    assert derive_next_free_transfers(history, 15, season="2026-2027") == 1


def _published_payloads(*, transfers=()):
    picks = [
        {
            "element": i,
            "is_captain": i == 1,
            "is_vice_captain": i == 2,
        }
        for i in range(1, 16)
    ]
    return {
        "/entry/63984/transfers/": list(transfers),
        "/entry/63984/history/": {
            "current": [{"event": 1, "event_transfers": 0}],
            "chips": [],
        },
        "/entry/63984/event/1/picks/": {
            "picks": picks,
            "entry_history": {
                "event": 1,
                "event_transfers": 0,
                "bank": 5,
                "value": 1005,
            },
            "active_chip": None,
        },
        "/entry/63984/": {
            "id": 63984,
            "name": "Apex XI",
            "player_first_name": "Test",
            "player_last_name": "Manager",
            "last_deadline_bank": 5,
        },
    }


def _events():
    return pd.DataFrame(
        [
            {"id": 1, "deadline_time": "2026-08-21T17:30:00Z"},
            {"id": 2, "deadline_time": "2026-08-28T17:30:00Z"},
        ]
    )


def test_latest_public_state_reads_published_picks():
    state = OfficialEntryClient(FakeHttp(_published_payloads()), 63984).latest_public_state(
        _events(),
        now=datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
    )
    assert state is not None
    assert state.entry_id == 63984
    assert state.published_gw == 1
    assert state.squad == set(range(1, 16))
    assert state.bank == 0.5
    assert state.team_value == 100.5
    assert state.free_transfers == 1
    assert state.captain_id == 1
    assert state.vice_captain_id == 2
    assert state.transfers_complete is True


def test_public_state_marks_transfer_ledger_incomplete_without_hiding_the_15():
    payloads = _published_payloads()
    payloads["/entry/63984/transfers/"] = RuntimeError("temporary transfer endpoint failure")
    state = OfficialEntryClient(FakeHttp(payloads), 63984).latest_public_state(
        _events(),
        now=datetime(2026, 8, 22, 9, tzinfo=timezone.utc),
    )
    assert state is not None
    assert state.squad == set(range(1, 16))
    assert state.transfers == []
    assert state.transfers_complete is False


def test_before_first_deadline_has_no_public_squad():
    http = FakeHttp(
        {
            "/entry/63984/transfers/": [],
            "/entry/63984/history/": {"current": [], "chips": []},
            "/entry/63984/": {"id": 63984, "name": "Apex XI"},
        }
    )
    events = pd.DataFrame(
        [{"id": 1, "deadline_time": "2026-08-21T17:30:00Z"}]
    )
    state = OfficialEntryClient(http, 63984).latest_public_state(
        events,
        now=datetime(2026, 8, 21, 8, tzinfo=timezone.utc),
    )
    assert state is None


def test_fpl_selling_price_uses_half_profit_rule():
    assert _selling_price(7.0, 7.4) == 7.2
    assert _selling_price(7.0, 7.3) == 7.1
    assert _selling_price(7.0, 6.8) == 6.8


def _public_state(
    *,
    published_gw: int,
    transfers: list[dict] | None = None,
    transfers_complete: bool = True,
) -> PublicEntryState:
    return PublicEntryState(
        entry_id=63984,
        entry_name="Apex XI",
        manager_name="Test Manager",
        published_gw=published_gw,
        squad={1},
        bank=0.5,
        free_transfers=1,
        team_value=100.5,
        captain_id=1,
        vice_captain_id=None,
        active_chip=None,
        transfers=list(transfers or []),
        transfers_complete=transfers_complete,
        chips_used=[],
    )


def test_gw1_selling_price_is_exact_from_official_cost_change_start_without_cache():
    players = pd.DataFrame(
        [{"player_id": 1, "price": 7.4, "cost_change_start": 4}]
    )
    selling, exact = _public_selling_prices(
        _public_state(published_gw=1, transfers_complete=False),
        players,
        None,
    )
    assert exact is True
    assert selling == {1: 7.2}


def test_later_transferred_in_player_uses_latest_public_purchase_cost():
    players = pd.DataFrame(
        [{"player_id": 1, "price": 7.6, "cost_change_start": 6}]
    )
    selling, exact = _public_selling_prices(
        _public_state(
            published_gw=2,
            transfers=[{"event": 2, "element_in": 1, "element_in_cost": 72}],
            transfers_complete=True,
        ),
        players,
        None,
    )
    assert exact is True
    assert selling == {1: 7.4}


def test_later_public_squad_fails_exact_pricing_when_transfer_ledger_is_unavailable():
    players = pd.DataFrame(
        [{"player_id": 1, "price": 7.6, "cost_change_start": 6}]
    )
    selling, exact = _public_selling_prices(
        _public_state(published_gw=2, transfers_complete=False),
        players,
        None,
    )
    assert exact is False
    assert selling == {1: 7.6}
