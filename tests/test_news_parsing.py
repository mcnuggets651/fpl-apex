from apex_fpl.data.news import parse_news_document


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
