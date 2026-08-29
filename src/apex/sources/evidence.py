from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
import yaml

from apex.domain.models import EvidenceEffect, EvidenceRecord, dataclass_to_dict
from apex.sources.official import fetch_official_snapshot

HARD_SOURCE_TIERS = frozenset({"official_club", "official_league"})
TRUSTED_SOURCE_TIERS = HARD_SOURCE_TIERS | frozenset({"trusted_media"})
STRONG_ABSENCE = re.compile(
    r"\b(ruled out|will miss|suspended|suspension|not available|unavailable|"
    r"out for (?:the )?(?:match|game|weekend)|long[- ]term (?:injury|absence))\b",
    re.I,
)
DECISION_RELEVANT = re.compile(
    r"\b(injur(?:y|ed)|doubtful|fitness doubt|late fitness test|"
    r"return(?:s|ed)? to training|back in training|fit again|available|"
    r"will start|set to start|unlikely to start|will not start|"
    r"penalt(?:y|ies)|corners|free[- ]kicks|set pieces|"
    r"transfer|set to leave|expected to leave)\b",
    re.I,
)
OFFICIAL_HARD_STATUSES = frozenset({"s", "u"})
OFFICIAL_RISK_STATUSES = frozenset({"d", "i", "n", "s", "u"})


@dataclass(frozen=True)
class EvidenceSource:
    name: str
    url: str
    tier: str
    required: bool = False


@dataclass(frozen=True)
class SourceOutcome:
    name: str
    url: str
    tier: str
    required: bool
    status: str
    item_count: int
    record_count: int
    error: str | None = None


@dataclass(frozen=True)
class EvidenceAcquisitionResult:
    records: tuple[EvidenceRecord, ...]
    manifest: dict
    records_path: Path
    manifest_path: Path


def _utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        dt = value
    else:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _canonical_hash(payload) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_json(path: Path, payload) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def load_evidence_sources(path: str | Path) -> tuple[EvidenceSource, ...]:
    source_path = Path(path)
    payload = yaml.safe_load(source_path.read_text(encoding="utf-8")) or {}
    raw = payload.get("feeds") or []
    sources = tuple(
        EvidenceSource(
            name=str(row["name"]),
            url=str(row["url"]),
            tier=str(row["tier"]),
            required=bool(row.get("required", False)),
        )
        for row in raw
    )
    if not sources:
        raise RuntimeError("external evidence source configuration is empty")
    if not any(source.tier in HARD_SOURCE_TIERS for source in sources):
        raise RuntimeError("external evidence requires at least one official source tier")
    for source in sources:
        if source.tier not in TRUSTED_SOURCE_TIERS:
            raise RuntimeError(
                f"unsupported evidence source tier for {source.name}: {source.tier}"
            )
        if not source.url.startswith(("https://", "http://")):
            raise RuntimeError(f"invalid evidence source URL for {source.name}")
    return sources


def _target_gameweek(official, now: datetime) -> tuple[int, datetime]:
    future = []
    for gameweek, value in official.deadlines.items():
        deadline = _utc(value)
        if deadline > now:
            future.append((int(gameweek), deadline))
    if not future:
        raise RuntimeError("no future Official FPL deadline for evidence acquisition")
    return min(future, key=lambda row: row[0])


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _utc(value)
    except Exception:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return None


class _LinkParser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.href: str | None = None
        self.text: list[str] = []
        self.items: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs):
        if tag.casefold() != "a":
            return
        href = dict(attrs).get("href")
        if href:
            self.href = str(href)
            self.text = []

    def handle_data(self, data: str):
        if self.href:
            text = " ".join(data.split())
            if text:
                self.text.append(text)

    def handle_endtag(self, tag: str):
        if tag.casefold() == "a" and self.href:
            title = " ".join(self.text).strip()
            link = urljoin(self.base_url, self.href)
            if len(title) >= 12 and urlparse(link).scheme in {"http", "https"}:
                self.items.append((title, link))
            self.href = None
            self.text = []


