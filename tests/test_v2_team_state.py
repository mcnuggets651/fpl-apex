from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from apex.domain.models import (
    ExecutionDecision,
    OfficialPlayer,
    OfficialSnapshot,
    Position,
    TeamState,
)
from apex.sources.team import apply_execution_overlay, fetch_team_state


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
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        for suffix, response in self.routes.items():
            if url.endswith(suffix):
                return response
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
            50 + (1 if index == 1 else 0),
            "a",
            True,
        )
        for index, position in enumerate(positions, start=1)
    )
    return OfficialSnapshot(
        1,
        "2026-2027",
        "2026-08-28T10:00:00Z",
        "official-seal",
        players,
        (),
        {
            1: "2026-08-21T17:30:00Z",
            2: "2026-08-28T17:30:00Z",
        },
    )


def authenticated_payload(*, limit=2, made=1, status="cost"):
    # Player 1 was bought at 50 and is now 51, therefore the exact FPL sell price is 50.
    picks = [
        {
            "element": player_id,
            "purchase_price": 50,
            "selling_price": 50,
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
            "bank": 7,
            "limit": limit,
            "made": made,
            "status": status,
            "cost": 0,
            "value": 757,
        },
    }


def auth_session(payload=None, *, me_status=200, team_status=200, entry=63984):
    return FakeSession(
        {
            "/api/me/": FakeResponse(me_status, {"player": {"entry": entry}}),
            "/api/my-team/63984/": FakeResponse(
                team_status,
                payload if payload is not None else authenticated_payload(),
            ),
        }
    )


def test_authenticated_team_state_is_exact_and_complete(monkeypatch):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "secret-token")
    session = auth_session()

    state = fetch_team_state(
        63984,
        official(),
        session=session,
        now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
    )

    assert state is not None
    assert state.state_complete_for_transfers is True
    assert state.squad_ids == tuple(range(1, 16))
    assert state.bank_tenths == 7
    assert state.free_transfers == 1
    assert state.purchase_prices_tenths == {player_id: 50 for player_id in range(1, 16)}
    assert state.selling_prices_tenths == {player_id: 50 for player_id in range(1, 16)}
    assert session.calls[0][1]["headers"]["X-API-Authorization"] == "Bearer secret-token"


def test_authenticated_wrong_entry_fails_closed(monkeypatch):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "secret-token")
    with pytest.raises(RuntimeError, match="different manager entry"):
        fetch_team_state(
            63984,
            official(),
            session=auth_session(entry=123),
            now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
        )


def test_rejected_authenticated_credential_does_not_publicly_downgrade(monkeypatch):
    monkeypatch.setenv("FPL_SESSION_COOKIE", "sessionid=secret")
    with pytest.raises(RuntimeError, match="credential was rejected"):
        fetch_team_state(
            63984,
            official(),
            session=auth_session(me_status=403),
            now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
        )


def test_authenticated_missing_prices_fail_closed(monkeypatch):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "secret-token")
    payload = authenticated_payload()
    payload["picks"][0].pop("selling_price")
    with pytest.raises(RuntimeError, match="omitted purchase/selling prices"):
        fetch_team_state(
            63984,
            official(),
            session=auth_session(payload),
            now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
        )


def test_authenticated_price_mismatch_requires_fresh_official_seal(monkeypatch):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "secret-token")
    payload = authenticated_payload()
    payload["picks"][0]["selling_price"] = 51
    with pytest.raises(RuntimeError, match="Restart acquisition from a fresh Official seal"):
        fetch_team_state(
            63984,
            official(),
            session=auth_session(payload),
            now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
        )


def test_unlimited_transfer_window_is_not_certified_as_ordinary_ft_state(monkeypatch):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "secret-token")
    state = fetch_team_state(
        63984,
        official(),
        session=auth_session(authenticated_payload(limit=None, made=2, status="unlimited")),
        now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
    )
    assert state is not None
    assert state.free_transfers == 0
    assert state.state_complete_for_transfers is False


def test_no_secret_uses_public_last_deadline_state_and_stays_incomplete(monkeypatch):
    monkeypatch.delenv("FPL_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("FPL_X_API_AUTHORIZATION", raising=False)
    public_picks = {
        "picks": [{"element": player_id} for player_id in range(1, 16)],
        "entry_history": {"bank": 4, "event_transfers": 0},
        "active_chip": None,
    }
    history = {"current": [{"event": 1, "event_transfers": 0}], "chips": []}
    session = FakeSession(
        {
            "/api/entry/63984/event/1/picks/": FakeResponse(200, public_picks),
            "/api/entry/63984/history/": FakeResponse(200, history),
        }
    )

    state = fetch_team_state(
        63984,
        official(),
        session=session,
        now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
    )
    assert state is not None
    assert state.state_complete_for_transfers is False
    assert state.purchase_prices_tenths == {}
    assert state.selling_prices_tenths == {}
    assert all("headers" not in kwargs for _, kwargs in session.calls)


def complete_state() -> TeamState:
    squad = tuple(range(1, 16))
    return TeamState(
        1,
        63984,
        1,
        squad,
        0,
        1,
        {player_id: 50 for player_id in squad},
        {player_id: 50 for player_id in squad},
        None,
        True,
    )


def test_execution_overlay_updates_bank_and_remaining_free_transfers():
    base = official()
    replacement_player = OfficialPlayer(16, "P16", 6, Position.GK, 49, "a", True)
    base = replace(base, players=base.players + (replacement_player,))
    state = complete_state()
    execution = ExecutionDecision(
        1,
        "decision-hash",
        "manager",
        "2026-08-28T15:00:00Z",
        "accepted transfer",
        tuple(range(2, 17)),
        tuple(range(2, 12)) + (16,),
        2,
        3,
        (12, 13, 14, 15),
        (16,),
        (1,),
    )

    updated = apply_execution_overlay(state, execution, base)

    assert updated.bank_tenths == 1
    assert updated.free_transfers == 0
    assert 1 not in updated.purchase_prices_tenths
    assert updated.purchase_prices_tenths[16] == 49
    assert updated.selling_prices_tenths[16] == 49
    assert updated.state_complete_for_transfers is True


def test_execution_overlay_rejects_negative_bank():
    base = official()
    expensive = OfficialPlayer(16, "P16", 6, Position.GK, 60, "a", True)
    base = replace(base, players=base.players + (expensive,))
    state = complete_state()
    execution = ExecutionDecision(
        1,
        "decision-hash",
        "manager",
        "2026-08-28T15:00:00Z",
        "accepted transfer",
        tuple(range(2, 17)),
        tuple(range(2, 12)) + (16,),
        2,
        3,
        (12, 13, 14, 15),
        (16,),
        (1,),
    )
    with pytest.raises(ValueError, match="negative bank"):
        apply_execution_overlay(state, execution, base)
