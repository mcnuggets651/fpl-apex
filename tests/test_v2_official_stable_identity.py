from __future__ import annotations

from apex.sources.official import _canonical_hash, _official_authority_payload


def _bootstrap(code: int) -> dict:
    return {
        "elements": [
            {
                "id": 7,
                "code": code,
                "team": 3,
                "element_type": 3,
                "now_cost": 75,
                "status": "a",
                "can_transact": True,
                "chance_of_playing_this_round": None,
                "chance_of_playing_next_round": None,
                "news": "",
                "news_added": None,
            }
        ],
        "events": [
            {
                "id": 2,
                "deadline_time": "2026-08-28T18:00:00Z",
                "finished": False,
                "is_current": False,
                "is_next": True,
            }
        ],
    }


def _fixtures() -> list[dict]:
    return [
        {
            "id": 20,
            "event": 2,
            "team_h": 3,
            "team_a": 4,
            "kickoff_time": "2026-08-29T14:00:00Z",
            "started": False,
            "finished": False,
            "provisional_start_time": False,
        }
    ]


def test_stable_fpl_code_is_part_of_official_authority_seal():
    first = _official_authority_payload(_bootstrap(12345), _fixtures())
    second = _official_authority_payload(_bootstrap(54321), _fixtures())
    assert first["players"][0]["code"] == 12345
    assert _canonical_hash(first) != _canonical_hash(second)
