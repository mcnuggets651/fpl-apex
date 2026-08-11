from apex_fpl.data.news import collect_news_sources, parse_news_document


def test_parse_rss_document():
    xml = b'''<?xml version="1.0"?><rss><channel><title>Trusted Football</title><item><title>Haaland returns to training</title><link>https://example.test/a</link><pubDate>Thu, 06 Aug 2026 10:00:00 GMT</pubDate></item></channel></rss>'''
    items = parse_news_document(xml, "https://example.test/feed.xml", "application/rss+xml")
    assert len(items) == 1
    assert items[0].source == "Trusted Football"
    assert "returns to training" in items[0].title


def test_parse_official_premier_league_html_news_links():
    html = b'''<html><body>
    <a href="/en/news/123456/latest-premier-league-player-injuries">Latest Premier League player injuries - club by club news</a>
    <a href="/en/news/123456/latest-premier-league-player-injuries">Latest Premier League player injuries - club by club news</a>
    <a href="/en/video/not-news">Ignore video</a>
    </body></html>'''
    items = parse_news_document(html, "https://www.premierleague.com/en/news", "text/html")
    assert len(items) == 1
    assert items[0].source == "Premier League"
    assert items[0].link == "https://www.premierleague.com/en/news/123456/latest-premier-league-player-injuries"


def test_structured_official_article_preserves_publication_and_body():
    html = b'''<html><head><script type="application/ld+json">
    {"@type":"NewsArticle","headline":"Manager confirms Example will start",
     "datePublished":"2026-08-11T09:00:00Z",
     "url":"https://club.example/news/team-news",
     "articleBody":"Example will start and is ready for the opener."}
    </script></head></html>'''
    items = parse_news_document(
        html,
        "https://club.example/news/team-news",
        "text/html",
        source_name="Official club",
        source_tier="official_club",
        retrieved_at="2026-08-11T10:00:00Z",
    )
    assert len(items) == 1
    assert items[0].published == "2026-08-11T09:00:00Z"
    assert "will start" in items[0].summary
    assert items[0].source_tier == "official_club"


def test_official_index_hydrates_same_host_structured_article(monkeypatch):
    index = b'''<a href="/news/team-news">Manager confirms Example will start</a>'''
    article = b'''<script type="application/ld+json">
    {"@type":"NewsArticle","headline":"Manager confirms Example will start",
     "datePublished":"2026-08-11T09:00:00Z","articleBody":"Example will start."}
    </script>'''

    class Response:
        def __init__(self, content):
            self.content = content
            self.headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    def get(url, **_kwargs):
        return Response(article if url.endswith("/news/team-news") else index)

    monkeypatch.setattr("apex_fpl.data.news.requests.get", get)
    result = collect_news_sources(
        [{"name": "Official club", "url": "https://club.example/news", "tier": "official_club"}]
    )
    timestamped = [item for item in result.items if item.published]
    assert len(timestamped) == 1
    assert len(result.items) == 1
    assert timestamped[0].link == "https://club.example/news/team-news"


def test_official_index_does_not_hydrate_cross_host_link(monkeypatch):
    index = b'''<a href="https://attacker.example/news/story">External news story cannot be followed</a>'''
    calls = []

    class Response:
        content = index
        headers = {"content-type": "text/html"}

        def raise_for_status(self):
            return None

    def get(url, **_kwargs):
        calls.append(url)
        return Response()

    monkeypatch.setattr("apex_fpl.data.news.requests.get", get)
    result = collect_news_sources(
        [{"name": "Official club", "url": "https://club.example/news", "tier": "official_club"}]
    )
    assert calls == ["https://club.example/news"]
    assert len(result.items) == 1
