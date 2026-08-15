from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from apex_fpl.optimisation.exact_decision import (
    ExactHorizonDecision,
    optimise_exact_horizon_decision,
    optimise_fixed_squad_gameweek,
)
from apex_fpl.optimisation.transfer_views import (
    optimise_initial_transfer_plan_view,
    optimise_transfer_plan_view,
)


@dataclass(frozen=True)
class JointPathCandidate:
    source_horizon: int
    source_rank: int
    squad_ids: tuple[int, ...]
    squad_names: tuple[str, ...]
    starting_cost: float
    starting_bank: float
    gw1_expected_points: float
    future_objective: float
    total_objective: float
    total_hit_cost: int
    weeks: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "source_horizon": self.source_horizon,
            "source_rank": self.source_rank,
            "squad_ids": list(self.squad_ids),
            "squad_names": list(self.squad_names),
            "starting_cost": self.starting_cost,
            "starting_bank": self.starting_bank,
            "gw1_expected_points": self.gw1_expected_points,
            "future_objective": self.future_objective,
            "total_objective": self.total_objective,
            "total_hit_cost": self.total_hit_cost,
            "weeks": list(self.weeks),
        }


@dataclass(frozen=True)
class JointInitialPathResult:
    status: str
    baseline: JointPathCandidate | None
    selected: JointPathCandidate | None
    candidates: tuple[JointPathCandidate, ...]
    small_pool_selected_ids: tuple[int, ...] | None
    full_pool_selected_ids: tuple[int, ...] | None
    candidate_pool_stable: bool
    gain_vs_baseline: float | None
    squad_overlap: int | None
    projection_col: str
    note: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "selected": self.selected.to_dict() if self.selected else None,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "small_pool_selected_ids": (
                list(self.small_pool_selected_ids) if self.small_pool_selected_ids else None
            ),
            "full_pool_selected_ids": (
                list(self.full_pool_selected_ids) if self.full_pool_selected_ids else None
            ),
            "candidate_pool_stable": self.candidate_pool_stable,
            "gain_vs_baseline": self.gain_vs_baseline,
            "squad_overlap": self.squad_overlap,
            "projection_col": self.projection_col,
            "note": self.note,
        }


def _projection_map(
    projections: pd.DataFrame,
    gw: int,
    projection_col: str,
) -> dict[int, float]:
    rows = projections[projections["gw"].astype(int).eq(int(gw))]
    if projection_col not in rows.columns:
        raise ValueError(f"projection table requires {projection_col!r}")
    grouped = rows.groupby("player_id")[projection_col].sum()
    return {int(pid): float(value) for pid, value in grouped.items()}


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    values = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): min(max(float(prob), 0.0), 1.0)
        for pid, prob in zip(players["player_id"].astype(int), values)
    }


def _candidate_key(candidate: JointPathCandidate) -> tuple[float, tuple[int, ...]]:
    return (-float(candidate.total_objective), tuple(candidate.squad_ids))


def select_best_joint_candidate(
    candidates: list[JointPathCandidate],
) -> JointPathCandidate | None:
    if not candidates:
        return None
    return min(candidates, key=_candidate_key)


