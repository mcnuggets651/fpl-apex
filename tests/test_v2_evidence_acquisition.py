from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
import requests

from apex.domain.models import EvidenceEffect, OfficialPlayer, OfficialSnapshot, Position
from apex.runtime import acquire as acquire_module
from apex.sources import evidence as evidence_module


class FakeResponse:
    def __init__(self, content: bytes, content_type: str = "application/rss+xml"):
        self.content = content
        self.headers = {"content-type": content_type}

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self, responses: dict[str, FakeResponse | Exception]):
        self.responses = responses

    def get(self, url, **kwargs):
        del kwargs
        result = self.responses[url]
        if isinstance(result, Exception):
            raise result
        return result


def _official(*, status="a", chance=100, news=""):
    player = OfficialPlayer(
        element_id=1,
        web_name="Player One",
        team_id=1,
        position=Position.MID,
        price_tenths=50,
        status=status,
        can_transact=True,
        fpl_code=1001,
    )
    official = OfficialSnapshot(
        schema_version=1,
        season="2026-2027",
        acquired_at="2026-08-29T08:00:00+00:00",
        source_hash="stable-hash",
        players=(player,),
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
                    "status": status,
                    "chance_of_playing_this_round": chance,
                    "news": news,
                    "news_added": "2026-08-29T07:00:00Z" if news else None,
                }
            ]
        },
        "fixtures": [],
    }
    return official, raw


