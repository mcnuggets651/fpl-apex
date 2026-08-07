from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse
import xml.etree.ElementTree as ET

import pandas as pd
import requests


@dataclass
class NewsItem:
    title: str
    source: str
    published: str
    link: str


def load_manual_signals(path: str | Path = "data/manual/availability.csv") -> pd.DataFrame:
    p = Path(path)
    if not p.exists():
        return pd.DataFrame(columns=["player_id", "availability_multiplier", "confidence", "reason"])
    df = pd.read_csv(p)
    required = {"player_id", "availability_multiplier"}
    if not required.issubset(df.columns):
        raise ValueError(f"manual availability file requires {sorted(required)}")
    return df


def _text(node: ET.Element | None, tags: list[str], default: str = "") -> str:
    if node is None:
        return default
    for tag in tags:
        child = node.find(tag)
        if child is not None and child.text:
            return child.text.strip()
    return default


def collect_feed_headlines(urls: list[str]) -> list[NewsItem]:
    """Parse common RSS/Atom feeds using only the Python standard library."""
    items: list[NewsItem] = []
    for url in urls:
        r = requests.get(url, timeout=20, headers={"User-Agent": "apex-fpl/0.1"})
        r.raise_for_status()
        root = ET.fromstring(r.content)
        source = urlparse(url).netloc
        channel = root.find("channel")
        if channel is not None:
            source = _text(channel, ["title"], source)
            entries = channel.findall("item")[:30]
            for e in entries:
                published = _text(e, ["pubDate"], datetime.now(timezone.utc).isoformat())
                try:
                    published = parsedate_to_datetime(published).isoformat()
                except Exception:
                    pass
                items.append(NewsItem(_text(e, ["title"]), source, published, _text(e, ["link"])))
        else:
            ns = {"a": "http://www.w3.org/2005/Atom"}
            source = _text(root, ["{http://www.w3.org/2005/Atom}title"], source)
            for e in root.findall("a:entry", ns)[:30]:
                link_node = e.find("a:link", ns)
                link = link_node.attrib.get("href", "") if link_node is not None else ""
                items.append(NewsItem(
                    _text(e, ["{http://www.w3.org/2005/Atom}title"]),
                    source,
                    _text(e, ["{http://www.w3.org/2005/Atom}updated", "{http://www.w3.org/2005/Atom}published"], datetime.now(timezone.utc).isoformat()),
                    link,
                ))
    return items
