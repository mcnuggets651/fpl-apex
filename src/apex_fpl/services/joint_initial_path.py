from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from apex_fpl.optimisation.exact_decision import (
    ExactHorizonDecision,
    optimise_exact_horizon_decision,
    optimise_fixed_squad_gameweek,
)
from apex_fpl.optimisation.transfer_views import optimise_transfer_plan_view


@dataclass(frozen=True)
class JointPathCandidate:
    source_rank: int
    squad_ids: tuple[int, ...]
    squad_names: tuple[str, ...]
    starting_cost: float
    starting_bank: float
    gw1_expected_points: float
    gw1_regret: float
    within_gw1_band: bool
    future_objective: float
    total_hit_cost: int
    weeks: tuple[dict, ...]

    def to_dict(self) -> dict:
        return {
            "source_rank": self.source_rank,
            "squad_ids": list(self.squad_ids),
            "squad_names": list(self.squad_names),
            "starting_cost": self.starting_cost,
            "starting_bank": self.starting_bank,
            "gw1_expected_points": self.gw1_expected_points,
            "gw1_regret": self.gw1_regret,
            "within_gw1_band": self.within_gw1_band,
            "future_objective": self.future_objective,
            "total_hit_cost": self.total_hit_cost,
            "weeks": list(self.weeks),
        }


@dataclass(frozen=True)
class JointInitialPathResult:
    status: str
    baseline: JointPathCandidate | None
    selected: JointPathCandidate | None
    candidates: tuple[JointPathCandidate, ...]
    best_gw1_points: float | None
    gw1_regret_tolerance: float
    gw1_floor: float | None
    small_pool_selected_ids: tuple[int, ...] | None
    full_pool_selected_ids: tuple[int, ...] | None
    candidate_pool_stable: bool
    squad_overlap: int | None
    gw1_delta_vs_static: float | None
    future_delta_vs_static: float | None
    projection_col: str
    note: str

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "selected": self.selected.to_dict() if self.selected else None,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "best_gw1_points": self.best_gw1_points,
            "gw1_regret_tolerance": self.gw1_regret_tolerance,
            "gw1_floor": self.gw1_floor,
            "small_pool_selected_ids": (
                list(self.small_pool_selected_ids) if self.small_pool_selected_ids else None
            ),
            "full_pool_selected_ids": (
                list(self.full_pool_selected_ids) if self.full_pool_selected_ids else None
            ),
            "candidate_pool_stable": self.candidate_pool_stable,
            "squad_overlap": self.squad_overlap,
            "gw1_delta_vs_static": self.gw1_delta_vs_static,
            "future_delta_vs_static": self.future_delta_vs_static,
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


def _candidate_key(candidate: JointPathCandidate) -> tuple:
    return (
        -float(candidate.future_objective),
        -float(candidate.gw1_expected_points),
        -float(candidate.starting_bank),
        tuple(candidate.squad_ids),
    )


