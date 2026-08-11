from pathlib import Path

from apex_fpl.config import _configured_news_sources


def test_configured_news_source_preserves_name_tier_and_url(monkeypatch, tmp_path: Path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "news_sources.yaml").write_text(
        "feeds:\n"
        "  - name: Example Club\n"
        "    url: https://example.test/news\n"
        "    tier: official_club\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("APEX_NEWS_FEEDS", raising=False)
    assert _configured_news_sources({}) == [
        {
            "name": "Example Club",
            "url": "https://example.test/news",
            "tier": "official_club",
        }
    ]