def _parse_document(content: bytes, content_type: str, base_url: str) -> list[dict]:
    media_type = content_type.partition(";")[0].casefold().strip()
    looks_xml = "xml" in media_type or content.lstrip().startswith(
        (b"<?xml", b"<rss", b"<feed")
    )
    if looks_xml:
        try:
            root = ET.fromstring(content)
            channel = root.find("channel")
            out: list[dict] = []
            if channel is not None:
                for item in channel.findall("item")[:80]:
                    title = (item.findtext("title") or "").strip()
                    link = (item.findtext("link") or "").strip()
                    published = (item.findtext("pubDate") or "").strip() or None
                    summary = (
                        item.findtext("description")
                        or item.findtext("summary")
                        or ""
                    ).strip()
                    out.append(
                        {
                            "title": title,
                            "link": link,
                            "published": published,
                            "summary": re.sub(r"<[^>]+>", " ", summary),
                        }
                    )
                return out
            atom = "{http://www.w3.org/2005/Atom}"
            for entry in root.findall(f"{atom}entry")[:80]:
                link_node = entry.find(f"{atom}link")
                out.append(
                    {
                        "title": (entry.findtext(f"{atom}title") or "").strip(),
                        "link": (
                            str(link_node.attrib.get("href") or "")
                            if link_node is not None
                            else ""
                        ),
                        "published": (
                            entry.findtext(f"{atom}published")
                            or entry.findtext(f"{atom}updated")
                            or None
                        ),
                        "summary": re.sub(
                            r"<[^>]+>",
                            " ",
                            (
                                entry.findtext(f"{atom}summary")
                                or entry.findtext(f"{atom}content")
                                or ""
                            ),
                        ),
                    }
                )
            return out
        except ET.ParseError:
            pass

    parser = _LinkParser(base_url)
    parser.feed(content.decode("utf-8", errors="ignore"))
    return [
        {"title": title, "link": link, "published": None, "summary": ""}
        for title, link in parser.items[:120]
    ]


def _aliases(raw_bootstrap: dict) -> tuple[dict[int, tuple[str, ...]], dict[str, set[int]]]:
    by_id: dict[int, tuple[str, ...]] = {}
    owners: dict[str, set[int]] = {}
    for row in raw_bootstrap.get("elements", []):
        element_id = int(row["id"])
        values = []
        full = " ".join(
            part.strip()
            for part in (
                str(row.get("first_name") or ""),
                str(row.get("second_name") or ""),
            )
            if part.strip()
        )
        for value in (full, row.get("web_name"), row.get("second_name")):
            text = str(value or "").strip()
            if len(text) >= 4 and text.casefold() not in {v.casefold() for v in values}:
                values.append(text)
                owners.setdefault(text.casefold(), set()).add(element_id)
        by_id[element_id] = tuple(values)
    return by_id, owners


def _record(
    *,
    element_id: int,
    source_name: str,
    source_url: str,
    source_tier: str,
    published_at: datetime,
    retrieved_at: datetime,
    expires_at: datetime,
    evidence_type: str,
    gameweek: int,
    effect: EvidenceEffect,
    excerpt: str,
    content_payload: dict,
) -> EvidenceRecord:
    content_hash = _canonical_hash(content_payload)
    evidence_id = _canonical_hash(
        {
            "element_id": element_id,
            "source_url": source_url,
            "gameweek": gameweek,
            "effect": effect.value,
            "content_hash": content_hash,
        }
    )[:32]
    return EvidenceRecord(
        evidence_id=evidence_id,
        element_id=int(element_id),
        source_name=source_name,
        source_url=source_url,
        source_tier=source_tier,
        published_at=published_at.isoformat(),
        retrieved_at=retrieved_at.isoformat(),
        expires_at=expires_at.isoformat(),
        evidence_type=evidence_type,
        gameweek=int(gameweek),
        effect=effect,
        content_hash=content_hash,
        excerpt=" ".join(excerpt.split())[:240],
    )


