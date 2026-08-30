from __future__ import annotations

from datetime import datetime, timezone

from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position
from apex.sources.team import acquire_team_state


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

    def get(self, url, **kwargs):
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


def public_routes(*, transfer_response: FakeResponse | None = None):
    picks = {
        "picks": [{"element": player_id} for player_id in range(1, 16)],
        "entry_history": {"bank": 4, "event_transfers": 0},
        "active_chip": None,
    }
    routes = {
        "/api/entry/63984/event/1/picks/": FakeResponse(200, picks),
        "/api/entry/63984/history/": FakeResponse(
            200,
            {"current": [{"event": 1, "event_transfers": 0}], "chips": []},
        ),
    }
    if transfer_response is not None:
        routes["/api/entry/63984/transfers/"] = transfer_response
    return routes


def test_public_fallback_freezes_historical_transfer_ledger_without_certifying(monkeypatch):
    monkeypatch.delenv("FPL_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("FPL_X_API_AUTHORIZATION", raising=False)
    ledger = [
        {
            "element_in": 16,
            "element_in_cost": 49,
            "element_out": 1,
            "element_out_cost": 50,
            "entry": 63984,
            "event": 1,
            "time": "2026-08-20T12:00:00Z",
        }
    ]
    acquisition = acquire_team_state(
        63984,
        official(),
        session=FakeSession(public_routes(transfer_response=FakeResponse(200, ledger))),
        now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
    )
    provenance = acquisition.provenance()

    assert acquisition.mode == "PUBLIC_DEADLINE_FALLBACK"
    assert acquisition.state is not None
    assert acquisition.state.state_complete_for_transfers is False
    assert acquisition.public_transfers == tuple(ledger)
    assert provenance["credential_present"] is False
    assert provenance["target_gameweek"] == 2
    assert provenance["public_transfer_ledger"]["row_count"] == 1
    assert provenance["public_transfer_ledger"]["events"] == [1]
    assert provenance["public_transfer_ledger"]["last_visible_event"] == 1
    assert provenance["public_transfer_ledger"]["target_gameweek_row_count"] == 0
    assert (
        provenance["public_transfer_ledger"]["visibility_contract"]
        == "PUBLIC_OTHER_VIEWERS_DEADLINE_REDACTED"
    )
    assert len(provenance["public_transfer_ledger"]["sha256"]) == 64


def test_public_transfer_ledger_failure_is_recorded_but_hold_state_survives(monkeypatch):
    monkeypatch.delenv("FPL_SESSION_COOKIE", raising=False)
    monkeypatch.delenv("FPL_X_API_AUTHORIZATION", raising=False)
    acquisition = acquire_team_state(
        63984,
        official(),
        session=FakeSession(public_routes(transfer_response=FakeResponse(503, {}))),
        now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
    )
    provenance = acquisition.provenance()

    assert acquisition.state is not None
    assert acquisition.state.state_complete_for_transfers is False
    assert provenance["public_transfer_ledger"]["available"] is False
    assert provenance["public_transfer_ledger"]["error"] == "HTTP 503"
    assert provenance["public_transfer_ledger"]["row_count"] == 0


def test_authenticated_mode_never_serializes_credential(monkeypatch):
    monkeypatch.setenv("FPL_X_API_AUTHORIZATION", "super-secret-token")
    picks = [
        {
            "element": player_id,
            "purchase_price": 50,
            "selling_price": 50,
        }
        for player_id in range(1, 16)
    ]
    session = FakeSession(
        {
            "/api/me/": FakeResponse(200, {"player": {"entry": 63984}}),
            "/api/my-team/63984/": FakeResponse(
                200,
                {
                    "picks": picks,
                    "chips": [],
                    "transfers": {
                        "bank": 3,
                        "limit": 1,
                        "made": 0,
                        "status": "cost",
                    },
                },
            ),
        }
    )

    acquisition = acquire_team_state(
        63984,
        official(),
        session=session,
        now=datetime(2026, 8, 28, 15, tzinfo=timezone.utc),
    )
    provenance = acquisition.provenance()
    serialized = str(provenance)

    assert acquisition.mode == "AUTHENTICATED_MY_TEAM"
    assert acquisition.state is not None
    assert acquisition.state.state_complete_for_transfers is True
    assert provenance["credential_present"] is True
    assert provenance["purchase_price_count"] == 15
    assert provenance["selling_price_count"] == 15
    assert "super-secret-token" not in serialized
    assert "Cookie" not in serialized
    assert "X-API-Authorization" not in serialized
