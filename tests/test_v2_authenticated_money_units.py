from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position
from apex.sources.team import fetch_team_state


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeSession:
    def __init__(
        self,
        payload,
        *,
        baseline_bank=4,
        latest=None,
        latest_status=200,
    ):
        self.payload = payload
        self.baseline_bank = baseline_bank
        self.latest = (
            [
                {
                    "element_in": 16,
                    "element_in_cost": 52,
                    "element_out": 17,
                    "element_out_cost": 55,
                    "entry": 63984,
                    "event": 3,
                    "time": "2026-08-29T12:00:00Z",
                }
            ]
            if latest is None
            else latest
        )
        self.latest_status = latest_status

    def get(self, url, **kwargs):
        del kwargs
        if url.endswith("/api/me/"):
            return FakeResponse(200, {"player": {"entry": 63984}})
        if url.endswith("/api/my-team/63984/"):
            return FakeResponse(200, self.payload)
        if url.endswith("/api/entry/63984/event/2/picks/"):
            return FakeResponse(
                200,
                {
                    "picks": [{"element": player_id} for player_id in range(1, 16)],
                    "entry_history": {"bank": self.baseline_bank},
                },
            )
        if url.endswith("/api/entry/63984/transfers-latest/"):
            return FakeResponse(self.latest_status, self.latest)
        raise AssertionError(f"unexpected GET {url}")


def official() -> OfficialSnapshot:
    positions = (
        [Position.GK] * 2
        + [Position.DEF] * 5
        + [Position.MID] * 5
        + [Position.FWD] * 3
    )
    players = tuple(
        OfficialPlayer(
            index,
            f"P{index}",
            1 + (index - 1) // 3,
            position,
            51 if index == 1 else 50,
            "a",
            True,
        )
        for index, position in enumerate(positions, start=1)
    )
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-29T12:00:00Z",
        "official-seal",
        players,
        (),
        {
            2: "2026-08-28T17:30:00Z",
            3: "2026-09-05T17:30:00Z",
        },
    )


def payload(*, price_scale: int = 1, bank: int = 7, value: int = 757):
    picks = [
        {
            "element": player_id,
            "purchase_price": 50 * price_scale,
            "selling_price": 50 * price_scale,
            "position": player_id,
            "multiplier": 1 if player_id <= 11 else 0,
            "is_captain": player_id == 1,
            "is_vice_captain": player_id == 2,
        }
        for player_id in range(1, 16)
    ]
    return {
        "picks": picks,
        "chips": [],
        "transfers": {
            "bank": bank,
            "value": value,
            "limit": 2,
            "made": 1,
            "status": "cost",
            "cost": 0,
        },
    }


def acquire(monkeypatch, body, **session_kwargs):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "secret-token")
    return fetch_team_state(
        63984,
        official(),
        session=FakeSession(body, **session_kwargs),
        now=datetime(2026, 8, 29, 15, tzinfo=timezone.utc),
    )


def test_authenticated_ten_x_owned_prices_and_bank_are_normalized_only_when_ledger_proves_them(monkeypatch):
    state = acquire(monkeypatch, payload(price_scale=10, bank=70))
    assert state is not None
    assert state.purchase_prices_tenths == {player_id: 50 for player_id in range(1, 16)}
    assert state.selling_prices_tenths == {player_id: 50 for player_id in range(1, 16)}
    assert state.bank_tenths == 7
    assert state.state_complete_for_transfers is True


def test_authenticated_ten_x_pick_prices_can_coexist_with_standard_bank_fields(monkeypatch):
    state = acquire(monkeypatch, payload(price_scale=10, bank=7))
    assert state is not None
    assert state.bank_tenths == 7
    assert state.selling_prices_tenths[1] == 50


def test_authenticated_value_field_is_not_treated_as_wallet_checksum(monkeypatch):
    state = acquire(monkeypatch, payload(price_scale=10, bank=70, value=1))
    assert state is not None
    assert state.bank_tenths == 7


def test_authenticated_mixed_owned_price_scales_fail_closed(monkeypatch):
    body = payload(price_scale=1)
    body["picks"][0]["purchase_price"] *= 10
    body["picks"][0]["selling_price"] *= 10
    with pytest.raises(RuntimeError, match="authenticated monetary state is inconsistent"):
        acquire(monkeypatch, body)


def test_authenticated_nonstandard_bank_must_match_independent_transfer_ledger(monkeypatch):
    with pytest.raises(RuntimeError, match="authenticated monetary state is inconsistent"):
        acquire(monkeypatch, payload(price_scale=10, bank=80))


def test_authenticated_nonstandard_price_scale_requires_current_transfer_ledger(monkeypatch):
    with pytest.raises(RuntimeError, match="authenticated monetary state is inconsistent"):
        acquire(
            monkeypatch,
            payload(price_scale=10, bank=70),
            latest_status=403,
        )


def test_authenticated_transfer_ledger_must_be_for_current_target_gameweek(monkeypatch):
    latest = [
        {
            "element_in": 16,
            "element_in_cost": 52,
            "element_out": 17,
            "element_out_cost": 55,
            "entry": 63984,
            "event": 2,
            "time": "2026-08-29T12:00:00Z",
        }
    ]
    with pytest.raises(RuntimeError, match="authenticated monetary state is inconsistent"):
        acquire(
            monkeypatch,
            payload(price_scale=10, bank=70),
            latest=latest,
        )


def test_authenticated_price_failure_does_not_disclose_owned_player_or_money(monkeypatch):
    body = payload(price_scale=1)
    body["picks"][0]["selling_price"] = 51
    with pytest.raises(RuntimeError) as observed:
        acquire(monkeypatch, body)
    message = str(observed.value)
    assert "element 1" not in message
    assert "expected sell" not in message
    assert "got 51" not in message
    assert "Restart acquisition from a fresh Official seal" in message