def _official_fpl_records(
    raw_bootstrap: dict,
    *,
    official,
    target_gameweek: int,
    deadline: datetime,
    retrieved_at: datetime,
) -> list[EvidenceRecord]:
    records = []
    for row in raw_bootstrap.get("elements", []):
        element_id = int(row["id"])
        status = str(row.get("status") or "").casefold()
        chance = row.get("chance_of_playing_this_round")
        news = str(row.get("news") or "").strip()
        if status == "a" and chance in (None, 100) and not news:
            continue

        hard = status in OFFICIAL_HARD_STATUSES or (
            chance is not None
            and int(chance) == 0
            and status in OFFICIAL_RISK_STATUSES
        )
        effect = EvidenceEffect.HARD_EXCLUDE if hard else EvidenceEffect.AUDIT_ONLY
        published = _parse_published(row.get("news_added")) or retrieved_at
        expires = deadline
        if expires <= published:
            expires = published + timedelta(hours=24)
        excerpt = news or (
            f"Official FPL availability status={status or 'unknown'}, "
            f"chance_of_playing_this_round={chance}"
        )
        records.append(
            _record(
                element_id=element_id,
                source_name="Official Fantasy Premier League",
                source_url="https://fantasy.premierleague.com/api/bootstrap-static/",
                source_tier="official_league",
                published_at=published,
                retrieved_at=retrieved_at,
                expires_at=expires,
                evidence_type="official_fpl_availability",
                gameweek=target_gameweek,
                effect=effect,
                excerpt=excerpt,
                content_payload={
                    "official_source_hash": official.source_hash,
                    "element_id": element_id,
                    "status": status,
                    "chance_of_playing_this_round": chance,
                    "news": news,
                    "news_added": row.get("news_added"),
                },
            )
        )
    return records


def _claim_segments(text: str) -> tuple[str, ...]:
    """Return conservative sentence/claim segments for player attribution.

    A decisive phrase in one sentence must never be inherited by another player
    merely because that player's name appears elsewhere in the same article or
    feed summary. Semicolons and line breaks are also treated as claim boundaries
    because football round-ups commonly join unrelated availability updates with
    them.
    """
    segments = re.split(r"(?<=[.!?])\s+|[;\n]+", text)
    return tuple(segment.strip() for segment in segments if segment.strip())


def _attributable_text(text: str, matched_names: list[str]) -> str:
    segments = [
        segment
        for segment in _claim_segments(text)
        if any(
            re.search(rf"(?<!\w){re.escape(name)}(?!\w)", segment, re.I)
            for name in matched_names
        )
    ]
    return " ".join(segments)


def _external_records(
    *,
    source: EvidenceSource,
    items: list[dict],
    aliases: dict[int, tuple[str, ...]],
    alias_owners: dict[str, set[int]],
    target_gameweek: int,
    deadline: datetime,
    retrieved_at: datetime,
) -> list[EvidenceRecord]:
    records = []
    for item in items:
        published = _parse_published(item.get("published"))
        if published is None:
            continue
        if retrieved_at - published > timedelta(days=14):
            continue
        title = str(item.get("title") or "")
        summary = re.sub(r"<[^>]+>", " ", str(item.get("summary") or ""))
        text = " ".join((title, summary)).strip()
        if not text or not (
            STRONG_ABSENCE.search(text) or DECISION_RELEVANT.search(text)
        ):
            continue
        link = str(item.get("link") or source.url)
        if not link.startswith(("https://", "http://")):
            link = source.url

        for element_id, names in aliases.items():
            matched = [
                name
                for name in names
                if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", text, re.I)
            ]
            if not matched:
                continue
            if not any(len(alias_owners[name.casefold()]) == 1 for name in matched):
                continue
            attributable = _attributable_text(text, matched)
            if not attributable or not (
                STRONG_ABSENCE.search(attributable)
                or DECISION_RELEVANT.search(attributable)
            ):
                continue
            strong = bool(STRONG_ABSENCE.search(attributable))
            effect = (
                EvidenceEffect.HARD_EXCLUDE
                if strong and source.tier in HARD_SOURCE_TIERS
                else EvidenceEffect.AUDIT_ONLY
            )
            expires = min(deadline, published + timedelta(days=7))
            if expires <= retrieved_at:
                continue
            excerpt = attributable
            records.append(
                _record(
                    element_id=element_id,
                    source_name=source.name,
                    source_url=link,
                    source_tier=source.tier,
                    published_at=published,
                    retrieved_at=retrieved_at,
                    expires_at=expires,
                    evidence_type=(
                        "explicit_absence"
                        if strong
                        else "decision_relevant_news"
                    ),
                    gameweek=target_gameweek,
                    effect=effect,
                    excerpt=excerpt,
                    content_payload={
                        "title": title,
                        "attributable_text": attributable[:500],
                        "link": link,
                        "published": published.isoformat(),
                        "source_tier": source.tier,
                        "element_id": element_id,
                    },
                )
            )
    return records


