from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from apex_fpl.constants import SQUAD_COUNTS, XI_MAX, XI_MIN
from apex_fpl.control.ruleset_registry import load_ruleset
from apex_fpl.core.identity import (
    IdentityIntegrityError,
    IdentityRegistry,
    IdentityResolutionState,
    IdentityWitness,
    OfficialPlayerId,
    PersonLink,
)
from apex_fpl.core.ids import PersonId
from apex_fpl.core.rules import RuleDefinition, RuleSet


ROOT = Path(__file__).resolve().parents[1]
RULESET_PATH = ROOT / "config/rules/2026-2027.yaml"
BOOTSTRAP = {
    "elements": [
        {"id": 11, "team": 1, "element_type": 3, "now_cost": 75, "web_name": "Alpha"},
        {"id": 22, "team": 2, "element_type": 4, "now_cost": 90, "web_name": "Beta"},
    ]
}


def test_current_official_integer_id_is_exact_identity():
    registry = IdentityRegistry.from_official_bootstrap(BOOTSTRAP)
    resolution = registry.resolve(
        IdentityWitness(
            source="external",
            claimed_player_id=OfficialPlayerId(11),
            team_id=1,
            position="MID",
            display_name="anything",
        )
    )
    assert resolution.state is IdentityResolutionState.EXACT
    assert int(resolution.require_decision_safe().player_id) == 11


def test_name_alone_never_resolves_decision_critical_identity():
    registry = IdentityRegistry.from_official_bootstrap(BOOTSTRAP)
    resolution = registry.resolve(
        IdentityWitness(source="external", display_name="Alpha")
    )
    assert resolution.state is IdentityResolutionState.UNMAPPED
    assert resolution.player is None
    with pytest.raises(IdentityIntegrityError, match="UNMAPPED"):
        resolution.require_decision_safe()


def test_reviewed_person_link_is_corrobated_but_not_promoted_to_exact():
    person = PersonId("person:reviewed:alpha")
    registry = IdentityRegistry.from_official_bootstrap(
        BOOTSTRAP,
        person_links=(
            PersonLink(
                person_id=person,
                player_id=OfficialPlayerId(11),
                source_reference="reviewed-link-fixture",
            ),
        ),
    )
    resolution = registry.resolve(
        IdentityWitness(source="historical", person_id=person, team_id=1, position="MID")
    )
    assert resolution.state is IdentityResolutionState.CORROBORATED
    assert int(resolution.require_decision_safe().player_id) == 11


def test_conflicting_identity_witness_is_ambiguous_and_blocks():
    registry = IdentityRegistry.from_official_bootstrap(BOOTSTRAP)
    resolution = registry.resolve(
        IdentityWitness(
            source="external",
            claimed_player_id=OfficialPlayerId(11),
            team_id=2,
        )
    )
    assert resolution.state is IdentityResolutionState.AMBIGUOUS
    with pytest.raises(IdentityIntegrityError, match="AMBIGUOUS"):
        resolution.require_decision_safe()


def test_official_registry_rejects_non_integer_and_duplicate_ids():
    fractional = {"elements": [{"id": 11.5, "team": 1, "element_type": 3, "now_cost": 75, "web_name": "A"}]}
    with pytest.raises(IdentityIntegrityError, match="exact integer"):
        IdentityRegistry.from_official_bootstrap(fractional)

    duplicate = deepcopy(BOOTSTRAP)
    duplicate["elements"].append(
        {"id": 11, "team": 3, "element_type": 2, "now_cost": 50, "web_name": "Dup"}
    )
    with pytest.raises(IdentityIntegrityError, match="duplicate"):
        IdentityRegistry.from_official_bootstrap(duplicate)


def test_ruleset_is_versioned_official_and_provenance_complete():
    ruleset = load_ruleset(RULESET_PATH)
    assert ruleset.season == "2026-2027"
    assert str(ruleset.ruleset_id).startswith("sha256:")
    assert ruleset.integer("FPL-SQUAD-BUDGET-TENTHS-001") == 1000
    assert ruleset.integer("FPL-FREE-TRANSFER-BANK-MAX-001") == 5
    assert ruleset.integer("FPL-EXTRA-TRANSFER-HIT-POINTS-001") == 4
    assert ruleset.integer("FPL-DEADLINE-OFFSET-MINUTES-001") == 90
    assert all(source.publisher == "Premier League" for source in ruleset.sources)
    assert all(rule.source_ids for rule in ruleset.rules)
    assert all(rule.effective_season == "2026-2027" for rule in ruleset.rules)


def test_ruleset_static_squad_and_lineup_constraints_match_current_official_rules():
    ruleset = load_ruleset(RULESET_PATH)
    assert ruleset.mapping("FPL-SQUAD-POSITIONS-001") == SQUAD_COUNTS
    assert ruleset.mapping("FPL-XI-POSITION-MIN-001") == XI_MIN
    assert ruleset.mapping("FPL-XI-POSITION-MAX-001") == XI_MAX

    positions = ("GK", "GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD")
    clubs = tuple(range(1, 16))
    prices = (40, 40, 45, 45, 45, 45, 45, 50, 50, 50, 50, 50, 60, 60, 60)
    assert ruleset.validate_squad(positions=positions, club_ids=clubs, prices_tenths=prices) == ()
    assert ruleset.validate_lineup(
        positions=("GK", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD")
    ) == ()


def test_ruleset_rejects_illegal_budget_club_count_and_formation():
    ruleset = load_ruleset(RULESET_PATH)
    positions = ("GK", "GK", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD")
    clubs = (1, 1, 1, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12)
    prices = (100,) * 15
    errors = ruleset.validate_squad(positions=positions, club_ids=clubs, prices_tenths=prices)
    assert any("club 1" in error for error in errors)
    assert any("budget" in error for error in errors)
    formation_errors = ruleset.validate_lineup(
        positions=("GK", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD")
    )
    assert any("DEF" in error for error in formation_errors)


def test_ruleset_semantic_identity_changes_when_rule_changes():
    original = load_ruleset(RULESET_PATH)
    rules = list(original.rules)
    target = original.require("FPL-SQUAD-BUDGET-TENTHS-001")
    rules[rules.index(target)] = RuleDefinition.create(
        rule_id=target.rule_id,
        capability=target.capability,
        value=999,
        source_ids=target.source_ids,
        effective_season=target.effective_season,
        effective_from=target.effective_from,
    )
    changed = RuleSet(season=original.season, sources=original.sources, rules=tuple(rules))
    assert changed.ruleset_id != original.ruleset_id


def test_ruleset_semantic_values_reject_uncontrolled_floats():
    with pytest.raises(TypeError, match="floats"):
        RuleDefinition.create(
            rule_id="TEST-FLOAT",
            capability="test",
            value=0.1,
            source_ids=("source",),
            effective_season="2026-2027",
            effective_from="2026-07-20",
        )
