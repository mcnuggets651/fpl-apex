from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin, urlparse
import xml.etree.ElementTree as ET

import pandas as pd
import requests


@dataclass
class NewsItem:
    title: str
    source: str
    published: str | None
    link: str
    source_tier: str = "unknown"
    retrieved_at: str = ""
    summary: str = ""


@dataclass(frozen=True)
class NewsSource:
    name: str
    url: str
    tier: str


@dataclass
class NewsCollectionResult:
    items: list[NewsItem]
    succeeded: list[str]
    failed: dict[str, str]


MANUAL_PROVENANCE_COLUMNS = (
    "source_name",
    "source_tier",
    "source_url",
    "evidence_type",
    "published_at",
    "expires_at",
    "relevant_excerpt",
    "content_hash",
    "transcriber",
)
TRUSTED_SOURCE_TIERS = {"official_club", "official_league", "trusted_media"}


def _utc(value: object, field: str) -> pd.Timestamp:
    parsed = pd.to_datetime(value, utc=True, errors="coerce")
    if pd.isna(parsed):
        raise ValueError(f"manual availability row requires valid {field}")
    return parsed


def load_manual_signals(
    path: str | Path = "data/manual/availability.csv",
    *,
    now: datetime | None = None,
) -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(
            columns=[
                "player_id",
                "availability_multiplier",
                "confidence",
                "reason",
                *MANUAL_PROVENANCE_COLUMNS,
                "retrieved_at",
            ]
        )
    df = pd.read_csv(p)
    required = {"player_id", "availability_multiplier"}
    if not required.issubset(df.columns):
        raise ValueError(f"manual availability file requires {sorted(required)}")
    missing = set(MANUAL_PROVENANCE_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(
            "manual availability overrides require provenance fields: "
            + ", ".join(sorted(missing))
        )
    now_value = pd.Timestamp(now or datetime.now(timezone.utc))
    now_utc = (
        now_value.tz_localize("UTC")
        if now_value.tzinfo is None
        else now_value.tz_convert("UTC")
    )
    out = df.copy()
    out["player_id"] = pd.to_numeric(out["player_id"], errors="raise").astype(int)
    out["availability_multiplier"] = pd.to_numeric(
        out["availability_multiplier"], errors="raise"
    ).clip(0, 1)
    for idx, row in out.iterrows():
        if str(row["source_tier"]).strip() not in {"official_club", "official_league"}:
            raise ValueError(
                f"manual availability row {idx} must transcribe an official source"
            )
        if not str(row["source_name"]).strip() or not str(row["source_url"]).startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                f"manual availability row {idx} lacks verifiable source provenance"
            )
        if not str(row["relevant_excerpt"]).strip() or not str(row["transcriber"]).strip():
            raise ValueError(
                f"manual availability row {idx} lacks excerpt/transcriber provenance"
            )
        digest = str(row["content_hash"]).strip().casefold()
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ValueError(f"manual availability row {idx} has invalid content_hash")
        published = _utc(row["published_at"], "published_at")
        expires = _utc(row["expires_at"], "expires_at")
        if expires <= published:
            raise ValueError(f"manual availability row {idx} expires before publication")
        if now_utc > expires:
            raise ValueError(f"manual availability row {idx} is expired")
    out["retrieved_at"] = now_utc.isoformat()
    return out.rename(
        columns={
            "source_name": "availability_source_name",
            "source_tier": "availability_source_tier",
            "source_url": "availability_source_url",
            "evidence_type": "availability_evidence_type",
            "published_at": "availability_published_at",
            "expires_at": "availability_expires_at",
            "retrieved_at": "availability_retrieved_at",
        }
    )


def _text(node: ET.Element | None, tags: list[str], default: str = "") -> str:
    if node is None:
        return default
    for tag in tags:
        child = node.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return default


