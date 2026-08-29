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
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, **kwargs):
        del kwargs
        if url.endswith("/api/me/"):
            return FakeResponse(200, {"player": {"entry": 63984}})
        if url.endswith("/api/my-team/63984/"):
            return FakeResponse(200, self.payload)
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


def payload(*, scale: int = 1, bank_scale: int | None = None, value_scale: int | None = None):
    bank_scale = scale if bank_scale is None else bank_scale
    value_scale = scale if value_scale is None else value_scale
    picks = [
        {
            "element": player_id,
            "purchase_price": 50 * scale,
            "selling_price": 50 * scale,
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
            "bank": 7 * bank_scale,
            "value": 757 * value_scale,
            "limit": 2,
            "made": 1,
            "status": "cost",
            "cost": 0,
        },
    }


def acquire(monkeypatch, body):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "secret-token")
    return fetch_team_state(
        63984,
        official(),
        session=FakeSession(body),
        now=datetime(2026, 8, 29, 15, tzinfo=timezone.utc),
    )


def test_authenticated_ten_x_owned_prices_are_normalized_only_when_fully_coherent(monkeypatch):
    state = acquire(monkeypatch, payload(scale=10))
    assert state is not None
    assert state.purchase_prices_tenths == {player_id: 50 for player_id in range(1, 16)}
    assert state.selling_prices_tenths == {player_id: 50 for player_id in range(1, 16)}
    assert state.bank_tenths == 7
    assert state.state_complete_for_transfers is True


def test_authenticated_ten_x_pick_prices_can_coexist_with_standard_bank_fields(monkeypatch):
    state = acquire(monkeypatch, payload(scale=10, bank_scale=1, value_scale=1))
    assert state is not None
    assert state.bank_tenths == 7
    assert state.selling_prices_tenths[1] == 50


def test_authenticated_mixed_owned_price_scales_fail_closed(monkeypatch):
    body = payload(scale=1)
    body["picks"][0]["purchase_price"] *= 10
    body["picks"][0]["selling_price"] *= 10
    with pytest.raises(RuntimeError, match="authenticated monetary state is inconsistent"):
        acquire(monkeypatch, body)


def test_authenticated_money_checksum_mismatch_fails_closed(monkeypatch):
    body = payload(scale=10)
    body["transfers"]["value"] += 10
    with pytest.raises(RuntimeError, match="authenticated monetary state is inconsistent"):
        acquire(monkeypatch, body)


def test_authenticated_nonstandard_price_scale_requires_value_checksum(monkeypatch):
    body = payload(scale=10)
    body["transfers"].pop("value")
    with pytest.raises(RuntimeError, match="authenticated monetary state is inconsistent"):
        acquire(monkeypatch, body)


def test_authenticated_price_failure_does_not_disclose_owned_player_or_money(monkeypatch):
    body = payload(scale=1)
    body["picks"][0]["selling_price"] = 51
    with pytest.raises(RuntimeError) as observed:
        acquire(monkeypatch, body)
    message = str(observed.value)
    assert "element 1" not in message
    assert "expected sell" not in message
    assert "got 51" not in message
    assert "Restart acquisition from a fresh Official seal" in message