def _evaluate_starting_squad(
    squad: pd.DataFrame,
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    budget: float,
    max_per_team: int,
    decay: float,
    projection_col: str,
    captain_eligible: set[int] | None,
    xi_eligible: set[int] | None,
    source_horizon: int,
    source_rank: int,
    transfer_candidate_limit: int,
) -> JointPathCandidate | None:
    ids = tuple(sorted(squad["player_id"].astype(int).tolist()))
    if len(ids) != 15:
        return None
    prices = pd.to_numeric(squad["price"], errors="coerce").fillna(0.0)
    starting_cost = float(prices.sum())
    starting_bank = max(float(budget) - starting_cost, 0.0)
    names = tuple(
        sorted(
            squad["web_name"].astype(str).tolist()
            if "web_name" in squad.columns
            else [str(pid) for pid in ids]
        )
    )

    gw1 = int(gameweeks[0])
    _, mechanics = optimise_fixed_squad_gameweek(
        squad,
        _projection_map(projections, gw1, projection_col),
        _appearance_map(players),
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
    )
    gw1_points = float(mechanics.expected_total_points)

    future = [int(gw) for gw in gameweeks[1:]]
    if not future:
        return JointPathCandidate(
            source_horizon,
            source_rank,
            ids,
            names,
            starting_cost,
            starting_bank,
            gw1_points,
            0.0,
            gw1_points,
            0,
            tuple(),
        )

    selling_prices = {
        int(row.player_id): float(row.price)
        for row in squad[["player_id", "price"]].itertuples(index=False)
    }
    transfer_plan = optimise_transfer_plan_view(
        players,
        projections,
        future,
        set(ids),
        projection_col=projection_col,
        bank=starting_bank,
        free_transfers=1,
        max_per_team=max_per_team,
        decay=decay,
        selling_prices=selling_prices,
        candidate_limit=transfer_candidate_limit,
        captain_eligible=captain_eligible,
    )
    if transfer_plan.status != "Optimal":
        return None
    future_objective = float(transfer_plan.objective)
    total_objective = gw1_points + float(decay) * future_objective
    hit_cost = sum(int(week.get("hit_cost", 0) or 0) for week in transfer_plan.weeks)
    return JointPathCandidate(
        source_horizon,
        source_rank,
        ids,
        names,
        starting_cost,
        starting_bank,
        gw1_points,
        future_objective,
        total_objective,
        hit_cost,
        tuple(transfer_plan.weeks),
    )


def _squad_from_plan_week(players: pd.DataFrame, week: dict) -> pd.DataFrame:
    ids = {
        int(row["player_id"])
        for row in (week.get("squad") or [])
        if row.get("player_id") is not None
    }
    return players[players["player_id"].astype(int).isin(ids)].copy()


def _enumerate_free_initial_candidates(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    budget: float,
    max_per_team: int,
    decay: float,
    projection_col: str,
    captain_eligible: set[int] | None,
    xi_eligible: set[int] | None,
    candidate_pool_limit: int,
    candidate_count: int,
    evaluation_transfer_limit: int,
) -> list[JointPathCandidate]:
    """Generate distinct free-GW1 paths and exact-rescore their starting squads."""
    excluded: list[set[int]] = []
    evaluated: list[JointPathCandidate] = []
    for rank in range(1, max(int(candidate_count), 1) + 1):
        plan = optimise_initial_transfer_plan_view(
            players,
            projections,
            gameweeks,
            projection_col=projection_col,
            candidate_limit=candidate_pool_limit,
            budget=budget,
            max_per_team=max_per_team,
            decay=decay,
            captain_eligible=captain_eligible,
            xi_eligible=xi_eligible,
            excluded_initial_squads=excluded,
            solver_relative_gap=0.0005,
            solver_time_limit=120,
        )
        if plan.status != "Optimal" or not plan.weeks:
            break
        squad = _squad_from_plan_week(players, plan.weeks[0])
        ids = set(squad["player_id"].astype(int))
        if len(ids) != 15:
            break
        excluded.append(ids)
        candidate = _evaluate_starting_squad(
            squad,
            players,
            projections,
            gameweeks,
            budget=budget,
            max_per_team=max_per_team,
            decay=decay,
            projection_col=projection_col,
            captain_eligible=captain_eligible,
            xi_eligible=xi_eligible,
            source_horizon=len(gameweeks),
            source_rank=rank,
            transfer_candidate_limit=evaluation_transfer_limit,
        )
        if candidate is not None:
            evaluated.append(candidate)
    return evaluated


