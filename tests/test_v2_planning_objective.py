from __future__ import annotations

from dataclasses import replace

import pytest

from apex_fpl.core.decision import RationalValue
from apex_fpl.core.decision_policy_support import ChipOptionValuePolicy, ExactPolicyValue
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import GlobalWorldId, ManagerStateId
from apex_fpl.core.manager_state import OwnedPlayer
from apex_fpl.core.planning import PlanningChipUse, PlanningState
from apex_fpl.core.rules import OfficialRuleSource, RuleDefinition, RuleSet
from apex_fpl.decision.planning_objective import terminal_chip_reserve


def _ruleset() -> RuleSet:
    source = OfficialRuleSource(
        source_id="PL-CHIPS",
        publisher="Premier League",
        title="FPL chips",
        url="https://www.premierleague.com/en/news/4679879/whats-happening-with-fpl-chips-in-202627",
        published_on="2026-07-20",
        verified_on="2026-08-25",
    )
    rules = (
        RuleDefinition.create(
            rule_id="FPL-CHIP-FIRST-SET-LAST-GW-001",
            capability="chips",
            value=19,
            source_ids=(source.source_id,),
            effective_season="2026-2027",
            effective_from="2026-07-20",
        ),
        RuleDefinition.create(
            rule_id="FPL-CHIP-SECOND-SET-FIRST-GW-001",
            capability="chips",
            value=20,
            source_ids=(source.source_id,),
            effective_season="2026-2027",
            effective_from="2026-07-20",
        ),
    )
    return RuleSet(season="2026-2027", sources=(source,), rules=rules)


def _squad() -> tuple[OwnedPlayer, ...]:
    positions = (
        "GK",
        "GK",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "DEF",
        "MID",
        "MID",
        "MID",
        "MID",
        "MID",
        "FWD",
        "FWD",
        "FWD",
    )
    return tuple(
        OwnedPlayer(
            player_id=OfficialPlayerId(index),
            team_id=index,
            position=position,
            purchase_basis_tenths=50,
            current_price_tenths=50,
            selling_price_tenths=50,
        )
        for index, position in enumerate(positions, start=1)
    )


def _state(*, gameweek: int, chips: tuple[PlanningChipUse, ...] = ()) -> PlanningState:
    ruleset = _ruleset()
    return PlanningState(
        origin_manager_state_id=ManagerStateId("manager"),
        price_world_id=GlobalWorldId("world"),
        season="2026-2027",
        entry_id=63984,
        gameweek=gameweek,
        ruleset_id=ruleset.ruleset_id,
        bank_tenths=0,
        free_transfers=1,
        squad=_squad(),
        chips_used=chips,
    )


def _policy() -> ChipOptionValuePolicy:
    return ChipOptionValuePolicy(
        season="2026-2027",
        horizon_gameweeks=6,
        first_available_at="2026-08-01T00:00:00Z",
        option_values=(
            ("BENCH_BOOST", ExactPolicyValue(1, 1)),
            ("FREE_HIT", ExactPolicyValue(2, 1)),
            ("TRIPLE_CAPTAIN", ExactPolicyValue(3, 1)),
            ("WILDCARD", ExactPolicyValue(4, 1)),
        ),
    )


def test_pre_boundary_reserve_counts_unused_current_and_future_entitlements() -> None:
    # One complete set is worth 10; before GW20 both set-1 and guaranteed set-2
    # entitlements remain economically available.
    assert terminal_chip_reserve(_state(gameweek=10), _policy(), ruleset=_ruleset()) == RationalValue(20, 1)


def test_used_current_set_entitlement_is_not_double_valued() -> None:
    state = _state(
        gameweek=10,
        chips=(PlanningChipUse(5, "TRIPLE_CAPTAIN", 1),),
    )
    assert terminal_chip_reserve(state, _policy(), ruleset=_ruleset()) == RationalValue(17, 1)


def test_set_one_reserve_expires_when_terminal_reaches_gw20() -> None:
    assert terminal_chip_reserve(_state(gameweek=20), _policy(), ruleset=_ruleset()) == RationalValue(10, 1)


def test_gw19_free_hit_does_not_destroy_second_set_entitlement() -> None:
    state = _state(
        gameweek=20,
        chips=(PlanningChipUse(19, "FREE_HIT", 1),),
    )
    assert terminal_chip_reserve(state, _policy(), ruleset=_ruleset()) == RationalValue(10, 1)


def test_planning_state_rejects_current_or_future_chip_history() -> None:
    with pytest.raises(ValueError, match="current/future"):
        _state(gameweek=10, chips=(PlanningChipUse(10, "WILDCARD", 1),))
    with pytest.raises(ValueError, match="current/future"):
        _state(gameweek=10, chips=(PlanningChipUse(11, "WILDCARD", 1),))


def test_terminal_reserve_rejects_season_drift() -> None:
    with pytest.raises(ValueError, match="season mismatch"):
        terminal_chip_reserve(
            _state(gameweek=10),
            replace(_policy(), season="2025-2026"),
            ruleset=_ruleset(),
        )
