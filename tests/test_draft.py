from __future__ import annotations

import pytest

from apex_fpl.config import load_settings
from apex_fpl.services.draft import (
    DraftAPIError,
    DraftFPLClient,
    DraftLeagueEntry,
    DraftLeagueSnapshot,
    build_draft_pool,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get(self, url, timeout):
        self.calls.append((url, timeout))
        return FakeResponse(self.payloads[url])


def test_snapshot_and_availability_contract_supports_entry_id_schema():
    base = "https://draft.example/api"
    session = FakeSession(
        {
            f"{base}/league/123/details": {
                "league": {"name": "Apex Draft"},
                "league_entries": [
                    {"id": 900, "entry_id": 9, "entry_name": "mcnuggets"},
                    {"id": 1000, "entry_id": 10, "entry_name": "rival"},
                ],
            },
            f"{base}/league/123/element-status": [
                {"element": 1, "status": "a", "owner": None},
                {"element": 2, "status": "o", "owner": 9},
                {"element": 3, "status": "l", "owner": None},
            ],
        }
    )
    client = DraftFPLClient(session=session, base_url=base, timeout=3.0)

    snapshot = client.snapshot(123)

    assert snapshot.league_name == "Apex Draft"
    assert snapshot.available_element_ids == (1,)
    assert snapshot.locked_element_ids == (3,)
    assert snapshot.owner_by_element() == {2: 9}
    assert snapshot.owner_name_lookup()[9] == "mcnuggets"
    assert snapshot.owner_name_lookup()[900] == "mcnuggets"
    assert snapshot.resolve_entry_id("MCNUGGETS") == 9
    assert session.calls == [
        (f"{base}/league/123/details", 3.0),
        (f"{base}/league/123/element-status", 3.0),
    ]


def test_snapshot_falls_back_when_details_only_has_id():
    base = "https://draft.example/api"
    session = FakeSession(
        {
            f"{base}/league/123/details": {
                "league": {"name": "Apex Draft"},
                "league_entries": [{"id": 9, "entry_name": "mcnuggets"}],
            },
            f"{base}/league/123/element-status": [],
        }
    )
    snapshot = DraftFPLClient(session=session, base_url=base).snapshot(123)

    assert snapshot.resolve_entry_id("mcnuggets") == 9
    assert snapshot.entries[0].transaction_entry_id == 9


def test_resolve_entry_id_fails_closed_for_unknown_name():
    snapshot = DraftLeagueSnapshot(
        league_id=123,
        league_name="Apex Draft",
        entries=(DraftLeagueEntry(9, "mcnuggets"),),
        element_status=(),
    )

    with pytest.raises(DraftAPIError, match="was not found"):
        snapshot.resolve_entry_id("someone else")


def test_build_draft_pool_keeps_draft_ids_separate_and_maps_owner():
    snapshot = DraftLeagueSnapshot(
        league_id=123,
        league_name="Apex Draft",
        entries=(DraftLeagueEntry(900, "mcnuggets", team_entry_id=9),),
        element_status=(
            {"element": 101, "status": "a", "owner": None},
            {"element": 202, "status": "o", "owner": 9},
        ),
    )
    bootstrap = {
        "teams": [{"id": 4, "name": "Newcastle"}],
        "element_types": [{"id": 4, "singular_name_short": "FWD"}],
        "elements": [
            {
                "id": 101,
                "first_name": "William",
                "second_name": "Osula",
                "web_name": "Osula",
                "team": 4,
                "element_type": 4,
            },
            {
                "id": 202,
                "first_name": "Jean-Philippe",
                "second_name": "Mateta",
                "web_name": "Mateta",
                "team": 4,
                "element_type": 4,
            },
        ],
    }

    rows = build_draft_pool(snapshot, bootstrap)

    assert rows[0] == {
        "draft_element_id": 101,
        "first_name": "William",
        "second_name": "Osula",
        "web_name": "Osula",
        "team": "Newcastle",
        "position": "FWD",
        "status": "a",
        "owner_entry_id": None,
        "owner_entry_name": "",
    }
    assert rows[1]["draft_element_id"] == 202
    assert rows[1]["owner_entry_id"] == 9
    assert rows[1]["owner_entry_name"] == "mcnuggets"


def test_load_settings_reads_draft_identity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "apex.yaml"
    cfg.write_text("", encoding="utf-8")
    monkeypatch.setenv("FPL_DRAFT_LEAGUE_ID", "12345")
    monkeypatch.setenv("FPL_DRAFT_ENTRY_NAME", "mcnuggets")

    settings = load_settings(cfg)

    assert settings.fpl_draft_league_id == 12345
    assert settings.fpl_draft_entry_name == "mcnuggets"


def test_load_settings_rejects_invalid_draft_league_id(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cfg = tmp_path / "apex.yaml"
    cfg.write_text("", encoding="utf-8")
    monkeypatch.setenv("FPL_DRAFT_LEAGUE_ID", "0")

    with pytest.raises(ValueError, match="FPL Draft league ID must be a positive integer"):
        load_settings(cfg)
