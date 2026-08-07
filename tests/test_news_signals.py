from __future__ import annotations

import pandas as pd

from apex_fpl.data.news import NewsItem
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
            published="2026-08-07T07:00:00+00:00",
            link="https://example.test/story",
        )
    ]
    signal, audit = infer_news_signals(players, items)
    assert signal.iloc[0]["news_event_type"] == "transfer"
    assert signal.iloc[0]["news_multiplier"] < 1.0
    assert audit.iloc[0]["event_type"] == "transfer"
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
            published="2026-08-07T07:00:00+00:00",
            link="https://example.test/manager",
        )
    ]
    signal, _ = infer_news_signals(players, items)
    assert signal.iloc[0]["news_event_type"] == "manager"
    assert signal.iloc[0]["news_multiplier"] == 0.68
