from __future__ import annotations

import pytest

from apex.forecast.dastan_identity import audit_current_roster, resolve_understat_clubs


def test_club_overlay_uses_only_reviewed_unique_aliases():
    payload = {
        "301": {"title": "Coventry"},
        "302": {"title": "Hull City"},
        "83": {"title": "Arsenal"},
    }
    rows = resolve_understat_clubs(
        payload,
        aliases={
            "Coventry City": ("Coventry", "Coventry_City"),
            "Hull City": ("Hull", "Hull_City"),
        },
    )
    assert [(row.club_name, row.understat_name, row.understat_team_id) for row in rows] == [
        ("Coventry City", "Coventry", 301),
        ("Hull City", "Hull City", 302),
    ]


def test_club_overlay_fails_closed_on_ambiguity():
    payload = {
        "301": {"title": "Coventry"},
        "999": {"title": "Coventry City"},
    }
    with pytest.raises(RuntimeError, match="expected exactly one"):
        resolve_understat_clubs(
            payload,
            aliases={"Coventry City": ("Coventry", "Coventry_City")},
        )


def test_roster_audit_keys_identity_by_stable_fpl_code_not_element_id():
    official = [
        {"id": 10, "code": 1001, "web_name": "A"},
        {"id": 20, "code": 1002, "web_name": "B"},
        {"id": 30, "code": 1003, "web_name": "C"},
    ]
    dastan = [
        {
            "fpl_code": "1001",
            "element": "999",
            "understat_id": "55",
            "mapping_status": "mapped",
        },
        {
            "fpl_code": "1002",
            "element": "20",
            "understat_id": "",
            "mapping_status": "unmapped",
        },
        {
            "fpl_code": "1999",
            "element": "40",
            "understat_id": "88",
            "mapping_status": "mapped",
        },
    ]
    audit = audit_current_roster(official, dastan)
    assert audit["matched_by_fpl_code"] == 2
    assert audit["missing_from_dastan_roster"] == [1003]
    assert audit["stale_dastan_codes"] == [1999]
    assert audit["unresolved_understat_codes"] == [1002]
    assert audit["element_id_drift"] == [
        {"fpl_code": 1001, "dastan_element": 999, "official_element": 10}
    ]


def test_roster_audit_rejects_duplicate_official_codes():
    with pytest.raises(ValueError, match="duplicate stable code"):
        audit_current_roster(
            [{"id": 1, "code": 100}, {"id": 2, "code": 100}],
            [],
        )