class _OfficialNewsHTMLParser(HTMLParser):
    """Extract article links from official Premier League/news-style HTML pages.

    The parser intentionally ignores arbitrary page copy and keeps only links that
    look like news/article URLs. This makes the fallback useful for official pages
    that do not publish RSS without turning Apex into a broad web scraper.
    """

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.items: list[tuple[str, str]] = []
        self._json_ld = False
        self._json_ld_text: list[str] = []
        self.articles: list[dict] = []

    @staticmethod
    def _article_href(href: str) -> bool:
        path = urlparse(href).path.casefold()
        return any(token in path for token in ("/news/", "/article/", "/articles/"))

    def handle_starttag(self, tag: str, attrs):
        if tag.casefold() == "script":
            attr = {str(k).casefold(): v for k, v in attrs}
            if str(attr.get("type", "")).casefold() == "application/ld+json":
                self._json_ld = True
                self._json_ld_text = []
            return
        if tag.casefold() != "a":
            return
        attr = dict(attrs)
        href = attr.get("href", "")
        if href and self._article_href(href):
            self.current_href = href
            self.current_text = []

    def handle_data(self, data: str):
        if self._json_ld:
            self._json_ld_text.append(data)
            return
        if self.current_href:
            text = " ".join(data.split())
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag: str):
        if tag.casefold() == "script" and self._json_ld:
            self._json_ld = False
            try:
                payload = json.loads("".join(self._json_ld_text))
                nodes = payload.get("@graph", []) if isinstance(payload, dict) else payload
                if isinstance(nodes, dict):
                    nodes = [nodes]
                if isinstance(payload, dict) and not nodes:
                    nodes = [payload]
                for node in nodes if isinstance(nodes, list) else []:
                    kinds = node.get("@type", []) if isinstance(node, dict) else []
                    if isinstance(kinds, str):
                        kinds = [kinds]
                    if any(kind in {"Article", "NewsArticle", "ReportageNewsArticle"} for kind in kinds):
                        self.articles.append(node)
            except (json.JSONDecodeError, TypeError):
                pass
            self._json_ld_text = []
            return
        if tag.casefold() == "a" and self.current_href:
            title = " ".join(self.current_text).strip()
            if len(title) >= 12:
                self.items.append((title, urljoin(self.base_url, self.current_href)))
            self.current_href = None
            self.current_text = []


def _parse_xml(
    content: bytes,
    url: str,
    *,
    source_name: str | None = None,
    source_tier: str = "unknown",
    retrieved_at: str = "",
) -> list[NewsItem]:
    root = ET.fromstring(content)
    source = source_name or urlparse(url).netloc
    channel = root.find("channel")
    items: list[NewsItem] = []
    if channel is not None:
        source = source_name or _text(channel, ["title"], source)
        entries = channel.findall("item")[:60]
        for entry in entries:
            published = _text(entry, ["pubDate"], "") or None
            try:
                published = parsedate_to_datetime(published).isoformat()
            except Exception:
                published = None
            items.append(
                NewsItem(
                    _text(entry, ["title"]),
                    source,
                    published,
                    _text(entry, ["link"]),
                    source_tier,
                    retrieved_at,
                    _text(entry, ["description", "summary"]),
                )
            )
        return items

    ns = {"a": "http://www.w3.org/2005/Atom"}
    source = source_name or _text(root, ["{http://www.w3.org/2005/Atom}title"], source)
    for entry in root.findall("a:entry", ns)[:60]:
        link_node = entry.find("a:link", ns)
        link = link_node.attrib.get("href", "") if link_node is not None else ""
        items.append(
            NewsItem(
                _text(entry, ["{http://www.w3.org/2005/Atom}title"]),
                source,
                _text(
                    entry,
                    [
                        "{http://www.w3.org/2005/Atom}updated",
                        "{http://www.w3.org/2005/Atom}published",
                    ],
                    "",
                ) or None,
                link,
                source_tier,
                retrieved_at,
                _text(
                    entry,
                    [
                        "{http://www.w3.org/2005/Atom}summary",
                        "{http://www.w3.org/2005/Atom}content",
                    ],
                ),
            )
        )
    return items


def _parse_html(
    content: bytes,
    url: str,
    *,
    source_name: str | None = None,
    source_tier: str = "unknown",
    retrieved_at: str = "",
) -> list[NewsItem]:
    parser = _OfficialNewsHTMLParser(url)
    parser.feed(content.decode("utf-8", errors="ignore"))
    source = source_name or (
        "Premier League"
        if "premierleague.com" in urlparse(url).netloc
        else urlparse(url).netloc
    )
    seen: set[tuple[str, str]] = set()
    items: list[NewsItem] = []
    for article in parser.articles:
        title = str(article.get("headline") or article.get("name") or "").strip()
        link_value = article.get("url") or article.get("mainEntityOfPage") or url
        if isinstance(link_value, dict):
            link_value = link_value.get("@id") or link_value.get("url") or url
        link = urljoin(url, str(link_value))
        published = article.get("datePublished") or article.get("dateCreated")
        summary = article.get("articleBody") or article.get("description") or ""
        if title and published:
            key = (title.casefold(), link)
            seen.add(key)
            items.append(
                NewsItem(title, source, str(published), link, source_tier, retrieved_at, str(summary))
            )
    for title, link in parser.items:
        key = (title.casefold(), link)
        if key in seen:
            continue
        seen.add(key)
        # Link-list pages expose retrieval time, not publication time. Unknown
        # publication time is retained as missing and cannot drive projections.
        items.append(NewsItem(title, source, None, link, source_tier, retrieved_at))
        if len(items) >= 80:
            break
    return items