def select_best_joint_candidate(
    candidates: list[JointPathCandidate],
) -> JointPathCandidate | None:
    eligible = [candidate for candidate in candidates if candidate.within_gw1_band]
    if not eligible:
        return None
    return min(eligible, key=_candidate_key)


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
    source_rank: int,
    transfer_candidate_limit: int,
    best_gw1_points: float,
    gw1_regret_tolerance: float,
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
    gw1_regret = max(float(best_gw1_points) - gw1_points, 0.0)
    within_band = gw1_regret <= float(gw1_regret_tolerance) + 1e-9

    future = [int(gw) for gw in gameweeks[1:]]
    if not future:
        return JointPathCandidate(
            source_rank,
            ids,
            names,
            starting_cost,
            starting_bank,
            gw1_points,
            gw1_regret,
            within_band,
            0.0,
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
    hit_cost = sum(int(week.get("hit_cost", 0) or 0) for week in transfer_plan.weeks)
    return JointPathCandidate(
        source_rank,
        ids,
        names,
        starting_cost,
        starting_bank,
        gw1_points,
        gw1_regret,
        within_band,
        float(transfer_plan.objective),
        hit_cost,
        tuple(transfer_plan.weeks),
    )


def _evaluate_exact_candidates(
    exact: ExactHorizonDecision,
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
    transfer_candidate_limit: int,
    gw1_regret_tolerance: float,
) -> list[JointPathCandidate]:
    best_gw1 = float(exact.objective)
    evaluated: list[JointPathCandidate] = []
    for row in exact.candidates:
        if best_gw1 - float(row.exact_objective) > float(gw1_regret_tolerance) + 1e-9:
            continue
        ids = {int(pid) for pid in row.squad_ids}
        squad = players[players["player_id"].astype(int).isin(ids)].copy()
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
            source_rank=int(row.generation_rank),
            transfer_candidate_limit=transfer_candidate_limit,
            best_gw1_points=best_gw1,
            gw1_regret_tolerance=gw1_regret_tolerance,
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
    transfer_candidate_limit: int = 180,
    exact_candidate_limit: int = 16,
    gw1_regret_tolerance: float = 0.25,
) -> JointInitialPathResult:
    """Choose a GW1 launch squad before valuing future transfer options.

    The opening squad is generated and exact-rescored on GW1 only. The existing
    near-equivalent points band is then a hard floor: no frozen future forecast may
    displace a launch squad by more than that GW1 expected-points tolerance. Only
    squads inside the GW1 band are ranked by the legal future transfer planner,
    which values bank, rolled free transfers and hit costs. Future moves remain
    contingencies and must be re-solved from fresh projections before each deadline.
    """
    gws = [int(gw) for gw in gameweeks]
    tolerance = max(float(gw1_regret_tolerance), 0.0)
    if not gws:
        return JointInitialPathResult(
            "unavailable", None, None, tuple(), None, tolerance, None,
            None, None, False, None, None, None, projection_col,
            "No future Gameweeks are available.",
        )

    static: ExactHorizonDecision = optimise_exact_horizon_decision(
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
    if static.status != "Optimal":
        return JointInitialPathResult(
            "infeasible", None, None, tuple(), None, tolerance, None,
            None, None, False, None, None, None, projection_col,
            "The static comparison baseline is not optimal.",
        )

    small_limit = max(int(exact_candidate_limit), 8)
    full_limit = max(small_limit * 2, small_limit + 8)
    launch_small = optimise_exact_horizon_decision(
        players,
        projections,
        [gws[0]],
        budget=budget,
        max_per_team=max_per_team,
        decay=1.0,
        candidate_limit=small_limit,
        near_equivalent_points=tolerance,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        projection_col=projection_col,
    )
    launch_full = optimise_exact_horizon_decision(
        players,
        projections,
        [gws[0]],
        budget=budget,
        max_per_team=max_per_team,
        decay=1.0,
        candidate_limit=full_limit,
        near_equivalent_points=tolerance,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        projection_col=projection_col,
    )
    if launch_small.status != "Optimal" or launch_full.status != "Optimal":
        return JointInitialPathResult(
            "infeasible", None, None, tuple(), None, tolerance, None,
            None, None, False, None, None, None, projection_col,
            "The GW1-first launch solve is not optimal.",
        )

    small_candidates = _evaluate_exact_candidates(
        launch_small,
        players,
        projections,
        gws,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        projection_col=projection_col,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        transfer_candidate_limit=transfer_candidate_limit,
        gw1_regret_tolerance=tolerance,
    )
    full_candidates = _evaluate_exact_candidates(
        launch_full,
        players,
        projections,
        gws,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        projection_col=projection_col,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        transfer_candidate_limit=transfer_candidate_limit,
        gw1_regret_tolerance=tolerance,
    )
    small = select_best_joint_candidate(small_candidates)
    selected = select_best_joint_candidate(full_candidates)
    best_gw1 = float(launch_full.objective)
    floor = best_gw1 - tolerance
    if selected is None:
        return JointInitialPathResult(
            "infeasible", None, None, tuple(full_candidates), best_gw1, tolerance,
            floor, small.squad_ids if small else None, None, False, None, None,
            None, projection_col,
            "No launch candidate survives the GW1 expected-points floor.",
        )

    baseline = _evaluate_starting_squad(
        static.solution.squad,
        players,
        projections,
        gws,
        budget=budget,
        max_per_team=max_per_team,
        decay=decay,
        projection_col=projection_col,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        source_rank=0,
        transfer_candidate_limit=transfer_candidate_limit,
        best_gw1_points=best_gw1,
        gw1_regret_tolerance=tolerance,
    )
    small_ids = small.squad_ids if small else None
    stable = bool(small_ids is not None and small_ids == selected.squad_ids)
    overlap = (
        len(set(selected.squad_ids) & set(baseline.squad_ids))
        if baseline is not None
        else None
    )
    gw1_delta = (
        float(selected.gw1_expected_points - baseline.gw1_expected_points)
        if baseline is not None
        else None
    )
    future_delta = (
        float(selected.future_objective - baseline.future_objective)
        if baseline is not None
        else None
    )

    return JointInitialPathResult(
        "optimal",
        baseline,
        selected,
        tuple(sorted(full_candidates, key=_candidate_key)),
        best_gw1,
        tolerance,
        floor,
        small_ids,
        selected.squad_ids,
        stable,
        overlap,
        gw1_delta,
        future_delta,
        projection_col,
        (
            "GW1 exact expected points are the primary launch objective. The existing "
            "near-equivalent point band is a hard floor; only then may the legal "
            "future transfer path choose between launch-equivalent squads. Execute "
            "only the current decision and rebuild projections before every later deadline."
        ),
    )
