from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import optimise_gameweek_mechanics
from apex_fpl.optimisation.transfers import TransferPlan
from apex_fpl.services.team_state import TeamState


FIRST_HALF_END_GW = 19


@dataclass(frozen=True)
class ChipWindow:
    next_gw: int
    baseline_net_points: float
    available: dict[str, bool]
    options: dict[str, dict]
    best_immediate_chip: str | None
    recommended_chip: str | None
    policy_reason: str
    note: str

    def to_dict(self) -> dict:
        return {
            "next_gw": self.next_gw,
            "baseline_net_points": self.baseline_net_points,
            "available": self.available,
            "options": self.options,
            "best_immediate_chip": self.best_immediate_chip,
            "recommended_chip": self.recommended_chip,
            "policy_reason": self.policy_reason,
            "note": self.note,
        }


def _chip_name(value: object) -> str:
    text = str(value or "").casefold().replace("_", "").replace("-", "")
    aliases = {
        "wildcard": "wildcard",
        "freehit": "free_hit",
        "bboost": "bench_boost",
        "benchboost": "bench_boost",
        "3xc": "triple_captain",
        "triplecaptain": "triple_captain",
    }
    return aliases.get(text, text)


def chip_availability(team_state: TeamState, next_gw: int) -> dict[str, bool]:
    """Return chip availability under the published 2026/27 two-half rules."""
    period_start, period_end = (1, FIRST_HALF_END_GW) if next_gw <= FIRST_HALF_END_GW else (20, 38)
    used: set[str] = set()
    previous_free_hit = False
    for row in team_state.chips_used:
        try:
            event = int(row.get("event"))
        except Exception:
            continue
        name = _chip_name(row.get("name"))
        if period_start <= event <= period_end:
            used.add(name)
        if event == next_gw - 1 and name == "free_hit":
            previous_free_hit = True

    available = {
        "wildcard": "wildcard" not in used,
        "free_hit": "free_hit" not in used and not previous_free_hit,
        "bench_boost": "bench_boost" not in used,
        "triple_captain": "triple_captain" not in used,
    }
    # Wildcard and Free Hit are unavailable for the opening Gameweek because the
    # initial squad already has unlimited transfers.
    if int(next_gw) == 1:
        available["wildcard"] = False
        available["free_hit"] = False
    return available


def _xp_map(
    projections: pd.DataFrame,
    gw: int,
    projection_col: str,
) -> dict[int, float]:
    d = projections[projections["gw"] == int(gw)].copy()
    if d.empty:
        return {}
    column = projection_col if projection_col in d.columns else "risk_adjusted_xp"
    if column not in d.columns:
        raise ValueError(
            f"chip analysis requires {projection_col!r} or 'risk_adjusted_xp'"
        )
    values = d.groupby("player_id")[column].sum()
    return {int(pid): float(value) for pid, value in values.items()}


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    p = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): float(prob)
        for pid, prob in zip(players["player_id"].astype(int), p)
    }


def _rows_to_frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    if not frame.empty and "player_id" in frame:
        frame["player_id"] = pd.to_numeric(frame["player_id"], errors="raise").astype(int)
    return frame


def _liquidation_budget(team_state: TeamState, players: pd.DataFrame) -> tuple[float, bool]:
    prices = {
        int(row.player_id): float(row.price)
        for row in players[["player_id", "price"]].itertuples(index=False)
    }
    total = float(team_state.bank)
    exact = bool(team_state.selling_prices_exact)
    for pid in team_state.squad:
        if pid in team_state.selling_prices:
            total += float(team_state.selling_prices[pid])
        else:
            total += float(prices.get(pid, 0.0))
            exact = False
    return total, exact