def optimise_joint_initial_path(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    budget: float = 100.0,
    max_per_team: int = 3,
    decay: float = 0.90,
    projection_col: str = "xp",
    captain_eligible: set[int] | None = None,
    xi_eligible: set[int] | None = None,
    per_view_candidates: int = 3,
    transfer_candidate_limit: int = 180,
    exact_candidate_limit: int = 16,
) -> JointInitialPathResult:
    """Choose the GW1 state by valuing its legal transfer policy, not a static hold.

    The production static exact-horizon squad remains the comparison baseline. The
    challenger now solves the correct pre-GW1 state directly: the first 15 are free
    decision variables under budget, GW2 starts with one free transfer, and every
    later squad follows legal transfer/bank/hit transitions. Distinct near-optimal
    starting squads from that joint MILP are exact-rescored for GW1 and then run
    through the existing future transfer planner.

    A smaller and an expanded position/price-aware candidate universe must select
    the same exact-rescored starting 15 before the existing promotion gate may act.
    """
    gws = [int(gw) for gw in gameweeks]
    if not gws:
        return JointInitialPathResult(
            "unavailable",
            None,
            None,
            tuple(),
            None,
            None,
            False,
            None,
            None,
            projection_col,
            "No future Gameweeks are available.",
        )

    exact: ExactHorizonDecision = optimise_exact_horizon_decision(
        players,
        projections,
        gws,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        candidate_limit=exact_candidate_limit,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        projection_col=projection_col,
    )
    if exact.status != "Optimal":
        return JointInitialPathResult(
            "infeasible",
            None,
            None,
            tuple(),
            None,
            None,
            False,
            None,
            None,
            projection_col,
            "The static exact-horizon baseline is not optimal.",
        )

    baseline = _evaluate_starting_squad(
        exact.solution.squad,
        players,
        projections,
        gws,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        projection_col=projection_col,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        source_horizon=len(gws),
        source_rank=0,
        transfer_candidate_limit=transfer_candidate_limit,
    )
    if baseline is None:
        return JointInitialPathResult(
            "infeasible",
            None,
            None,
            tuple(),
            None,
            None,
            False,
            None,
            None,
            projection_col,
            "The canonical starting squad has no optimal future transfer path.",
        )

    small_limit = max(110, min(int(transfer_candidate_limit), 150))
    full_limit = max(int(transfer_candidate_limit), 220)
    candidate_count = max(int(per_view_candidates), 3)

    small_candidates = _enumerate_free_initial_candidates(
        players,
        projections,
        gws,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        projection_col=projection_col,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        candidate_pool_limit=small_limit,
        candidate_count=candidate_count,
        evaluation_transfer_limit=full_limit,
    )
    full_candidates = _enumerate_free_initial_candidates(
        players,
        projections,
        gws,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        projection_col=projection_col,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        candidate_pool_limit=full_limit,
        candidate_count=candidate_count,
        evaluation_transfer_limit=full_limit,
    )

    small = select_best_joint_candidate(small_candidates)
    selected = select_best_joint_candidate(full_candidates)
    if selected is None:
        return JointInitialPathResult(
            "infeasible",
            baseline,
            None,
            tuple(full_candidates),
            small.squad_ids if small else None,
            None,
            False,
            None,
            None,
            projection_col,
            "The free-GW1 multi-period solver produced no exact-rescorable path.",
        )

    small_ids = small.squad_ids if small else None
    stable = bool(small_ids is not None and small_ids == selected.squad_ids)
    gain = float(selected.total_objective - baseline.total_objective)
    overlap = len(set(selected.squad_ids) & set(baseline.squad_ids))

    return JointInitialPathResult(
        "optimal",
        baseline,
        selected,
        tuple(sorted(full_candidates, key=_candidate_key)),
        small_ids,
        selected.squad_ids,
        stable,
        gain,
        overlap,
        projection_col,
        (
            "GW1 is optimised as a free initial squad inside the multi-period path. "
            "GW2 starts with one free transfer; later moves respect rolled FTs, bank, "
            "fixed current prices and explicit hit costs. Candidate paths are exact-"
            "rescored for GW1 and future moves remain contingencies to re-solve before "
            "each deadline."
        ),
    )
