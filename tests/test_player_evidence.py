from datetime import datetime, timezone

import pandas as pd

from apex_fpl.services.player_evidence import build_selected_player_evidence
from apex_fpl.services.decision_eligibility import evidence_eligibility


NOW = datetime(2026, 8, 11, 8, tzinfo=timezone.utc)


def _players() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "web_name": "Captain",
                "expected_minutes": 78,
                "start_probability": 0.88,
                "minutes_confidence": 0.80,
                "tactical_role": "ten",
                "tactical_role_source": "statistical_inference",
                "role_confidence": 0.70,
            },
            {
                "player_id": 2,
                "web_name": "Uncertain",
                "expected_minutes": 61,
                "start_probability": 0.62,
                "minutes_confidence": 0.60,
                "tactical_role": "winger",
                "tactical_role_source": "statistical_inference",
                "role_confidence": 0.50,
            },
        ]
    )


def _news() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "player_id": 1,
                "headline": "Captain will start",
                "source_name": "Official club",
                "source_tier": "official_club",
                "source_url": "https://example.test/captain",
                "published_at": "2026-08-11T07:00:00+00:00",
                "retrieved_at": "2026-08-11T07:30:00+00:00",
                "evidence_type": "manager",
                "eligible_for_projection": True,
                "multiplier": 1.0,
                "minutes_delta": 8.0,
                "start_probability_delta": 0.10,
            }
        ]
    )


def test_uncovered_high_uncertainty_starter_is_flagged_but_not_rejected():
    players, _ = evidence_eligibility(_players(), _news())
    payload = build_selected_player_evidence(
        players, _news(), [1, 2], xi_ids=[1, 2], captain_id=1, now=NOW
    )
    coverage = payload["coverage"]
    assert coverage["captain_has_current_evidence"] is True
    assert coverage["high_uncertainty_starters_missing_evidence"] == [2]
    assert coverage["selected_xi_ineligible_ids"] == []
    assert coverage["ready"] is True


def test_current_tactical_provenance_covers_high_uncertainty_starter():
    players = _players()
    mask = players.player_id.eq(2)
    players.loc[mask, "lineup_evidence_type"] = "official_manager"
    players.loc[mask, "source_name"] = "Official club"
    players.loc[mask, "source_tier"] = "official_club"
    players.loc[mask, "source_url"] = "https://example.test/uncertain"
    players.loc[mask, "published_at"] = "2026-08-11T07:00:00+00:00"
    players.loc[mask, "retrieved_at"] = "2026-08-11T07:30:00+00:00"
    players.loc[mask, "expires_at"] = "2026-08-12T07:00:00+00:00"
    payload = build_selected_player_evidence(
        players, _news(), [1, 2], xi_ids=[1, 2], captain_id=1, now=NOW
    )
    assert payload["coverage"]["ready"] is True
    assert payload["coverage"]["relevant_evidence_rows"] == 2


def test_single_trusted_media_story_is_visible_but_not_decision_grade_for_captain():
    news = _news()
    news.loc[:, "source_tier"] = "trusted_media"
    payload = build_selected_player_evidence(
        _players().iloc[[0]], news, [1], xi_ids=[1], captain_id=1, now=NOW
    )
    assert payload["coverage"]["captain_has_current_evidence"] is True
    assert payload["coverage"]["captain_has_decision_grade_evidence"] is False
    assert payload["coverage"]["ready"] is True


def test_two_independent_trusted_media_sources_are_decision_grade():
    news = pd.concat([_news(), _news()], ignore_index=True)
    news.loc[:, "source_tier"] = "trusted_media"
    news.loc[0, "source_name"] = "Trusted A"
    news.loc[0, "source_url"] = "https://a.example/captain"
    news.loc[1, "source_name"] = "Trusted B"
    news.loc[1, "source_url"] = "https://b.example/captain"
    news.loc[1, "headline"] = "Manager confirms Captain in the XI"
    payload = build_selected_player_evidence(
        _players().iloc[[0]], news, [1], xi_ids=[1], captain_id=1, now=NOW
    )
    assert payload["coverage"]["captain_has_decision_grade_evidence"] is True
    assert payload["coverage"]["ready"] is True


def test_two_articles_from_same_trusted_publisher_are_not_independent():
    news = pd.concat([_news(), _news()], ignore_index=True)
    news.loc[:, "source_tier"] = "trusted_media"
    news.loc[1, "source_url"] = "https://example.test/second-captain-story"
    payload = build_selected_player_evidence(
        _players().iloc[[0]], news, [1], xi_ids=[1], captain_id=1, now=NOW
    )
    assert payload["coverage"]["captain_has_decision_grade_evidence"] is False
    assert payload["coverage"]["ready"] is True