def _sources(path: Path, rows: list[dict]) -> Path:
    lines = ["feeds:"]
    for row in rows:
        lines.extend(
            [
                f"  - name: {row['name']}",
                f"    url: {row['url']}",
                f"    tier: {row['tier']}",
                f"    required: {'true' if row.get('required') else 'false'}",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _rss(title: str | None = None) -> bytes:
    # A healthy required source must now contain at least one parseable item.
    # The default item is intentionally football-generic so it proves source
    # usability without creating decision-relevant player evidence.
    title = title or "General football roundup and weekend preview"
    item = f"""
    <item>
      <title>{title}</title>
      <link>https://example.test/article</link>
      <pubDate>Sat, 29 Aug 2026 07:30:00 GMT</pubDate>
      <description>{title}</description>
    </item>
    """
    return f"<rss><channel><title>Feed</title>{item}</channel></rss>".encode()


def test_official_fpl_zero_chance_injury_is_hard_exclusion(monkeypatch, tmp_path):
    official, raw = _official(
        status="i",
        chance=0,
        news="Hamstring injury - Expected back 20 Sep",
    )
    monkeypatch.setattr(
        evidence_module,
        "fetch_official_snapshot",
        lambda **kwargs: (official, raw),
    )
    source_url = "https://official.test/news"
    sources = _sources(
        tmp_path / "sources.yaml",
        [
            {
                "name": "Official League",
                "url": source_url,
                "tier": "official_league",
                "required": True,
            }
        ],
    )
    result = evidence_module.collect_v2_evidence(
        sources_path=sources,
        records_path=tmp_path / "hard.json",
        manifest_path=tmp_path / "manifest.json",
        expected_official_hash="stable-hash",
        session=FakeSession({source_url: FakeResponse(_rss())}),
        now=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
    )
    official_rows = [
        row for row in result.records
        if row.evidence_type == "official_fpl_availability"
    ]
    assert len(official_rows) == 1
    assert official_rows[0].effect == EvidenceEffect.HARD_EXCLUDE
    assert result.manifest["completed"] is True


def test_trusted_media_explicit_absence_remains_audit_only(monkeypatch, tmp_path):
    official, raw = _official()
    monkeypatch.setattr(
        evidence_module,
        "fetch_official_snapshot",
        lambda **kwargs: (official, raw),
    )
    official_url = "https://official.test/news"
    media_url = "https://media.test/rss"
    sources = _sources(
        tmp_path / "sources.yaml",
        [
            {
                "name": "Official League",
                "url": official_url,
                "tier": "official_league",
                "required": True,
            },
            {
                "name": "Trusted Media",
                "url": media_url,
                "tier": "trusted_media",
                "required": False,
            },
        ],
    )
    result = evidence_module.collect_v2_evidence(
        sources_path=sources,
        records_path=tmp_path / "hard.json",
        manifest_path=tmp_path / "manifest.json",
        expected_official_hash="stable-hash",
        session=FakeSession(
            {
                official_url: FakeResponse(_rss()),
                media_url: FakeResponse(_rss("Player One ruled out for weekend")),
            }
        ),
        now=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
    )
    media_rows = [
        row for row in result.records
        if row.source_name == "Trusted Media"
    ]
    assert len(media_rows) == 1
    assert media_rows[0].effect == EvidenceEffect.AUDIT_ONLY


def test_official_explicit_absence_can_hard_exclude(monkeypatch, tmp_path):
    official, raw = _official()
    monkeypatch.setattr(
        evidence_module,
        "fetch_official_snapshot",
        lambda **kwargs: (official, raw),
    )
    official_url = "https://official.test/news"
    sources = _sources(
        tmp_path / "sources.yaml",
        [
            {
                "name": "Official League",
                "url": official_url,
                "tier": "official_league",
                "required": True,
            }
        ],
    )
    result = evidence_module.collect_v2_evidence(
        sources_path=sources,
        records_path=tmp_path / "hard.json",
        manifest_path=tmp_path / "manifest.json",
        expected_official_hash="stable-hash",
        session=FakeSession(
            {
                official_url: FakeResponse(
                    _rss("Player One will miss the weekend")
                )
            }
        ),
        now=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
    )
    external = [
        row for row in result.records
        if row.source_name == "Official League"
    ]
    assert len(external) == 1
    assert external[0].effect == EvidenceEffect.HARD_EXCLUDE


def test_multi_player_article_does_not_cross_assign_absence_claim():
    source = evidence_module.EvidenceSource(
        "Official League",
        "https://official.test/news",
        "official_league",
        True,
    )
    records = evidence_module._external_records(
        source=source,
        items=[
            {
                "title": "Player One ruled out for weekend. Player Two will start.",
                "summary": "",
                "link": "https://official.test/article",
                "published": "Sat, 29 Aug 2026 07:30:00 GMT",
            }
        ],
        aliases={1: ("Player One",), 2: ("Player Two",)},
        alias_owners={"player one": {1}, "player two": {2}},
        target_gameweek=3,
        deadline=datetime(2026, 9, 12, 10, 0, tzinfo=timezone.utc),
        retrieved_at=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
    )
    by_id = {row.element_id: row for row in records}
    assert by_id[1].effect == EvidenceEffect.HARD_EXCLUDE
    assert by_id[1].excerpt == "Player One ruled out for weekend."
    assert by_id[2].effect == EvidenceEffect.AUDIT_ONLY
    assert by_id[2].excerpt == "Player Two will start."


def test_required_official_source_failure_writes_failed_manifest(
    monkeypatch,
    tmp_path,
):
    official, raw = _official()
    monkeypatch.setattr(
        evidence_module,
        "fetch_official_snapshot",
        lambda **kwargs: (official, raw),
    )
    official_url = "https://official.test/news"
    sources = _sources(
        tmp_path / "sources.yaml",
        [
            {
                "name": "Official League",
                "url": official_url,
                "tier": "official_league",
                "required": True,
            }
        ],
    )
    manifest = tmp_path / "manifest.json"
    with pytest.raises(RuntimeError, match="required external evidence source failed"):
        evidence_module.collect_v2_evidence(
            sources_path=sources,
            records_path=tmp_path / "hard.json",
            manifest_path=manifest,
            expected_official_hash="stable-hash",
            session=FakeSession(
                {official_url: requests.ConnectionError("feed unavailable")}
            ),
            now=datetime(2026, 8, 29, 8, 0, tzinfo=timezone.utc),
        )
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["completed"] is False
    assert payload["required_source_failures"] == ["Official League"]


def test_required_evidence_failure_has_stable_acquisition_stage(
    monkeypatch,
    tmp_path,
):
    config = tmp_path / "apex_v2.yaml"
    config.write_text(
        "\n".join(
            (
                "season: '2026-2027'",
                "entry_id: 63984",
                "max_horizon: 1",
                "snapshot_dir: snapshots",
                "evidence:",
                "  required: true",
                "  sources_path: sources.yaml",
                "  records_path: acquisition/evidence/hard.json",
                "  manifest_path: acquisition/evidence/acquisition.json",
                "providers: []",
                "",
            )
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        acquire_module,
        "collect_v2_evidence",
        lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("official evidence unavailable")
        ),
    )
    with pytest.raises(acquire_module.AcquisitionStageError) as observed:
        acquire_module.acquire_and_freeze(
            config,
            run_id="run-evidence-failure",
            code_sha="abc",
            run_started_at="2026-08-29T07:59:00+00:00",
            workdir=tmp_path,
            expected_official_hash="stable-hash",
        )
    assert observed.value.stage == "external_evidence"
    assert observed.value.cause_message == "official evidence unavailable"
