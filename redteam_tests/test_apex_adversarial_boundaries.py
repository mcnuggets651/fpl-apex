from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd

from apex_fpl.data.official import OfficialSnapshot
from apex_fpl.optimisation.mechanics import best_captain_vice_ids
from apex_fpl.optimisation.squad import optimise_squad
from apex_fpl.services.data_quality import _fixture_surface_check, _projection_surface_check
from apex_fpl.services.pipeline import _decision_gameweeks
from apex_fpl.services.provenance import SourceStatus, validate_core_pin
from apex_fpl.services.readiness import REQUIRED_SCENARIOS, REQUIRED_SOURCES, evaluate_report
from apex_fpl.services.safety import assess_safety


def _snapshot(retrieved_at: str) -> OfficialSnapshot:
    return OfficialSnapshot(
        players=pd.DataFrame({"player_id": [1], "position": ["MID"]}),
        teams=pd.DataFrame(),
        fixtures=pd.DataFrame(),
        events=pd.DataFrame(),
        raw_bootstrap={},
        raw_fixtures=[],
        retrieved_at=retrieved_at,
        bootstrap_sha256="a" * 64,
        fixtures_sha256="b" * 64,
    )


def _healthy_sources() -> list[SourceStatus]:
    return [SourceStatus(name=name, ok=True, configured=True) for name in REQUIRED_SOURCES]


def _ready_payload() -> dict:
    scenario = {
        "status": "Optimal",
        "squad": list(range(1, 16)),
        "xi": list(range(1, 12)),
        "captain": [1],
        "vice_captain": [2],
    }
    return {
        "safe_to_act": True,
        "full_apex_ready": True,
        "data_quality": {"ready": True},
        "official_snapshot": {
            "snapshot_id": "s1",
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
            "bootstrap_sha256": "a" * 64,
            "fixtures_sha256": "b" * 64,
        },
        "sources": [
            {"name": name, "configured": True, "ok": True}
            for name in REQUIRED_SOURCES
        ],
        "scenarios": {name: dict(scenario) for name in REQUIRED_SCENARIOS},
    }


def test_safety_fails_closed_when_official_timestamp_missing() -> None:
    result = assess_safety(
        _snapshot(""),
        _healthy_sources(),
        pd.DataFrame(),
        pd.DataFrame({"player_id": [1], "gw": [1], "xp": [1.0]}),
        {"unrestricted": SimpleNamespace(status="Optimal")},
        list(REQUIRED_SOURCES),
    )
    assert result.safe_to_act is False
    assert any("timestamp" in row.lower() or "retrieved" in row.lower() for row in result.blockers)


def test_safety_rejects_far_future_official_timestamp() -> None:
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    result = assess_safety(
        _snapshot(future),
        _healthy_sources(),
        pd.DataFrame(),
        pd.DataFrame({"player_id": [1], "gw": [1], "xp": [1.0]}),
        {"unrestricted": SimpleNamespace(status="Optimal")},
        list(REQUIRED_SOURCES),
    )
    assert result.safe_to_act is False


def test_safety_handles_naive_timestamp_as_invalid_instead_of_crashing() -> None:
    result = assess_safety(
        _snapshot(datetime.now().isoformat()),
        _healthy_sources(),
        pd.DataFrame(),
        pd.DataFrame({"player_id": [1], "gw": [1], "xp": [1.0]}),
        {"unrestricted": SimpleNamespace(status="Optimal")},
        list(REQUIRED_SOURCES),
    )
    assert result.safe_to_act is False


def test_readiness_rejects_non_hex_sha256() -> None:
    payload = _ready_payload()
    payload["official_snapshot"]["bootstrap_sha256"] = "z" * 64
    result = evaluate_report(payload)
    assert result.ready is False
    assert any("sha256" in row.lower() for row in result.blockers)


