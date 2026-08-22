from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from apex_fpl.optimisation.bench_policy import BenchResilienceError
from apex_fpl.optimisation.exact_decision import optimise_fixed_squad_gameweek
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.solver_status import certified_infeasible
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
    canonical_squad: list[dict] | None = None
    canonical_xi: list[dict] | None = None
    canonical_captain: str | None = None
    canonical_captain_id: int | None = None
    canonical_vice_captain: str | None = None
    canonical_vice_captain_id: int | None = None
    canonical_bench_gk: str | None = None
    canonical_bench_gk_id: int | None = None
    canonical_outfield_bench_order: list[str] | None = None
    canonical_outfield_bench_order_ids: list[int] | None = None
    canonical_expected_points: float | None = None
    state_transition_reconciled: bool = False
    roll_admissible: bool = True
    current_bench_resilience_enforced: bool = False

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
            "roll_admissible": self.roll_admissible,
            "action_now": self.action_now,
            "contingent_future": self.contingent_future,
            "future_moves_are_contingent": True,
            "projection_col": self.projection_col,
            "note": self.note,
            "canonical_squad": self.canonical_squad,
            "canonical_xi": self.canonical_xi,
            "canonical_captain": self.canonical_captain,
            "canonical_captain_id": self.canonical_captain_id,
            "canonical_vice_captain": self.canonical_vice_captain,
            "canonical_vice_captain_id": self.canonical_vice_captain_id,
            "canonical_bench_gk": self.canonical_bench_gk,
            "canonical_bench_gk_id": self.canonical_bench_gk_id,
            "canonical_outfield_bench_order": self.canonical_outfield_bench_order,
            "canonical_outfield_bench_order_ids": self.canonical_outfield_bench_order_ids,
            "canonical_expected_points": self.canonical_expected_points,
            "state_transition_reconciled": self.state_transition_reconciled,
            "current_bench_resilience_enforced": self.current_bench_resilience_enforced,
        }


def _next_ft_after_roll(free_transfers: int) -> int:
    return min(MAX_ROLLED_FREE_TRANSFERS, max(1, int(free_transfers) + 1))


def _projection_map(
    projections: pd.DataFrame,
    gw: int,
    projection_col: str,
) -> dict[int, float]:
    rows = projections[projections["gw"].astype(int).eq(int(gw))]
    if projection_col not in rows.columns:
        if projection_col == "xp" and "risk_adjusted_xp" in rows.columns:
            projection_col = "risk_adjusted_xp"
        else:
            raise ValueError(f"projection table requires {projection_col!r}")
    values = rows.groupby("player_id")[projection_col].sum()
    return {int(pid): float(value) for pid, value in values.items()}


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    values = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): min(max(float(prob), 0.0), 1.0)
        for pid, prob in zip(players["player_id"].astype(int), values)
    }


def _named_records(frame: pd.DataFrame, xp: dict[int, float]) -> list[dict]:
    cols = [
        col
        for col in ["player_id", "web_name", "team_name", "position", "price"]
        if col in frame.columns
    ]
    out = frame[cols].copy()
    out["gw1_xp"] = out["player_id"].astype(int).map(xp).fillna(0.0)
    return out.to_dict("records")


