from __future__ import annotations

from copy import deepcopy

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
        raise AssertionError(url)


def _payloads():
    bootstrap = {
        "elements": [
            {
                "id": 1,
                "code": 123456,
                "web_name": "Player",
                "team": 1,
                "element_type": 3,
                "now_cost": 75,
                "status": "a",
                "can_transact": True,
                "chance_of_playing_this_round": 100,
                "chance_of_playing_next_round": 100,
                "news": "",
                "news_added": None,
                # Continuously changing market counters: audit-only, not authority.
                "selected_by_percent": "11.1",
                "transfers_in_event": 100,
                "transfers_out_event": 50,
                "total_points": 7,
            }
        ],
        "events": [
            {
                "id": 2,
                "deadline_time": "2026-08-29T10:00:00Z",
                "finished": False,
                "is_current": False,
                "is_next": True,
            }
        ],
    }
    fixtures = [
        {
            "id": 100,
            "event": 2,
            "team_h": 1,
            "team_a": 2,
            "kickoff_time": "2026-08-29T14:00:00Z",
            "started": False,
            "finished": False,
            "provisional_start_time": False,
        }
    ]
    return bootstrap, fixtures


def _snapshot(bootstrap, fixtures):
    return fetch_official_snapshot(
        season="2026-2027",
        session=_Session(bootstrap, fixtures),
    )


def test_market_noise_changes_raw_hash_but_not_authority_seal():
    bootstrap, fixtures = _payloads()
    first, first_raw = _snapshot(bootstrap, fixtures)

    noisy = deepcopy(bootstrap)
    noisy["elements"][0]["selected_by_percent"] = "13.7"
    noisy["elements"][0]["transfers_in_event"] = 91234
    noisy["elements"][0]["transfers_out_event"] = 731
    noisy["elements"][0]["total_points"] = 999
    second, second_raw = _snapshot(noisy, fixtures)

    assert first.source_hash == second.source_hash
    assert (
        first_raw["raw_hashes"]["bootstrap_sha256"]
        != second_raw["raw_hashes"]["bootstrap_sha256"]
    )


def test_identity_price_status_availability_changes_move_authority_seal():
    bootstrap, fixtures = _payloads()
    baseline, _ = _snapshot(bootstrap, fixtures)

    for field, value in (
        ("code", 654321),
        ("now_cost", 76),
        ("status", "d"),
        ("can_transact", False),
        ("chance_of_playing_next_round", 50),
        ("news", "Knock - 50% chance of playing"),
    ):
        changed = deepcopy(bootstrap)
        changed["elements"][0][field] = value
        observed, _ = _snapshot(changed, fixtures)
        assert observed.source_hash != baseline.source_hash, field


def test_fixture_or_deadline_change_moves_authority_seal():
    bootstrap, fixtures = _payloads()
    baseline, _ = _snapshot(bootstrap, fixtures)

    moved_fixture = deepcopy(fixtures)
    moved_fixture[0]["kickoff_time"] = "2026-08-30T14:00:00Z"
    fixture_snapshot, _ = _snapshot(bootstrap, moved_fixture)
    assert fixture_snapshot.source_hash != baseline.source_hash

    moved_deadline = deepcopy(bootstrap)
    moved_deadline["events"][0]["deadline_time"] = "2026-08-29T11:00:00Z"
    deadline_snapshot, _ = _snapshot(moved_deadline, fixtures)
    assert deadline_snapshot.source_hash != baseline.source_hash
