from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
import pytest

from apex_fpl.data.news import NewsItem
from apex_fpl.models.minutes import minutes_profile
from apex_fpl.services.news_signals import infer_news_signals


def test_transfer_headline_creates_risk_without_changing_identity():
    players = pd.DataFrame(
        [
            {
                "player_id": 10,
                "web_name": "Example",
                "second_name": "Example",
                "team": 3,
                "position": "MID",
                "price": 7.0,
            }
        ]
    )
    items = [
        NewsItem(
            title="Example close to joining another club after transfer talks",
            source="trusted",
            source_tier="trusted_media",
            published="2026-08-07T07:00:00+00:00",
            link="https://example.test/story",
        )
    ]
    signal, audit = infer_news_signals(
        players,
        items,
        now=datetime(2026, 8, 7, 8, tzinfo=timezone.utc),
    )
    assert signal.iloc[0]["news_event_type"] == "transfer"
    assert signal.iloc[0]["news_multiplier"] < 1.0
    assert audit.iloc[0]["evidence_type"] == "transfer"
    # The signal contract does not contain identity fields that could overwrite
    # the official FPL universe.
    assert "team" not in signal.columns
    assert "position" not in signal.columns
    assert "price" not in signal.columns


def test_manager_start_doubt_is_classified():
    players = pd.DataFrame(
        [{"player_id": 20, "web_name": "Starter", "second_name": "Starter"}]
    )
    items = [
        NewsItem(
            title="Manager says Starter is unlikely to start this weekend",
            source="trusted",
            source_tier="trusted_media",
            published="2026-08-07T07:00:00+00:00",
            link="https://example.test/manager",
        )
    ]
    signal, _ = infer_news_signals(
        players,
        items,
        now=datetime(2026, 8, 7, 8, tzinfo=timezone.utc),
    )
    assert signal.iloc[0]["news_event_type"] == "manager"
    assert signal.iloc[0]["news_multiplier"] == 0.68


def test_stale_injury_headline_is_expired_before_it_can_change_minutes():
    players = pd.DataFrame(
        [{"player_id": 30, "web_name": "Fresh", "second_name": "Fresh"}]
    )
    items = [
        NewsItem(
            title="Fresh ruled out with hamstring injury",
            source="trusted",
            source_tier="trusted_media",
            published="2026-07-20T10:00:00+00:00",
            link="https://example.test/old-story",
        )
    ]
    signal, audit = infer_news_signals(
        players,
        items,
        max_age_hours=120,
        now=datetime(2026, 8, 7, 8, tzinfo=timezone.utc),
    )
    assert signal.empty
    assert len(audit) == 1
    assert audit.iloc[0]["eligible_for_projection"] == False  # noqa: E712
    assert audit.iloc[0]["ineligibility_reason"] == "expired_publication"


def test_unknown_publication_time_is_audited_but_cannot_change_projection():
    players = pd.DataFrame(
        [{"player_id": 40, "web_name": "Known", "second_name": "Known"}]
    )
    items = [
        NewsItem(
            title="Known will start this weekend",
            source="Official club",
            source_tier="official_club",
            published=None,
            retrieved_at="2026-08-07T08:00:00+00:00",
            link="https://example.test/story",
        )
    ]
    signal, audit = infer_news_signals(
        players,
        items,
        now=datetime(2026, 8, 7, 8, tzinfo=timezone.utc),
    )
    assert signal.empty
    assert audit.iloc[0]["published_at"] is None
    assert audit.iloc[0]["retrieved_at"] == "2026-08-07T08:00:00+00:00"
    assert audit.iloc[0]["ineligibility_reason"] == "unknown_publication_time"


