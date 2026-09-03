from __future__ import annotations

from copy import deepcopy

import pytest

from apex.sources.official import fetch_official_snapshot


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return deepcopy(self._payload)


class _Session:
    def __init__(self, bootstrap, fixtures):
        self.bootstrap = bootstrap
        self.fixtures = fixtures

    def get(self, url, timeout):
        del timeout
        if url.endswith("/bootstrap-static/"):
            return _Response(self.bootstrap)
        if url.endswith("/fixtures/"):
            return _Response(self.fixtures)
        raise AssertionError(f"unexpected URL {url}")


def _payloads():
    bootstrap = {
        "elements": [
            {
                "id": 1,
                "code": 1001,
                "web_name": "One",
                "team": 1,
                "element_type": 3,
                "now_cost": 50,
                "status": "a",
                "can_transact": True,
            },
            {
                "id": 2,
                "code": 1002,
                "web_name": "Two",
                "team": 2,
                "element_type": 4,
                "now_cost": 60,
                "status": "a",
                "can_transact": True,
            },
        ],
        "teams": [
            {"id": 1, "name": "A"},
            {"id": 2, "name": "B"},
        ],
        "events": [
            {
                "id": 5,
                "deadline_time": "2026-09-12T10:00:00Z",
                "finished": False,
                "is_current": False,
                "is_next": True,
            }
        ],
    }
    fixtures = [
        {
            "id": 101,
            "event": 5,
            "team_h": 1,
            "team_a": 2,
            "kickoff_time": "2026-09-12T14:00:00Z",
            "started": False,
            "finished": False,
        }
    ]
    return bootstrap, fixtures


def _fetch(bootstrap, fixtures):
    return fetch_official_snapshot(
        season="2026-2027",
        session=_Session(bootstrap, fixtures),
    )


def test_official_rejects_nonpositive_player_price():
    bootstrap, fixtures = _payloads()
    bootstrap["elements"][0]["now_cost"] = 0

    with pytest.raises(ValueError, match="price"):
        _fetch(bootstrap, fixtures)


def test_official_rejects_player_team_not_in_official_team_catalogue():
    bootstrap, fixtures = _payloads()
    bootstrap["elements"][0]["team"] = 999

    with pytest.raises(ValueError, match="team"):
        _fetch(bootstrap, fixtures)


def test_official_rejects_duplicate_fixture_ids():
    bootstrap, fixtures = _payloads()
    fixtures.append(dict(fixtures[0]))

    with pytest.raises(ValueError, match="duplicate fixture"):
        _fetch(bootstrap, fixtures)


def test_official_rejects_fixture_team_not_in_official_team_catalogue():
    bootstrap, fixtures = _payloads()
    fixtures[0]["team_a"] = 999

    with pytest.raises(ValueError, match="fixture.*team|team.*fixture"):
        _fetch(bootstrap, fixtures)


def test_official_rejects_non_boolean_transaction_flag():
    bootstrap, fixtures = _payloads()
    bootstrap["elements"][0]["can_transact"] = "false"

    with pytest.raises(ValueError, match="can_transact"):
        _fetch(bootstrap, fixtures)
