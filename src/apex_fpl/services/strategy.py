from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.transfer_views import optimise_transfer_plan_view
from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.rules import MAX_ROLLED_FREE_TRANSFERS
from apex_fpl.services.team_state import TeamState


@dataclass(frozen=True)
class RecedingHorizonStrategy:
    status: str
    next_gw: int | None
    recommended_action: str
    recommended_transfers: int
    recommended_hit: int
    optimal_objective: float | None
    roll_objective: float | None
    roll_regret: float | None
    action_now: dict | None
    contingent_future: list[dict]
    projection_col: str
    note: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "next_gw": self.next_gw,
            "recommended_action": self.recommended_action,
            "recommended_transfers": self.recommended_transfers,
            "recommended_hit": self.recommended_hit,
            "optimal_objective": self.optimal_objective,
            "roll_objective": self.roll_objective,
            "roll_regret": self.roll_regret,
            "action_now": self.action_now,
            "contingent_future": self.contingent_future,
            "future_moves_are_contingent": True,
            "projection_col": self.projection_col,
            "note": self.note,
        }


def _next_ft_after_roll(free_transfers: int) -> int:
    return min(MAX_ROLLED_FREE_TRANSFERS, max(1, int(free_transfers) + 1))


def analyse_receding_horizon(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    team_state: TeamState,
    optimal_plan: TransferPlan | None = None,
    *,
    max_per_team: int = 3,
    decay: float = 0.90,
    projection_col: str = "xp",
    candidate_limit: int = 160,
) -> RecedingHorizonStrategy:
    """Return the one action Pinnacle should execute at the next deadline.

    The function re-solves the full transfer path on the explicit maximum-EV
    projection surface rather than inheriting the legacy risk-adjusted plan. That
    keeps uncertainty as a separate robustness question and prevents risk from
    being double-counted. Only the first action is actionable; all later moves are
    contingent and must be recalculated after new information arrives.
    """
    gws = [int(gw) for gw in gameweeks]
    if not gws:
        return RecedingHorizonStrategy(
            "unavailable", None, "none", 0, 0, None, None, None, None, [],
            projection_col, "No future Gameweek is available."
        )

    ev_plan = optimise_transfer_plan_view(
        players,
        projections,
        gws,
        set(team_state.squad),
        projection_col=projection_col,
        bank=team_state.bank,
        free_transfers=team_state.free_transfers,
        max_per_team=max_per_team,
        decay=decay,
        selling_prices=team_state.selling_prices,
        candidate_limit=candidate_limit,
    )
    plan = ev_plan if ev_plan.status == "Optimal" else optimal_plan
    if plan is None or plan.status != "Optimal" or not plan.weeks:
        return RecedingHorizonStrategy(
            "unavailable", gws[0], "none", 0, 0, None, None, None, None, [],
            projection_col, "No optimal personalised transfer plan is available."
        )

    first_gw = gws[0]
    current_week = optimise_initial_horizon(
        players,
        projections,
        [first_gw],
        budget=1000.0,
        max_per_team=max_per_team,
        decay=1.0,
        locked=set(team_state.squad),
        projection_col=projection_col,
    )
    if current_week.status != "Optimal":
        return RecedingHorizonStrategy(
            "error", first_gw, "none", 0, 0,
            float(plan.objective), None, None,
            plan.weeks[0], plan.weeks[1:], projection_col,
            "Could not solve the explicit roll counterfactual from the current squad."
        )

    roll_objective = float(current_week.objective)
    if len(gws) > 1:
        future = optimise_transfer_plan_view(
            players,
            projections,
            gws[1:],
            set(team_state.squad),
            projection_col=projection_col,
            bank=team_state.bank,
            free_transfers=_next_ft_after_roll(team_state.free_transfers),
            max_per_team=max_per_team,
            decay=decay,
            selling_prices=team_state.selling_prices,
            candidate_limit=candidate_limit,
        )
        if future.status == "Optimal":
            roll_objective += float(decay) * float(future.objective)

    first = plan.weeks[0]
    transfers = int(first.get("transfers", 0) or 0)
    hit = int(first.get("hit_cost", 0) or 0)
    if transfers == 0:
        action = "roll"
    elif hit > 0:
        action = "transfer_with_hit"
    elif transfers == 1:
        action = "one_free_transfer"
    else:
        action = "multiple_free_transfers"

    optimal_objective = float(plan.objective)
    regret = max(optimal_objective - roll_objective, 0.0)
    return RecedingHorizonStrategy(
        status="optimal",
        next_gw=first_gw,
        recommended_action=action,
        recommended_transfers=transfers,
        recommended_hit=hit,
        optimal_objective=optimal_objective,
        roll_objective=float(roll_objective),
        roll_regret=float(regret),
        action_now=first,
        contingent_future=plan.weeks[1:],
        projection_col=projection_col,
        note=(
            "Execute only action_now. The later path is a mathematical contingency, "
            "not a promise: refresh prices, minutes, injuries, transfers and news "
            "before every subsequent deadline and solve again."
        ),
    )