def _unavailable(
    *,
    status: str,
    next_gw: int | None,
    projection_col: str,
    note: str,
    optimal_objective: float | None = None,
    action_now: dict | None = None,
    contingent_future: list[dict] | None = None,
    roll_admissible: bool = True,
) -> RecedingHorizonStrategy:
    return RecedingHorizonStrategy(
        status=status,
        next_gw=next_gw,
        recommended_action="none",
        recommended_transfers=0,
        recommended_hit=0,
        optimal_objective=optimal_objective,
        roll_objective=None,
        roll_regret=None,
        action_now=action_now,
        contingent_future=list(contingent_future or []),
        projection_col=projection_col,
        note=note,
        roll_admissible=roll_admissible,
        current_bench_resilience_enforced=True,
    )


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
    captain_eligible: set[int] | None = None,
) -> RecedingHorizonStrategy:
    """Return the one action Pinnacle should execute at the next deadline.

    The full legal transfer path is re-solved on the current maximum-EV projection
    surface, but only its first action is executable. The first/submitted Gameweek is
    constrained by the governed bench-resilience policy inside the transfer MILP and
    then independently rescored with exact XI/captain/vice/autosub mechanics. Every
    later move is an unconstrained contingency and must be rebuilt after new football
    and price evidence.

    ``optimal_plan`` remains an API-compatibility input only. It is deliberately not
    used as a fallback because an older plan may have been solved under a different
    feasibility contract.
    """
    del optimal_plan
    gws = [int(gw) for gw in gameweeks]
    if not gws:
        return _unavailable(
            status="unavailable",
            next_gw=None,
            projection_col=projection_col,
            note="No future Gameweek is available.",
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
        captain_eligible=captain_eligible,
        enforce_current_bench_resilience=True,
    )
    if ev_plan.status != "Optimal" or not ev_plan.weeks:
        detail = ev_plan.solver_message or ev_plan.status
        return _unavailable(
            status="unavailable",
            next_gw=gws[0],
            projection_col=projection_col,
            note=(
                "No optimal current-bench-safe personalised transfer plan is available: "
                f"{detail}"
            ),
        )
    plan = ev_plan

    first_gw = gws[0]
    current_week = optimise_initial_horizon(
        players,
        projections,
        [first_gw],
        budget=1000.0,
        max_per_team=max_per_team,
        decay=1.0,
        locked=set(team_state.squad),
        captain_eligible=captain_eligible,
        projection_col=projection_col,
        enforce_current_bench_resilience=True,
    )
    roll_admissible = current_week.status == "Optimal"
    if not roll_admissible and not certified_infeasible(
        current_week.status,
        current_week.solver,
    ):
        return _unavailable(
            status="error",
            next_gw=first_gw,
            projection_col=projection_col,
            note=(
                "The explicit roll counterfactual ended without an optimal solution or "
                "a certified infeasibility proof."
            ),
            optimal_objective=float(plan.objective),
            action_now=plan.weeks[0],
            contingent_future=plan.weeks[1:],
        )

    roll_objective: float | None = None
    if roll_admissible:
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
                captain_eligible=captain_eligible,
                # This starts next deadline, so today's bench evidence is not frozen
                # into that future contingency.
                enforce_current_bench_resilience=False,
            )
            if future.status == "Optimal":
                roll_objective += float(decay) * float(future.objective)
            elif not future.certified_infeasible:
                return _unavailable(
                    status="error",
                    next_gw=first_gw,
                    projection_col=projection_col,
                    note=(
                        "The future path for the roll counterfactual is inconclusive; "
                        "Apex will not fabricate roll regret."
                    ),
                    optimal_objective=float(plan.objective),
                    action_now=plan.weeks[0],
                    contingent_future=plan.weeks[1:],
                    roll_admissible=True,
                )

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
    if action == "roll" and not roll_admissible:
        return _unavailable(
            status="error",
            next_gw=first_gw,
            projection_col=projection_col,
            note="The optimiser selected roll even though roll is bench-policy-inadmissible.",
            optimal_objective=float(plan.objective),
            action_now=first,
            contingent_future=plan.weeks[1:],
            roll_admissible=False,
        )

    action_ids = {
        int(row["player_id"])
        for row in (first.get("squad") or [])
        if row.get("player_id") is not None
    }
    in_ids = {
        int(row["player_id"])
        for row in (first.get("transfers_in") or [])
        if row.get("player_id") is not None
    }
    out_ids = {
        int(row["player_id"])
        for row in (first.get("transfers_out") or [])
        if row.get("player_id") is not None
    }
    expected_ids = (set(map(int, team_state.squad)) - out_ids) | in_ids
    transition_ok = bool(
        len(action_ids) == 15
        and action_ids == expected_ids
        and len(in_ids) == len(out_ids) == transfers
        and int(first.get("free_transfers_before", -1)) == int(team_state.free_transfers)
        and float(first.get("bank_after", -1.0)) >= 0.0
    )

    canonical_squad = None
    canonical_xi = None
    captain_name = None
    captain_id = None
    vice_name = None
    vice_id = None
    bench_gk_name = None
    bench_gk_id = None
    bench_order_names = None
    bench_order_ids = None
    exact_points = None
    if transition_ok:
        squad = players[players["player_id"].astype(int).isin(action_ids)].copy()
        xp = _projection_map(projections, first_gw, projection_col)
        xi_eligible = (
            set(
                players.loc[
                    players["xi_evidence_eligible"].fillna(False), "player_id"
                ].astype(int)
            )
            if "xi_evidence_eligible" in players.columns
            else None
        )
        try:
            xi, mechanics = optimise_fixed_squad_gameweek(
                squad,
                xp,
                _appearance_map(players),
                captain_eligible=captain_eligible,
                xi_eligible=xi_eligible,
                enforce_current_bench_resilience=True,
            )
        except (BenchResilienceError, ValueError) as exc:
            return _unavailable(
                status="error",
                next_gw=first_gw,
                projection_col=projection_col,
                note=(
                    "Transfer MILP/exact-mechanics feasibility disagreement: "
                    f"{type(exc).__name__}: {exc}"
                ),
                optimal_objective=float(plan.objective),
                action_now=first,
                contingent_future=plan.weeks[1:],
                roll_admissible=roll_admissible,
            )
        names = {
            int(row.player_id): str(row.web_name)
            for row in players[["player_id", "web_name"]]
            .drop_duplicates("player_id")
            .itertuples(index=False)
        }
        canonical_squad = _named_records(squad, xp)
        canonical_xi = _named_records(xi, xp)
        captain_id = int(mechanics.captain_id)
        vice_id = int(mechanics.vice_captain_id)
        bench_gk_id = int(mechanics.bench_gk_id)
        bench_order_ids = [int(pid) for pid in mechanics.outfield_bench_order]
        captain_name = names.get(captain_id, str(captain_id))
        vice_name = names.get(vice_id, str(vice_id))
        bench_gk_name = names.get(bench_gk_id, str(bench_gk_id))
        bench_order_names = [names.get(pid, str(pid)) for pid in bench_order_ids]
        exact_points = float(mechanics.expected_total_points)

    optimal_objective = float(plan.objective)
    regret = (
        max(optimal_objective - float(roll_objective), 0.0)
        if roll_objective is not None
        else None
    )
    return RecedingHorizonStrategy(
        status="optimal" if transition_ok else "error",
        next_gw=first_gw,
        recommended_action=action,
        recommended_transfers=transfers,
        recommended_hit=hit,
        optimal_objective=optimal_objective,
        roll_objective=roll_objective,
        roll_regret=regret,
        action_now=first,
        contingent_future=plan.weeks[1:],
        projection_col=projection_col,
        note=(
            "Execute only action_now. The submitted squad/bench was constrained in the "
            "transfer MILP and independently verified by exact FPL mechanics. Later "
            "moves are mathematical contingencies: refresh prices, minutes, injuries, "
            "transfers, roles and news before every subsequent deadline and solve again."
        ),
        canonical_squad=canonical_squad,
        canonical_xi=canonical_xi,
        canonical_captain=captain_name,
        canonical_captain_id=captain_id,
        canonical_vice_captain=vice_name,
        canonical_vice_captain_id=vice_id,
        canonical_bench_gk=bench_gk_name,
        canonical_bench_gk_id=bench_gk_id,
        canonical_outfield_bench_order=bench_order_names,
        canonical_outfield_bench_order_ids=bench_order_ids,
        canonical_expected_points=exact_points,
        state_transition_reconciled=transition_ok,
        roll_admissible=roll_admissible,
        current_bench_resilience_enforced=True,
    )
