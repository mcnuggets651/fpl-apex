from __future__ import annotations

from apex.domain.models import OfficialSnapshot, SystemDecision, TeamState
from apex.domain.rules import (
    BUDGET_TENTHS,
    season_rules,
    validate_bench_order,
    validate_squad,
    validate_xi,
)

_ALLOWED_DECISION_MODES = {
    "INITIAL_SQUAD",
    "TRANSFER_HORIZON",
    "HOLD_H1_ONLY",
    "HOLD_TEAM_STATE_INCOMPLETE",
}
_HOLD_MODES = {"HOLD_H1_ONLY", "HOLD_TEAM_STATE_INCOMPLETE"}


def _validate_transfer_state(
    official: OfficialSnapshot,
    decision: SystemDecision,
    team_state: TeamState | None,
) -> list[str]:
    errors: list[str] = []
    if team_state is None:
        return ["transfer decision requires frozen team state"]
    if not team_state.state_complete_for_transfers:
        errors.append("frozen team state is incomplete for transfers")

    current = set(map(int, team_state.squad_ids))
    incoming = set(map(int, decision.transfers_in))
    outgoing = set(map(int, decision.transfers_out))
    submitted = set(map(int, decision.squad_ids))

    unknown_out = sorted(outgoing - current)
    if unknown_out:
        errors.append(
            "transfer out contains player not owned by frozen team state: "
            f"{unknown_out}"
        )
    already_owned = sorted(incoming & current)
    if already_owned:
        errors.append(
            "transfer in contains player already owned by frozen team state: "
            f"{already_owned}"
        )

    expected = (current - outgoing) | incoming
    if submitted != expected:
        errors.append(
            "transfer transition does not match frozen team state plus submitted "
            "transfers"
        )

    player_map = official.player_map()
    missing_sell = sorted(
        player_id
        for player_id in outgoing
        if player_id not in team_state.selling_prices_tenths
    )
    if missing_sell:
        errors.append(
            "frozen team state lacks exact selling price for transfer out: "
            f"{missing_sell}"
        )

    unknown_in = sorted(player_id for player_id in incoming if player_id not in player_map)
    if unknown_in:
        errors.append(f"transfer in contains unknown Official FPL ids: {unknown_in}")

    if not missing_sell and not unknown_in:
        proceeds = sum(
            int(team_state.selling_prices_tenths[player_id])
            for player_id in outgoing
        )
        spend = sum(int(player_map[player_id].price_tenths) for player_id in incoming)
        cash_after = int(team_state.bank_tenths) + proceeds - spend
        if cash_after < 0:
            errors.append(
                "transfer cash affordability failed: "
                f"bank={team_state.bank_tenths}, proceeds={proceeds}, "
                f"spend={spend}, cash_after={cash_after}"
            )

    rules = season_rules(official.season)
    free_transfers = int(team_state.free_transfers)
    if not 0 <= free_transfers <= rules.max_rolled_free_transfers:
        errors.append(
            "frozen free-transfer state outside supported range: "
            f"{free_transfers}"
        )
    expected_hits = max(0, len(incoming) - max(free_transfers, 0))
    if int(decision.transfer_hits) != expected_hits:
        errors.append(
            "transfer hit count does not match frozen team state: "
            f"submitted={decision.transfer_hits}, expected={expected_hits}"
        )
    if int(decision.horizon) < 2:
        errors.append("TRANSFER_HORIZON decision requires horizon >= 2")
    return errors


def validate_system_decision(
    official: OfficialSnapshot,
    decision: SystemDecision,
    team_state: TeamState | None = None,
) -> tuple[str, ...]:
    players = official.player_map()
    mode = str(decision.decision_mode)
    budget = BUDGET_TENTHS if mode == "INITIAL_SQUAD" else None
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
    if int(decision.horizon) < 1:
        errors.append("decision horizon must be positive")
    if int(decision.transfer_hits) < 0:
        errors.append("transfer hits cannot be negative")
    if mode not in _ALLOWED_DECISION_MODES:
        errors.append(f"unknown decision mode: {mode}")

    if mode == "INITIAL_SQUAD":
        if decision.transfers_in or decision.transfers_out:
            errors.append("INITIAL_SQUAD decision cannot contain transfer metadata")
        if int(decision.transfer_hits) != 0:
            errors.append("INITIAL_SQUAD decision cannot contain transfer hits")
    elif mode == "TRANSFER_HORIZON":
        errors.extend(_validate_transfer_state(official, decision, team_state))
    elif mode in _HOLD_MODES:
        if decision.transfers_in or decision.transfers_out:
            errors.append("hold decision cannot contain permanent transfers")
        if int(decision.transfer_hits) != 0:
            errors.append("hold decision cannot contain transfer hits")
        if team_state is not None and set(map(int, decision.squad_ids)) != set(
            map(int, team_state.squad_ids)
        ):
            errors.append("hold decision cannot mutate frozen team-state squad")

    return tuple(dict.fromkeys(errors))