def collect_v2_evidence(
    *,
    sources_path: str | Path,
    records_path: str | Path,
    manifest_path: str | Path,
    expected_official_hash: str | None = None,
    season: str = "2026-2027",
    session: requests.Session | None = None,
    now: datetime | None = None,
) -> EvidenceAcquisitionResult:
    retrieved_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    http = session or requests.Session()
    official, raw = fetch_official_snapshot(
        season=season,
        session=http,
    )
    if expected_official_hash and official.source_hash != expected_official_hash:
        raise RuntimeError(
            "Official FPL authority changed before evidence acquisition: "
            f"expected {expected_official_hash}, got {official.source_hash}"
        )
    target_gameweek, deadline = _target_gameweek(official, retrieved_at)
    bootstrap = raw.get("bootstrap") or {}
    aliases, alias_owners = _aliases(bootstrap)
    sources = load_evidence_sources(sources_path)

    records: list[EvidenceRecord] = _official_fpl_records(
        bootstrap,
        official=official,
        target_gameweek=target_gameweek,
        deadline=deadline,
        retrieved_at=retrieved_at,
    )
    outcomes: list[SourceOutcome] = []
    headers = {"User-Agent": "fpl-apex-v2/1"}
    for source in sources:
        try:
            response = http.get(source.url, timeout=20, headers=headers)
            response.raise_for_status()
            items = _parse_document(
                response.content,
                response.headers.get("content-type", ""),
                source.url,
            )
            source_records = _external_records(
                source=source,
                items=items,
                aliases=aliases,
                alias_owners=alias_owners,
                target_gameweek=target_gameweek,
                deadline=deadline,
                retrieved_at=retrieved_at,
            )
            records.extend(source_records)
            usable = bool(items)
            outcomes.append(
                SourceOutcome(
                    source.name,
                    source.url,
                    source.tier,
                    source.required,
                    "SUCCESS" if usable else "EMPTY",
                    len(items),
                    len(source_records),
                    None if usable else "no parseable evidence items returned",
                )
            )
        except Exception as exc:
            outcomes.append(
                SourceOutcome(
                    source.name,
                    source.url,
                    source.tier,
                    source.required,
                    "FAILED",
                    0,
                    0,
                    f"{type(exc).__name__}: {exc}",
                )
            )

    deduped = {record.evidence_id: record for record in records}
    ordered = tuple(deduped[key] for key in sorted(deduped))
    required_failures = [
        outcome.name
        for outcome in outcomes
        if outcome.required and outcome.status != "SUCCESS"
    ]
    completed = not required_failures
    source_config_sha = hashlib.sha256(Path(sources_path).read_bytes()).hexdigest()
    manifest = {
        "schema_version": 1,
        "completed": completed,
        "season": season,
        "target_gameweek": target_gameweek,
        "deadline": deadline.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "expected_official_hash": expected_official_hash,
        "observed_official_hash": official.source_hash,
        "source_config_sha256": source_config_sha,
        "sources": [dataclass_to_dict(outcome) for outcome in outcomes],
        "required_source_failures": required_failures,
        "record_count": len(ordered),
        "hard_exclude_count": sum(
            record.effect == EvidenceEffect.HARD_EXCLUDE for record in ordered
        ),
        "audit_only_count": sum(
            record.effect == EvidenceEffect.AUDIT_ONLY for record in ordered
        ),
        "official_fpl_record_count": sum(
            record.evidence_type == "official_fpl_availability" for record in ordered
        ),
    }
    records_file = _write_json(
        Path(records_path),
        {
            "schema_version": 1,
            "records": [dataclass_to_dict(record) for record in ordered],
        },
    )
    manifest_file = _write_json(Path(manifest_path), manifest)

    if not completed:
        raise RuntimeError(
            "required external evidence source failed: "
            + ", ".join(required_failures)
        )
    return EvidenceAcquisitionResult(
        ordered,
        manifest,
        records_file,
        manifest_file,
    )
