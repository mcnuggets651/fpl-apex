from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from apex.domain.models import OfficialPlayer, OfficialSnapshot, Position
from apex.sources import evidence as evidence_module


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/rss+xml"):
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, url: str, response: FakeResponse):
        self.url = url
        self.response = response

    def get(self, url, **kwargs):
        del kwargs
        if url != self.url:
            raise AssertionError(url)
        return self.response


def test_required_source_with_zero_parseable_items_fails_closed(monkeypatch, tmp_path: Path):
    official = OfficialSnapshot(
        schema_version=1,
        season="2026-2027",
        acquired_at="2026-08-29T08:00:00+00:00",
        source_hash="stable-hash",
        players=(
            OfficialPlayer(1, "Player One", 1, Position.MID, 50, "a", True, 1001),
        ),
        fixtures=(),
        deadlines={3: "2026-09-12T10:00:00+00:00"},
    )
    raw = {
        "bootstrap": {
            "elements": [
                {
                    "id": 1,
                    "first_name": "Player",
                    "second_name": "One",
                    "web_name": "Player One",
                    "status": "a",
                    "chance_of_playing_this_round": 100,
                    "news": "",
                    "news_added": None,
                }
            ]
        },
        "fixtures": [],
    }
    monkeypatch.setattr(
        evidence_module,
        "fetch_official_snapshot",
        lambda **kwargs: (official, raw),
    )
    source_url = "https://official.test/news"
    sources = tmp_path / "sources.yaml"
    sources.write_text(
        "\n".join(
            (
                "feeds:",
                "  - name: Official League",
                f"    url: {source_url}",
                "    tier: official_league",
                "    required: true",
                "",
            )
        ),
        encoding="utf-8",
    )
    manifest = tmp_path / "manifest.json"
    with pytest.raises(RuntimeError, match="required external evidence source failed"):
        evidence_module.collect_v2_evidence(
            sources_path=sources,
            records_path=tmp_path / "hard.json",
            manifest_path=manifest,
            expected_official_hash="stable-hash",
            session=FakeSession(
                source_url,
                FakeResponse(b"<rss><channel><title>Feed</title></channel></rss>"),
            ),
            now=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
        )

    import json

    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["completed"] is False
    assert payload["required_source_failures"] == ["Official League"]
    assert payload["sources"][0]["status"] == "EMPTY"