def test_readiness_rejects_non_list_decision_structures_even_if_lengths_match() -> None:
    payload = _ready_payload()
    for scenario in payload["scenarios"].values():
        scenario["squad"] = "abcdefghijklmno"
        scenario["xi"] = "abcdefghijk"
        scenario["captain"] = "x"
        scenario["vice_captain"] = "y"
    result = evaluate_report(payload)
    assert result.ready is False


def test_readiness_rejects_duplicate_squad_and_xi_ids() -> None:
    payload = _ready_payload()
    for scenario in payload["scenarios"].values():
        scenario["squad"] = [1] * 15
        scenario["xi"] = [1] * 11
        scenario["captain"] = [1]
        scenario["vice_captain"] = [1]
    result = evaluate_report(payload)
    assert result.ready is False


def test_validate_core_pin_rejects_non_hex_commit_sha() -> None:
    source = {
        "commit": "z" * 40,
        "committed_at": datetime.now(timezone.utc).isoformat(),
    }
    ok, _, _ = validate_core_pin(source, max_age_hours=24.0)
    assert ok is False


def test_projection_surface_cannot_substitute_bogus_id_for_missing_official_player() -> None:
    projections = pd.DataFrame(
        {
            "player_id": [1, 999],
            "gw": [1, 1],
            "xp": [4.0, 4.0],
            "projection_confidence": [0.9, 0.9],
        }
    )
    check = _projection_surface_check(projections, {1, 2}, [1])
    assert check.status == "fail"
    assert check.coverage is not None and check.coverage < 1.0


def test_fixture_surface_cannot_substitute_bogus_opponents_for_official_sides() -> None:
    official = OfficialSnapshot(
        players=pd.DataFrame({"player_id": [1, 2]}),
        teams=pd.DataFrame({"id": [1, 2]}),
        fixtures=pd.DataFrame([{"event": 1, "team_h": 1, "team_a": 2}]),
        events=pd.DataFrame({"id": [1]}),
        raw_bootstrap={},
        raw_fixtures=[],
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        bootstrap_sha256="a" * 64,
        fixtures_sha256="b" * 64,
    )
    surface = pd.DataFrame(
        [
            {
                "gw": 1,
                "team": 1,
                "opponent": 999,
                "expected_team_goals": 1.5,
                "clean_sheet_prob": 0.30,
            },
            {
                "gw": 1,
                "team": 2,
                "opponent": 998,
                "expected_team_goals": 1.2,
                "clean_sheet_prob": 0.40,
            },
        ]
    )
    check = _fixture_surface_check(official, surface, [1])
    assert check.status == "fail"


def test_decision_gameweeks_never_resurrects_a_past_deadline() -> None:
    events = pd.DataFrame(
        {
            "id": [38],
            "deadline_time": [(pd.Timestamp.now(tz="UTC") - pd.Timedelta(hours=1)).isoformat()],
            "finished": [False],
        }
    )
    assert _decision_gameweeks(events, 8) == []


def test_captain_multiplier_one_adds_zero_extra_copy() -> None:
    captain, vice, bonus = best_captain_vice_ids(
        [1, 2],
        {1: 6.0, 2: 5.0},
        {1: 1.0, 2: 1.0},
        captain_multiplier=1,
    )
    assert {captain, vice} == {1, 2}
    assert bonus == 0.0


def _minimal_legal_pool() -> pd.DataFrame:
    rows = []
    pid = 1
    for position, count in (("GK", 2), ("DEF", 5), ("MID", 5), ("FWD", 3)):
        for _ in range(count):
            rows.append(
                {
                    "player_id": pid,
                    "web_name": f"P{pid}",
                    "team": pid,
                    "team_name": f"T{pid}",
                    "position": position,
                    "price": 4.0,
                    "horizon_xp": 5.0,
                    "gw1_xp": 5.0,
                }
            )
            pid += 1
    return pd.DataFrame(rows)


def test_locked_player_absent_from_pool_cannot_be_silently_ignored() -> None:
    result = optimise_squad(_minimal_legal_pool(), budget=100.0, locked={999999})
    assert result.status != "Optimal"
