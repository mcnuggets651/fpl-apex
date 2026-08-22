from __future__ import annotations

import pandas as pd
import pytest

from apex_fpl.services.player_identity import (
    IdentityIntegrityError,
    audit_identity_sources,
    build_official_identity_registry,
    resolve_source_identities,
    validate_required_id_coverage,
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


def test_registry_duplicate_ids_fail_instead_of_being_silently_deduplicated() -> None:
    corrupted = pd.concat([_official(), _official().iloc[[0]]], ignore_index=True)
    with pytest.raises(IdentityIntegrityError, match="duplicate player IDs"):
        build_official_identity_registry(corrupted)


def test_registry_blank_official_name_fails_closed() -> None:
    corrupted = _official()
    corrupted.loc[0, "web_name"] = ""
    with pytest.raises(IdentityIntegrityError, match="blank web_name"):
        build_official_identity_registry(corrupted)


def test_correct_id_and_name_resolves_exactly() -> None:
    rows = pd.DataFrame([{"player_id": 10, "source_player_name": "Alpha"}])
    safe, result = resolve_source_identities(
        _official(), rows, source="test", name_columns=("source_player_name",)
    )
    assert result.ready
    assert result.exact_id_matches == 1
    assert safe.iloc[0]["player_id"] == 10


def test_unicode_name_witnesses_normalize_without_alias_remapping() -> None:
    official = pd.DataFrame(
        [
            {"player_id": 1, "web_name": "João Pedro", "team": 1, "team_name": "Chelsea", "position": "FWD"},
            {"player_id": 2, "web_name": "Guéhi", "team": 2, "team_name": "Man City", "position": "DEF"},
        ]
    )
    rows = pd.DataFrame(
        [
            {"player_id": 1, "source_player_name": "Joao Pedro"},
            {"player_id": 2, "source_player_name": "Guehi"},
        ]
    )
    _, result = resolve_source_identities(official, rows, source="unicode")
    assert result.ready
    assert result.exact_id_matches == 2
    assert result.name_fallback_matches == 0


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


def test_numeric_element_type_is_compared_to_official_position_semantically() -> None:
    rows = pd.DataFrame(
        [{"player_id": 20, "source_player_name": "Beta", "element_type": 3}]
    )
    _, result = resolve_source_identities(_official(), rows, source="element-type")
    assert result.ready


def test_malformed_numeric_team_identity_is_not_silently_ignored() -> None:
    rows = pd.DataFrame(
        [{"player_id": 10, "source_player_name": "Alpha", "team": "Arsenal"}]
    )
    with pytest.raises(IdentityIntegrityError, match="team identity is non-numeric"):
        resolve_source_identities(_official(), rows, source="bad-team-field")


def test_valid_official_id_without_independent_witness_fails() -> None:
    rows = pd.DataFrame([{"player_id": 10, "value": 1.0}])
    with pytest.raises(IdentityIntegrityError, match="independent identity witness"):
        resolve_source_identities(_official(), rows, source="test")


def test_roster_complete_source_coverage_passes_only_for_exact_official_id_set() -> None:
    rows = pd.DataFrame(
        [{"player_id": pid, "source_player_name": name} for pid, name in [(10, "Alpha"), (20, "Beta"), (30, "Smith"), (40, "Smith")]]
    )
    coverage = validate_required_id_coverage(_official(), rows, source="airsenal")
    assert coverage["ready"]
    assert coverage["official_ids"] == 4
    assert coverage["source_ids"] == 4
    assert coverage["missing_ids"] == []
    assert coverage["extra_ids"] == []


def test_roster_complete_source_missing_id_fails_closed() -> None:
    rows = pd.DataFrame([{"player_id": 10}, {"player_id": 20}, {"player_id": 30}])
    coverage = validate_required_id_coverage(_official(), rows, source="airsenal")
    assert not coverage["ready"]
    assert coverage["missing_ids"] == [40]
    assert "missing 1 Official FPL player IDs" in coverage["blockers"][0]


def test_roster_complete_source_extra_unknown_id_fails_closed() -> None:
    rows = pd.DataFrame([{"player_id": 10}, {"player_id": 20}, {"player_id": 30}, {"player_id": 40}, {"player_id": 999}])
    coverage = validate_required_id_coverage(_official(), rows, source="airsenal")
    assert not coverage["ready"]
    assert coverage["extra_ids"] == [999]


def test_audit_reports_source_blockers_machine_readably() -> None:
    sources = {
        "good": pd.DataFrame([{"player_id": 10, "source_player_name": "Alpha"}]),
        "bad": pd.DataFrame([{"player_id": 10, "source_player_name": "Beta"}]),
    }
    audit = audit_identity_sources(_official(), sources)
    assert audit["contract"] == "apex-player-identity-integrity-v2"
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
