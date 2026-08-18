import json

from apex_fpl.data.understat import (
    UNDERSTAT_API_URL,
    UNDERSTAT_PAGE_URL,
    decode_league_page,
    fetch_understat_season,
)


def _payload() -> dict:
    return {
        "dates": [
            {
                "id": "1",
                "isResult": True,
                "h": {"id": "1", "title": "Arsenal"},
                "a": {"id": "2", "title": "Chelsea"},
                "goals": {"h": "1", "a": "0"},
                "xG": {"h": "1.4", "a": "0.7"},
                "datetime": "2018-08-01 15:00:00",
            }
        ],
        "teams": {
            "1": {"id": "1", "title": "Arsenal", "history": []},
            "2": {"id": "2", "title": "Chelsea", "history": []},
        },
    }


def _league_page(payload: dict) -> str:
    dates = json.dumps({"dates": payload["dates"]}, separators=(",", ":"))
    teams = json.dumps({"teams": payload["teams"]}, separators=(",", ":"))
    return (
        "<html><script>"
        f"var datesData = JSON.parse({dates!r});"
        f"var teamsData = JSON.parse({teams!r});"
        "</script></html>"
    )


def test_decode_league_page_reconstructs_api_contract() -> None:
    payload = _payload()
    assert decode_league_page(_league_page(payload)) == payload


def test_fetch_falls_back_to_league_page_when_api_endpoint_is_gone(tmp_path) -> None:
    payload = _payload()
    calls = []

    def fetcher(url: str, timeout: int) -> str:
        calls.append((url, timeout))
        if url == UNDERSTAT_API_URL.format(season=2018):
            raise RuntimeError("404")
        assert url == UNDERSTAT_PAGE_URL.format(season=2018)
        return _league_page(payload)

    out = fetch_understat_season(2018, cache_dir=tmp_path, attempts=1, fetcher=fetcher)

    assert out == payload
    assert [url for url, _ in calls] == [
        UNDERSTAT_API_URL.format(season=2018),
        UNDERSTAT_PAGE_URL.format(season=2018),
    ]
