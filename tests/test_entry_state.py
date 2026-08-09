from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from apex_fpl.data.entry import OfficialEntryClient, derive_next_free_transfers
from apex_fpl.services.team_state import _selling_price


class FakeHttp:
    def __init__(self, payloads):
        self.payloads = payloads

    def get_json(self, url, key, force=False, params=None):
        for needle, payload in self.payloads.items():
            if needle in url:
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


def test_latest_public_state_reads_published_picks():
    picks = [
        {
            "element": i,
            "is_captain": i == 1,
            "is_vice_captain": i == 2,
        }
        for i in range(1, 16)
    ]
    http = FakeHttp(
        {
            "/entry/63984/transfers/": [],
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
    )
    events = pd.DataFrame(
        [
            {"id": 1, "deadline_time": "2026-08-21T17:30:00Z"},
            {"id": 2, "deadline_time": "2026-08-28T17:30:00Z"},
        ]
    )
    state = OfficialEntryClient(http, 63984).latest_public_state(
        events,
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