def evaluate_chip_window(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    team_state: TeamState,
    transfer_plan: TransferPlan | None,
    *,
    max_per_team: int = 3,
    decay: float = 0.90,
    projection_col: str = "xp",
    captain_eligible: set[int] | None = None,
) -> ChipWindow:
    """Quantify the value of each chip at the next deadline.

    This evaluates the *current window* rather than pretending to know every future
    Blank/Double Gameweek. Bench Boost and Triple Captain are exact expectation
    deltas on the recommended post-transfer team. Free Hit is a one-week temporary
    re-optimisation with the manager's liquidation budget. Wildcard is a permanent
    full-horizon rebuild compared with the best current transfer path.

    The engine reports the value; it does not burn a chip automatically merely
    because today's gain is positive. Future opportunity cost still matters and is
    re-evaluated every deadline.
    """
    gws = [int(gw) for gw in gameweeks]
    if not gws:
        raise ValueError("chip analysis requires at least one future Gameweek")
    next_gw = gws[0]
    xp = _xp_map(projections, next_gw, projection_col)
    appearance = _appearance_map(players)

    if transfer_plan is not None and transfer_plan.status == "Optimal" and transfer_plan.weeks:
        first = transfer_plan.weeks[0]
        squad = _rows_to_frame(first.get("squad", []))
        xi = _rows_to_frame(first.get("xi", []))
        hit = int(first.get("hit_cost", 0) or 0)
    else:
        current = optimise_initial_horizon(
            players,
            projections,
            [next_gw],
            budget=1000.0,
            max_per_team=max_per_team,
            decay=1.0,
            locked=set(team_state.squad),
            captain_eligible=captain_eligible,
        )
        if current.status != "Optimal":
            raise RuntimeError("could not optimise the current squad for chip analysis")
        squad, xi, hit = current.squad, current.xi, 0

    mechanics = optimise_gameweek_mechanics(
        squad,
        xi,
        xp,
        appearance,
        captain_eligible=captain_eligible,
    )
    baseline_net = float(mechanics.expected_total_points - hit)
    available = chip_availability(team_state, next_gw)
    options: dict[str, dict] = {}

    # Triple Captain adds one more copy of the same captain/vice fallback bonus
    # already earned under normal captaincy.
    tc_gain = float(mechanics.expected_captain_bonus)
    options["triple_captain"] = {
        "available": available["triple_captain"],
        "expected_gain_vs_no_chip": tc_gain if available["triple_captain"] else None,
        "expected_points_with_chip": baseline_net + tc_gain if available["triple_captain"] else None,
        "captain_id": mechanics.captain_id,
        "vice_captain_id": mechanics.vice_captain_id,
    }

    squad_ids = set(squad["player_id"].astype(int))
    xi_ids = set(xi["player_id"].astype(int))
    bench_ids = squad_ids - xi_ids
    full_bench_xp = sum(max(float(xp.get(pid, 0.0)), 0.0) for pid in bench_ids)
    bb_gain = max(float(full_bench_xp - mechanics.expected_autosub_points), 0.0)
    options["bench_boost"] = {
        "available": available["bench_boost"],
        "expected_gain_vs_no_chip": bb_gain if available["bench_boost"] else None,
        "expected_points_with_chip": baseline_net + bb_gain if available["bench_boost"] else None,
        "bench_unconditional_xp": float(full_bench_xp),
        "normal_autosub_xp": float(mechanics.expected_autosub_points),
    }

    liquidation_budget, budget_exact = _liquidation_budget(team_state, players)
    if available["free_hit"]:
        fh = optimise_initial_horizon(
            players,
            projections,
            [next_gw],
            budget=liquidation_budget,
            max_per_team=max_per_team,
            decay=1.0,
            captain_eligible=captain_eligible,
        )
        if fh.status == "Optimal":
            fh_mechanics = optimise_gameweek_mechanics(
                fh.squad,
                fh.xi,
                xp,
                appearance,
                captain_eligible=captain_eligible,
            )
            fh_points = float(fh_mechanics.expected_total_points)
            options["free_hit"] = {
                "available": True,
                "expected_gain_vs_no_chip": float(fh_points - baseline_net),
                "expected_points_with_chip": fh_points,
                "temporary_budget": round(liquidation_budget, 2),
                "budget_exact": budget_exact,
                "squad": fh.squad.to_dict("records"),
                "xi": fh.xi.to_dict("records"),
                "captain_id": fh_mechanics.captain_id,
                "vice_captain_id": fh_mechanics.vice_captain_id,
                "bench_order": list(fh_mechanics.outfield_bench_order),
            }
        else:
            options["free_hit"] = {"available": True, "status": "infeasible"}
    else:
        options["free_hit"] = {"available": False, "expected_gain_vs_no_chip": None}

    if available["wildcard"]:
        wc = optimise_initial_horizon(
            players,
            projections,
            gws,
            budget=liquidation_budget,
            max_per_team=max_per_team,
            decay=decay,
            captain_eligible=captain_eligible,
        )
        base_horizon = (
            float(transfer_plan.objective)
            if transfer_plan is not None and transfer_plan.status == "Optimal"
            else None
        )
        options["wildcard"] = {
            "available": True,
            "horizon_objective": float(wc.objective) if wc.status == "Optimal" else None,
            "objective_gain_vs_transfer_path": (
                float(wc.objective - base_horizon)
                if wc.status == "Optimal" and base_horizon is not None
                else None
            ),
            "liquidation_budget": round(liquidation_budget, 2),
            "budget_exact": budget_exact,
            "squad": wc.squad.to_dict("records") if wc.status == "Optimal" else [],
        }
    else:
        options["wildcard"] = {
            "available": False,
            "objective_gain_vs_transfer_path": None,
        }

    immediate = []
    for name in ("triple_captain", "bench_boost", "free_hit"):
        value = options.get(name, {}).get("expected_gain_vs_no_chip")
        if options.get(name, {}).get("available") and value is not None:
            immediate.append((float(value), name))
    best = max(immediate)[1] if immediate else None
    return ChipWindow(
        next_gw=next_gw,
        baseline_net_points=baseline_net,
        available=available,
        options=options,
        best_immediate_chip=best,
        recommended_chip=None,
        policy_reason=(
            "Hold. Current-window gain is diagnostic only; Apex has not yet compared it "
            "with a calibrated remaining-half opportunity-cost distribution."
        ),
        note=(
            "Chip values are current-window opportunity values, not an instruction to "
            "spend a chip automatically. The production policy is hold until a known "
            "Blank/Double Gameweek or another window beats a calibrated opportunity-cost "
            "threshold, then refresh all evidence before committing."
        ),
    )
