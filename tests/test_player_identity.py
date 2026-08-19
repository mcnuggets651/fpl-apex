from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.services.player_identity import (
    IdentityIntegrityError,
    audit_identity_sources,
    build_official_identity_registry,
    resolve_source_identities,
)


def _official() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": 10, "web_name": "Alpha", "first_name": "A", "second_name": "Alpha", "team": 1, "team_name": "Arsenal", "position": "DEF", "price": 4.5, "status": "a"},
            {"player_id": 20, "web_name": "Beta", "first_name": "B", "second_name": "Beta", "team": 2, "team_name": "Chelsea", "position": "MID", "price": 5.0, "status": "a"},
            {"player_id": 30, "web_name": "Smith", "first_name": "Alex", "second_name": "Smith", "team": 3, "team_name": "Liverpool", "position": "FWD", "price": 6.0, "status": "a"},
            {"player_id": 40, "web_name": "Smith", "first_name": "Jamie", "second_name": "Smith", "team": 4, "team_name": "Everton", "position": "FWD", "price": 6.0, "status": "a"},
        ]
    )


def test_registry_is_unique_and_canonical() -> None:
    registry = build_official_identity_registry(_official())
    assert registry["player_id"].tolist() == [10, 20, 30, 40]


def test_correct_id_and_name_resolves_exactly() -> None:
    rows = pd.DataFrame([{"player_id": 10, "source_player_name": "Alpha"}])
    safe, result = resolve_source_identities(
        _official(), rows, source="test", name_columns=("source_player_name",)
    )
    assert result.ready
    assert result.exact_id_matches == 1
    assert safe.iloc[0]["player_id"] == 10


def test_wrong_id_with_valid_other_name_fails_instead_of_remapping() -> None:
    rows = pd.DataFrame([{"player_id": 10, "source_player_name": "Beta"}])
    with pytest.raises(IdentityIntegrityError, match="name conflict"):
        resolve_source_identities(
            _official(), rows, source="test", name_columns=("source_player_name",)
        )


def test_correct_id_with_wrong_name_fails() -> None:
    rows = pd.DataFrame([{"player_id": 20, "source_player_name": "Not Beta"}])
    with pytest.raises(IdentityIntegrityError, match="name conflict"):
        resolve_source_identities(
            _official(), rows, source="test", name_columns=("source_player_name",)
        )


def test_missing_id_unique_name_fallback_is_logged() -> None:
    rows = pd.DataFrame([{"player_id": None, "source_player_name": "Beta"}])
    safe, result = resolve_source_identities(
        _official(), rows, source="test", name_columns=("source_player_name",)
    )
    assert result.ready
    assert result.name_fallback_matches == 1
    assert int(safe.iloc[0]["player_id"]) == 20
    assert result.warnings


def test_ambiguous_name_fallback_fails_closed() -> None:
    rows = pd.DataFrame([{"player_id": None, "source_player_name": "Smith"}])
    with pytest.raises(IdentityIntegrityError, match="ambiguous"):
        resolve_source_identities(
            _official(), rows, source="test", name_columns=("source_player_name",)
        )


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [("team_name", "Chelsea", "team conflict"), ("position", "MID", "position conflict")],
)
def test_context_conflicts_fail_closed(field: str, value: str, message: str) -> None:
    rows = pd.DataFrame(
        [{"player_id": 10, "source_player_name": "Alpha", field: value}]
    )
    with pytest.raises(IdentityIntegrityError, match=message):
        resolve_source_identities(
            _official(), rows, source="test", name_columns=("source_player_name",)
        )


def test_valid_official_id_without_independent_witness_fails() -> None:
    rows = pd.DataFrame([{"player_id": 10, "value": 1.0}])
    with pytest.raises(IdentityIntegrityError, match="independent identity witness"):
        resolve_source_identities(_official(), rows, source="test")


def test_audit_reports_source_blockers_machine_readably() -> None:
    sources = {
        "good": pd.DataFrame([{"player_id": 10, "source_player_name": "Alpha"}]),
        "bad": pd.DataFrame([{"player_id": 10, "source_player_name": "Beta"}]),
    }
    audit = audit_identity_sources(_official(), sources)
    assert audit["contract"] == "apex-player-identity-integrity-v1"
    assert not audit["ready"]
    assert audit["sources"]["good"]["ready"]
    assert not audit["sources"]["bad"]["ready"]


def test_coyle_gabriel_mismatch_shape_is_rejected() -> None:
    official = pd.DataFrame(
        [
            {"player_id": 1, "web_name": "Coyle", "team": 5, "team_name": "Hull", "position": "DEF"},
            {"player_id": 2, "web_name": "Gabriel", "team": 1, "team_name": "Arsenal", "position": "DEF"},
        ]
    )
    rows = pd.DataFrame([{"player_id": 1, "source_player_name": "Gabriel"}])
    with pytest.raises(IdentityIntegrityError):
        resolve_source_identities(
            official, rows, source="regression", name_columns=("source_player_name",)
        )


def test_neave_thiaw_mismatch_shape_is_rejected() -> None:
    official = pd.DataFrame(
        [
            {"player_id": 11, "web_name": "Neave", "team": 14, "team_name": "Newcastle", "position": "FWD"},
            {"player_id": 12, "web_name": "Thiaw", "team": 14, "team_name": "Newcastle", "position": "DEF"},
        ]
    )
    rows = pd.DataFrame([{"player_id": 11, "source_player_name": "Thiaw"}])
    with pytest.raises(IdentityIntegrityError):
        resolve_source_identities(
            official, rows, source="regression", name_columns=("source_player_name",)
        )
