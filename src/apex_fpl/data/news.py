from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
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
        if str(row["source_tier"]).strip() not in TRUSTED_SOURCE_TIERS:
            raise ValueError(
                f"manual availability row {idx} has untrusted source_tier"
            )
        if not str(row["source_name"]).strip() or not str(row["source_url"]).startswith(
            ("https://", "http://")
        ):
            raise ValueError(
                f"manual availability row {idx} lacks verifiable source provenance"
            )
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

    @staticmethod
    def _article_href(href: str) -> bool:
        path = urlparse(href).path.casefold()
        return "/news/" in path or "/en/news/" in path

    def handle_starttag(self, tag: str, attrs):
        if tag.casefold() != "a":
            return
        attr = dict(attrs)
        href = attr.get("href", "")
        if href and self._article_href(href):
            self.current_href = href
            self.current_text = []

    def handle_data(self, data: str):
        if self.current_href:
            text = " ".join(data.split())
            if text:
                self.current_text.append(text)

    def handle_endtag(self, tag: str):
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
