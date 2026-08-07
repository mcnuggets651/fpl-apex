from apex_fpl.services.readiness import evaluate_report


def _payload():
    squad = [{"player_id": i} for i in range(15)]
    xi = [{"player_id": i} for i in range(11)]
    scenario = {
        "status": "Optimal",
        "squad": squad,
        "xi": xi,
        "captain": [{"player_id": 1}],
        "vice_captain": [{"player_id": 2}],
    }
    sources = [
        {"name": name, "ok": True, "configured": True}
        for name in ("official_fpl", "fpl_core_playerstats", "airsenal", "news_feeds")
    ]
    return {
        "safe_to_act": True,
        "full_apex_ready": True,
        "official_snapshot": {
            "snapshot_id": "20260807T070000Z-test",
            "retrieved_at": "2026-08-07T07:00:00+00:00",
            "bootstrap_sha256": "a" * 64,
            "fixtures_sha256": "b" * 64,
        },
        "sources": sources,
        "scenarios": {
            "unrestricted": dict(scenario),
            "haaland": dict(scenario),
            "no-haaland": dict(scenario),
        },
    }


def test_ready_report_passes():
    result = evaluate_report(_payload())
    assert result.ready
    assert result.blockers == ()


def test_missing_genuine_airsenal_blocks_report():
    payload = _payload()
    for row in payload["sources"]:
        if row["name"] == "airsenal":
            row["configured"] = False
    payload["full_apex_ready"] = False
    payload["safe_to_act"] = False
    result = evaluate_report(payload)
    assert not result.ready
    assert any("airsenal" in blocker for blocker in result.blockers)


def test_missing_vice_captain_blocks_report():
    payload = _payload()
    payload["scenarios"]["haaland"]["vice_captain"] = []
    result = evaluate_report(payload)
    assert not result.ready
    assert any("vice-captain" in blocker for blocker in result.blockers)