def parse_news_document(
    content: bytes,
    url: str,
    content_type: str = "",
    *,
    source_name: str | None = None,
    source_tier: str = "unknown",
    retrieved_at: str = "",
) -> list[NewsItem]:
    """Parse RSS/Atom, with a narrow official-news HTML fallback."""
    media_type = content_type.partition(";")[0].strip().casefold()
    if media_type in {"text/html", "application/xhtml+xml"}:
        return _parse_html(
            content,
            url,
            source_name=source_name,
            source_tier=source_tier,
            retrieved_at=retrieved_at,
        )

    looks_xml = "xml" in media_type or content.lstrip().startswith(
        (b"<?xml", b"<rss", b"<feed")
    )
    if looks_xml:
        try:
            return _parse_xml(
                content,
                url,
                source_name=source_name,
                source_tier=source_tier,
                retrieved_at=retrieved_at,
            )
        except ET.ParseError:
            pass
    try:
        return _parse_xml(
            content,
            url,
            source_name=source_name,
            source_tier=source_tier,
            retrieved_at=retrieved_at,
        )
    except ET.ParseError:
        return _parse_html(
            content,
            url,
            source_name=source_name,
            source_tier=source_tier,
            retrieved_at=retrieved_at,
        )


def collect_news_sources(sources: list[str | NewsSource | dict]) -> NewsCollectionResult:
    """Collect each configured source independently and preserve outage details.

    One broken media feed must not throw away healthy official/trusted evidence.
    The caller still receives explicit failed-source provenance and can decide how
    strict the production gate should be.
    """
    items: list[NewsItem] = []
    succeeded: list[str] = []
    failed: dict[str, str] = {}
    seen: set[tuple[str, str]] = set()
    for configured in sources:
        if isinstance(configured, NewsSource):
            source = configured
        elif isinstance(configured, dict):
            source = NewsSource(
                name=str(configured.get("name") or configured.get("url") or "unknown"),
                url=str(configured.get("url") or ""),
                tier=str(configured.get("tier") or "unknown"),
            )
        else:
            source = NewsSource(urlparse(str(configured)).netloc, str(configured), "unknown")
        url = source.url
        try:
            retrieved_at = datetime.now(timezone.utc).isoformat()
            response = requests.get(url, timeout=20, headers={"User-Agent": "apex-fpl/0.1"})
            response.raise_for_status()
            parsed = parse_news_document(
                response.content,
                url,
                response.headers.get("content-type", ""),
                source_name=source.name,
                source_tier=source.tier,
                retrieved_at=retrieved_at,
            )
            # Official index pages often expose article links but not publication
            # timestamps. Hydrate a bounded number of those links and accept only
            # structured Article metadata from the destination page.
            if "html" in response.headers.get("content-type", "").casefold():
                hydrated: list[NewsItem] = []
                for candidate in [row for row in parsed if row.published is None][:30]:
                    candidate_url = urlparse(candidate.link)
                    source_url = urlparse(url)
                    if (
                        candidate_url.scheme != "https"
                        or candidate_url.netloc.casefold() != source_url.netloc.casefold()
                    ):
                        continue
                    try:
                        article_response = requests.get(
                            candidate.link,
                            timeout=20,
                            headers={"User-Agent": "apex-fpl/0.1"},
                        )
                        article_response.raise_for_status()
                        hydrated.extend(
                            row
                            for row in parse_news_document(
                                article_response.content,
                                candidate.link,
                                article_response.headers.get("content-type", "text/html"),
                                source_name=source.name,
                                source_tier=source.tier,
                                retrieved_at=retrieved_at,
                            )
                            if row.published is not None
                        )
                    except Exception:
                        continue
                parsed.extend(hydrated)
                parsed.sort(key=lambda row: row.published is None)
            succeeded.append(url)
            for item in parsed:
                key = (item.title.casefold().strip(), item.link)
                if not item.title.strip() or key in seen:
                    continue
                seen.add(key)
                items.append(item)
        except Exception as exc:
            failed[url] = f"{type(exc).__name__}: {exc}"
    if not succeeded:
        details = "; ".join(f"{url}: {err}" for url, err in failed.items())
        raise RuntimeError(f"all configured news sources failed: {details}")
    return NewsCollectionResult(items=items, succeeded=succeeded, failed=failed)


def collect_feed_headlines(urls: list[str]) -> list[NewsItem]:
    """Backwards-compatible convenience wrapper."""
    return collect_news_sources(urls).items