def test_verified_start_news_produces_bounded_predictable_minutes_update():
    players = pd.DataFrame(
        [
            {
                "player_id": 50,
                "web_name": "Riser",
                "second_name": "Riser",
                "minutes": 0,
                "starts": 0,
                "previous_minutes_per_match": 40,
                "previous_start_probability": 0.45,
                "status": "a",
            }
        ]
    )
    item = NewsItem(
        title="Manager confirms Riser will start this weekend",
        source="Riser FC",
        source_tier="official_club",
        published="2026-08-07T07:00:00+00:00",
        retrieved_at="2026-08-07T08:00:00+00:00",
        link="https://example.test/manager",
    )
    signal, _ = infer_news_signals(
        players,
        [item],
        now=datetime(2026, 8, 7, 8, tzinfo=timezone.utc),
    )
    enriched = players.merge(signal, on="player_id", how="left")
    baseline = minutes_profile(players).iloc[0]
    changed = minutes_profile(enriched).iloc[0]
    assert signal.iloc[0]["news_minutes_delta"] == 8.0
    assert signal.iloc[0]["news_start_probability_delta"] == 0.10
    assert changed["expected_minutes"] - baseline["expected_minutes"] == 8.0
    assert changed["start_probability"] - baseline["start_probability"] == pytest.approx(0.10)


def test_long_term_contract_is_not_misclassified_as_long_term_injury():
    players = pd.DataFrame(
        [{"player_id": 60, "web_name": "Defender", "second_name": "Defender"}]
    )
    item = NewsItem(
        title="Defender signs new long-term deal with club",
        source="Trusted",
        source_tier="trusted_media",
        published="2026-08-11T07:00:00+00:00",
        retrieved_at="2026-08-11T08:00:00+00:00",
        link="https://example.test/contract",
    )
    signal, audit = infer_news_signals(
        players,
        [item],
        now=datetime(2026, 8, 11, 8, tzinfo=timezone.utc),
    )
    assert signal.empty
    assert audit.iloc[0]["evidence_type"] == "general"
    assert audit.iloc[0]["ineligibility_reason"] == "no_decision_relevant_evidence"


def test_ambiguous_surname_requires_full_name_or_club_context():
    players = pd.DataFrame(
        [
            {"player_id": 70, "first_name": "Alex", "second_name": "Smith", "web_name": "Smith", "team_name": "North FC"},
            {"player_id": 71, "first_name": "Ben", "second_name": "Smith", "web_name": "Smith", "team_name": "South FC"},
        ]
    )
    item = NewsItem(
        title="Manager confirms Smith will start",
        source="Trusted",
        source_tier="trusted_media",
        published="2026-08-11T07:00:00+00:00",
        link="https://example.test/story",
    )
    signal, audit = infer_news_signals(
        players, [item], now=datetime(2026, 8, 11, 8, tzinfo=timezone.utc)
    )
    assert signal.empty
    assert set(audit["ineligibility_reason"]) == {"ambiguous_player_identity"}

    item.title = "North FC manager confirms Smith will start"
    signal, _ = infer_news_signals(
        players, [item], now=datetime(2026, 8, 11, 8, tzinfo=timezone.utc)
    )
    assert signal["player_id"].tolist() == [70]


def test_typed_set_piece_and_role_evidence_is_decision_eligible():
    players = pd.DataFrame(
        [{"player_id": 80, "first_name": "Role", "second_name": "Player", "web_name": "Player"}]
    )
    items = [
        NewsItem(
            title="Role Player is on penalties and playing as a number 10",
            source="Official club",
            source_tier="official_club",
            published="2026-08-06T08:00:00+00:00",
            link="https://example.test/role",
        )
    ]
    signal, audit = infer_news_signals(
        players, items, now=datetime(2026, 8, 11, 8, tzinfo=timezone.utc)
    )
    assert signal.iloc[0]["news_event_type"] == "set_piece"
    assert audit.iloc[0]["eligible_for_projection"] == True  # noqa: E712


def test_negated_injury_phrase_cannot_reduce_minutes():
    players = pd.DataFrame(
        [{"player_id": 81, "first_name": "Fit", "second_name": "Player", "web_name": "Player"}]
    )
    item = NewsItem(
        title="Manager confirms Fit Player is not injured and will start",
        source="Official club",
        source_tier="official_club",
        published="2026-08-11T07:00:00+00:00",
        link="https://example.test/fitness",
    )
    signal, _ = infer_news_signals(
        players, [item], now=datetime(2026, 8, 11, 8, tzinfo=timezone.utc)
    )
    assert signal.iloc[0]["news_multiplier"] == 1.0
    assert signal.iloc[0]["news_event_type"] == "manager"
