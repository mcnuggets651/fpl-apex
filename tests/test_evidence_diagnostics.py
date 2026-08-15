from __future__ import annotations

import pandas as pd

from apex_fpl.services.data_quality import _preseason_check
from apex_fpl.services.enrichment import _enrich_understat_player_rates


def test_preseason_quality_distinguishes_advanced_and_event_evidence():
    friendlies = pd.DataFrame(
        {
            "player_id": [1, 2],
            "match_id": [10, 10],
            "minutes_played": [90, 45],
            "xg": [None, None],
            "xa": [None, None],
            "defensive_contributions": [None, None],
            "goals": [2, 0],
            "assists": [0, 1],
            "total_shots": [5, 1],
        }
    )
    check = _preseason_check(friendlies)
    assert check.status == "warning"
    assert check.coverage == 0.0
    assert "advanced xG/xA/defcon observation coverage=0.0%" in check.detail
    assert "evidence coverage=100.0%" in check.detail
    assert "does not affect attacking xP" in check.detail


def test_understat_enrichment_exposes_match_method(monkeypatch):
    players = pd.DataFrame(
        {
            "player_id": [1],
            "first_name": ["João Pedro Junqueira"],
            "second_name": ["de Jesus"],
            "web_name": ["João Pedro"],
            "team_name": ["Chelsea"],
            "expected_goals_per_90_core": [0.45],
            "expected_assists_per_90_core": [0.15],
        }
    )
    normalized = pd.DataFrame(
        {
            "player_name": ["Joao Pedro"],
            "team_name": ["Chelsea"],
            "understat_xg90": [0.5],
            "understat_xa90": [0.2],
        }
    )
    monkeypatch.setattr(
        "apex_fpl.services.enrichment.fetch_understat_season",
        lambda *args, **kwargs: {},
    )
    monkeypatch.setattr(
        "apex_fpl.services.enrichment.normalise_understat_players",
        lambda payload, year: normalized,
    )
    out = _enrich_understat_player_rates(players).iloc[0]
    assert bool(out["understat_player_matched"]) is True
    assert out["understat_match_method"] == "web_name_team"
