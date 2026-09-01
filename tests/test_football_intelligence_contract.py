from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from apex_fpl.contracts.football_intelligence import (
    CONTRACT_VERSION,
    FootballIntelligenceContractError,
    build_football_intelligence_snapshot,
    write_football_intelligence_snapshot,
)


COMMIT = "1" * 40
NOW = datetime(2026, 9, 1, 7, 0, tzinfo=timezone.utc)


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    report_dir = tmp_path / "reports"
    snapshot_root = tmp_path / "snapshots"
    snapshot_id = "20260901T055500Z-golden01"
    snapshot_dir = snapshot_root / snapshot_id
    report_dir.mkdir(parents=True)
    snapshot_dir.mkdir(parents=True)

    manifest = {
        "snapshot_id": snapshot_id,
        "retrieved_at": "2026-09-01T05:55:00+00:00",
        "players": 2,
        "fixtures": 1,
        "bootstrap_sha256": "a" * 64,
        "fixtures_sha256": "b" * 64,
    }
    bootstrap = {
        "elements": [
            {
                "id": 10,
                "first_name": "Alpha",
                "second_name": "Midfielder",
                "web_name": "Alpha",
                "team": 1,
                "element_type": 3,
            },
            {
                "id": 20,
                "first_name": "Beta",
                "second_name": "Forward",
                "web_name": "Beta",
                "team": 2,
                "element_type": 4,
            },
        ],
        "teams": [{"id": 1, "name": "Home FC"}, {"id": 2, "name": "Away FC"}],
    }
    fixtures = [
        {
            "id": 1001,
            "event": 1,
            "team_h": 1,
            "team_a": 2,
            "kickoff_time": "2026-09-02T19:00:00Z",
        }
    ]
    for name, payload in (
        ("manifest.json", manifest),
        ("bootstrap-static.json", bootstrap),
        ("fixtures.json", fixtures),
    ):
        (snapshot_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    report = {
        "generated_at": "2026-09-01T06:00:00+00:00",
        "gameweeks": [1],
        "safe_to_act": True,
        "full_apex_ready": True,
        "safety": {"blockers": [], "warnings": ["golden fixture warning"]},
        "official_snapshot": manifest,
        "sources": [
            {
                "name": "official_fpl",
                "ok": True,
                "configured": True,
                "version": "official-v1",
                "checked_at": "2026-09-01T05:55:10+00:00",
                "detail": "must not be exported",
            },
            {
                "name": "fpl_core_playerstats",
                "ok": True,
                "configured": True,
                "version": "core-sha",
                "checked_at": "2026-09-01T05:56:00+00:00",
            },
            {
                "name": "market_odds",
                "ok": True,
                "configured": True,
                "version": "market-must-not-leak",
                "checked_at": "2026-09-01T05:57:00+00:00",
            },
            {
                "name": "airsenal",
                "ok": True,
                "configured": True,
                "version": "expert-must-not-leak",
                "checked_at": "2026-09-01T05:58:00+00:00",
            },
        ],
    }
    (report_dir / "latest.json").write_text(json.dumps(report), encoding="utf-8")

    common_player = {
        "status": "a",
        "chance_of_playing_next_round": "100",
        "expected_minutes": "78",
        "start_probability": "0.86",
        "appearance_probability": "0.93",
        "minutes_60_plus_probability": "0.79",
        "minutes_confidence": "0.84",
        "availability_probability": "1.0",
        "tactical_role": "wide_attacker",
        "tactical_role_source": "statistical_inference",
        "role_confidence": "0.72",
        "club_changed": "false",
        "transfer_current_role_evidence": "0.8",
        "penalty_share": "",
        "corners_share": "0.5",
        "direct_freekick_share": "0.2",
        "indirect_freekick_share": "0.3",
        "availability_source_name": "Official Club",
        "availability_source_tier": "official_club",
        "availability_source_url": "https://club.invalid/team-news",
        "availability_evidence_type": "availability",
        "availability_published_at": "2026-09-01T05:00:00+00:00",
        "availability_retrieved_at": "2026-09-01T05:10:00+00:00",
        "availability_expires_at": "2026-09-03T05:00:00+00:00",
        "news_event_type": "role_confirmation",
        "news_source_name": "Official Club",
        "news_source_tier": "official_club",
        "news_source_url": "https://club.invalid/manager",
        "news_published_at": "2026-09-01T04:00:00+00:00",
        "news_retrieved_at": "2026-09-01T04:05:00+00:00",
        "price": "99",
        "projection_confidence": "0.99",
    }
    players = [
        {
            "player_id": 10,
            "web_name": "Alpha",
            "team": 1,
            "team_name": "Home FC",
            "position": "MID",
            **common_player,
        },
        {
            "player_id": 20,
            "web_name": "Beta",
            "team": 2,
            "team_name": "Away FC",
            "position": "FWD",
            **{**common_player, "expected_minutes": "70", "start_probability": "0.75"},
        },
    ]
    _write_csv(report_dir / "players.csv", players)

    projections = [
        {
            "player_id": 10,
            "gw": 1,
            "opponent": 2,
            "is_home": "true",
            "attack_model_xg90": "0.42",
            "attack_model_xa90": "0.31",
            "xg_rate_credibility_adjusted": "false",
            "xa_rate_credibility_adjusted": "true",
            "attack_rate_reliability": "0.88",
            "model_defensive_contribution_per_90": "3.2",
            "defensive_rate_reliability": "0.90",
            "market_xp": "999",
            "canonical_ev_xp": "888",
            "risk_adjusted_xp": "777",
            "airsenal_xp": "666",
            "official_xp": "555",
            "xp": "444",
        },
        {
            "player_id": 20,
            "gw": 1,
            "opponent": 1,
            "is_home": "false",
            "attack_model_xg90": "0.55",
            "attack_model_xa90": "0.12",
            "xg_rate_credibility_adjusted": "false",
            "xa_rate_credibility_adjusted": "false",
            "attack_rate_reliability": "0.95",
            "model_defensive_contribution_per_90": "1.8",
            "defensive_rate_reliability": "0.80",
            "market_xp": "998",
            "canonical_ev_xp": "887",
            "risk_adjusted_xp": "776",
            "airsenal_xp": "665",
            "official_xp": "554",
            "xp": "443",
        },
    ]
    _write_csv(report_dir / "projections.csv", projections)
    return report_dir, snapshot_root


def _build(tmp_path: Path, **kwargs):
    report_dir, snapshot_root = _fixture(tmp_path)
    return build_football_intelligence_snapshot(
        report_dir,
        snapshot_root,
        producer_commit_sha=COMMIT,
        season="2026/27",
        now=NOW,
        **kwargs,
    )


def test_golden_contract_is_deterministic_and_market_independent(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    first = build_football_intelligence_snapshot(
        report_dir,
        snapshot_root,
        producer_commit_sha=COMMIT,
        season="2026/27",
        now=NOW,
    )
    second = build_football_intelligence_snapshot(
        report_dir,
        snapshot_root,
        producer_commit_sha=COMMIT,
        season="2026/27",
        now=NOW,
    )
    assert first == second
    assert first["payload"]["schema_version"] == CONTRACT_VERSION
    assert first["payload"]["rollout_mode"] == "SHADOW_RESEARCH_ONLY"
    assert len(first["payload"]["players"]) == 2
    assert len(first["payload"]["fixtures"]) == 1
    assert first["payload"]["capabilities"]["fpl_expected_points"] is False
    assert first["payload"]["capabilities"]["betting_probability"] is False

    serialized = json.dumps(first, sort_keys=True)
    for forbidden in (
        "market_xp",
        "canonical_ev_xp",
        "risk_adjusted_xp",
        "airsenal_xp",
        "official_xp",
        "market-must-not-leak",
        "expert-must-not-leak",
        "https://club.invalid",
    ):
        assert forbidden not in serialized


def test_market_and_ensemble_changes_do_not_change_snapshot(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    before = build_football_intelligence_snapshot(
        report_dir,
        snapshot_root,
        producer_commit_sha=COMMIT,
        season="2026/27",
        now=NOW,
    )
    rows = list(csv.DictReader((report_dir / "projections.csv").open(encoding="utf-8")))
    for row in rows:
        row["market_xp"] = "1.234567"
        row["canonical_ev_xp"] = "2.345678"
        row["risk_adjusted_xp"] = "3.456789"
        row["airsenal_xp"] = "4.567890"
        row["official_xp"] = "5.678901"
        row["xp"] = "6.789012"
    _write_csv(report_dir / "projections.csv", rows)
    after = build_football_intelligence_snapshot(
        report_dir,
        snapshot_root,
        producer_commit_sha=COMMIT,
        season="2026/27",
        now=NOW,
    )
    assert before == after


def test_stale_report_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FootballIntelligenceContractError, match="stale"):
        _build(tmp_path, max_age_hours=0.5)


def test_future_report_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    report = json.loads((report_dir / "latest.json").read_text())
    report["generated_at"] = "2026-09-02T06:00:00+00:00"
    (report_dir / "latest.json").write_text(json.dumps(report))
    with pytest.raises(FootballIntelligenceContractError, match="future-dated"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_snapshot_manifest_mismatch_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    report = json.loads((report_dir / "latest.json").read_text())
    report["official_snapshot"]["bootstrap_sha256"] = "c" * 64
    (report_dir / "latest.json").write_text(json.dumps(report))
    with pytest.raises(FootballIntelligenceContractError, match="disagrees"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_duplicate_player_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    rows = list(csv.DictReader((report_dir / "players.csv").open(encoding="utf-8")))
    rows.append(dict(rows[0]))
    _write_csv(report_dir / "players.csv", rows)
    with pytest.raises(FootballIntelligenceContractError, match="duplicate"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_wrong_club_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    rows = list(csv.DictReader((report_dir / "players.csv").open(encoding="utf-8")))
    rows[0]["team"] = "2"
    _write_csv(report_dir / "players.csv", rows)
    with pytest.raises(FootballIntelligenceContractError, match="club mismatch"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("expected_minutes", "91", "expected_minutes"),
        ("start_probability", "1.1", "start_probability"),
        ("appearance_probability", "0.5", "start_probability exceeds"),
        ("minutes_60_plus_probability", "0.99", "60\\+ probability exceeds"),
    ],
)
def test_impossible_minute_inputs_fail_closed(
    tmp_path: Path, field: str, value: str, message: str
) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    rows = list(csv.DictReader((report_dir / "players.csv").open(encoding="utf-8")))
    rows[0][field] = value
    _write_csv(report_dir / "players.csv", rows)
    with pytest.raises(FootballIntelligenceContractError, match=message):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_duplicate_projection_fixture_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    rows = list(csv.DictReader((report_dir / "projections.csv").open(encoding="utf-8")))
    rows.append(dict(rows[0]))
    _write_csv(report_dir / "projections.csv", rows)
    with pytest.raises(FootballIntelligenceContractError, match="duplicate player/fixture"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_fixture_mismatch_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    rows = list(csv.DictReader((report_dir / "projections.csv").open(encoding="utf-8")))
    rows[0]["opponent"] = "999"
    _write_csv(report_dir / "projections.csv", rows)
    with pytest.raises(FootballIntelligenceContractError, match="official fixture"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_missing_critical_projection_column_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    rows = list(csv.DictReader((report_dir / "projections.csv").open(encoding="utf-8")))
    for row in rows:
        row.pop("attack_model_xg90")
    _write_csv(report_dir / "projections.csv", rows)
    with pytest.raises(FootballIntelligenceContractError, match="missing required columns"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_future_news_evidence_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    rows = list(csv.DictReader((report_dir / "players.csv").open(encoding="utf-8")))
    rows[0]["news_published_at"] = "2026-09-01T08:00:00+00:00"
    _write_csv(report_dir / "players.csv", rows)
    with pytest.raises(FootballIntelligenceContractError, match="future-dated"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha=COMMIT,
            season="2026/27",
            now=NOW,
        )


def test_unsupported_commit_identity_fails_closed(tmp_path: Path) -> None:
    report_dir, snapshot_root = _fixture(tmp_path)
    with pytest.raises(FootballIntelligenceContractError, match="40-char"):
        build_football_intelligence_snapshot(
            report_dir,
            snapshot_root,
            producer_commit_sha="main",
            season="2026/27",
            now=NOW,
        )


def test_write_is_hash_checked_and_write_once(tmp_path: Path) -> None:
    snapshot = _build(tmp_path)
    output = tmp_path / "artifact.json"
    write_football_intelligence_snapshot(snapshot, output)
    assert output.is_file()
    with pytest.raises(FootballIntelligenceContractError, match="refusing to overwrite"):
        write_football_intelligence_snapshot(snapshot, output)

    tampered = json.loads(json.dumps(snapshot))
    tampered["payload"]["competition"]["name"] = "Tampered"
    with pytest.raises(FootballIntelligenceContractError, match="payload hash"):
        write_football_intelligence_snapshot(tampered, tmp_path / "tampered.json")
