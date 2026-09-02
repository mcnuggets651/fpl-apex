from __future__ import annotations

from apex.domain.models import OfficialSnapshot, SystemDecision
from apex.domain.rules import (
    BUDGET_TENTHS,
    validate_bench_order,
    validate_squad,
    validate_xi,
)


def validate_system_decision(
    official: OfficialSnapshot,
    decision: SystemDecision,
) -> tuple[str, ...]:
    players = official.player_map()
    budget = BUDGET_TENTHS if decision.decision_mode == "INITIAL_SQUAD" else None
    errors = list(
        validate_squad(
            players,
            decision.squad_ids,
            budget_tenths=budget,
        )
    )
    errors += validate_xi(players, decision.squad_ids, decision.xi_ids)
    errors += validate_bench_order(
        players,
        decision.squad_ids,
        decision.xi_ids,
        decision.bench_order,
    )
    if decision.captain_id not in set(decision.xi_ids):
        errors.append("captain must be in XI")
    if decision.vice_captain_id not in set(decision.xi_ids):
        errors.append("vice-captain must be in XI")
    if decision.captain_id == decision.vice_captain_id:
        errors.append("captain and vice-captain must differ")
    if set(decision.transfers_in) & set(decision.transfers_out):
        errors.append("same player cannot be transferred in and out")
    if len(decision.transfers_in) != len(decision.transfers_out):
        errors.append("permanent transfers must balance in and out")
    return tuple(dict.fromkeys(errors))
