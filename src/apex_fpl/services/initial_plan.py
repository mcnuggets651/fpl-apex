from __future__ import annotations

from typing import Any

import pandas as pd

from apex_fpl.optimisation.transfer_views import optimise_transfer_plan_view


def _ids(frame: pd.DataFrame) -> set[int]:
    if frame.empty or "player_id" not in frame.columns:
        return set()
    return set(pd.to_numeric(frame["player_id"], errors="coerce").dropna().astype(int))


def build_initial_squad_contingencies(
    solution: Any,
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    budget: float,
    max_per_team: int,
    decay: float,
    captain_eligible: set[int] | None = None,
) -> dict:
    """Plan GW2-GW5 from the selected GW1 squad without pre-committing moves."""
    future = [int(gw) for gw in gameweeks[1:5]]
    squad_ids = _ids(solution.squad)
    if solution.status != "Optimal" or len(squad_ids) != 15:
        return {
            "status": "unavailable",
            "future_moves_are_contingent": True,
            "reason": "The initial maximum-EV squad is not a legal optimal solution.",
            "weeks": [],
        }
    if not future:
        return {
            "status": "not_applicable",
            "future_moves_are_contingent": True,
            "reason": "No later actionable Gameweek exists in the official horizon.",
            "weeks": [],
        }

    prices = (
        players.drop_duplicates("player_id")
        .set_index("player_id")["price"]
        .apply(pd.to_numeric, errors="coerce")
        .to_dict()
    )
    starting_cost = sum(float(prices.get(pid, 0.0) or 0.0) for pid in squad_ids)
    starting_bank = max(float(budget) - starting_cost, 0.0)
    plan = optimise_transfer_plan_view(
        players,
        projections,
        future,
        squad_ids,
        projection_col="xp",
        bank=starting_bank,
        free_transfers=1,
        max_per_team=max_per_team,
        decay=decay,
        selling_prices={pid: float(prices.get(pid, 0.0) or 0.0) for pid in squad_ids},
        candidate_limit=180,
        captain_eligible=captain_eligible,
    )
    return {
        "status": plan.status,
        "starting_bank": round(starting_bank, 2),
        "projection_surface": "ensemble mean xp",
        "future_moves_are_contingent": True,
        "actionable_now": "GW1 squad, XI, bench order, captain and vice only",
        "execution_trigger": (
            "Before every later deadline, refresh official fixtures, prices, injuries, "
            "minutes, news and all required forecasts. Execute only the newly re-solved "
            "first action if the strict Pinnacle gate remains green; never execute a "
            "stored future move from this packet."
        ),
        "weeks": plan.weeks if plan.status == "Optimal" else [],
    }


def initial_chip_policy(gameweeks: list[int]) -> dict:
    return {
        "status": "hold",
        "recommended_chip": None,
        "review_gameweeks": [int(gw) for gw in gameweeks[:5]],
        "reason": (
            "A GW1-window score cannot measure the opportunity cost of using a chip "
            "before later blanks, doubles and fixture swings are known."
        ),
        "rules": {
            "wildcard": (
                "Hold in GW1. Re-evaluate only when a fresh multi-week solve shows a "
                "structural squad rebuild beats the legal free-transfer path."
            ),
            "free_hit": (
                "Hold for an official blank/double or severe one-week discontinuity; "
                "the permanent squad must revert correctly in the counterfactual."
            ),
            "bench_boost": (
                "Hold until all 15 players have credible starts and the remaining-half "
                "opportunity-cost comparison is calibrated."
            ),
            "triple_captain": (
                "Hold until a high-minutes captain ceiling is supported by the full gate "
                "and compared with remaining likely double-Gameweek opportunities."
            ),
        },
    }
