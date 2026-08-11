from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations
import math

import pandas as pd

from apex_fpl.constants import XI_MAX, XI_MIN
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import (
    GameweekMechanics,
    autosub_weights_ids,
    best_captain_vice_ids,
    evaluate_gameweek_mechanics_ids,
)
from apex_fpl.optimisation.squad import SquadSolution


@dataclass(frozen=True)
class ExactWeekDecision:
    gw: int
    discount: float
    xi_ids: tuple[int, ...]
    mechanics: GameweekMechanics


@dataclass(frozen=True)
class ExactCandidate:
    generation_rank: int
    approximate_objective: float
    squad_ids: tuple[int, ...]
    exact_objective: float
    weeks: tuple[ExactWeekDecision, ...]
    generator_solver: dict


@dataclass(frozen=True)
class ExactHorizonDecision:
    status: str
    objective: float
    solution: SquadSolution
    weeks: tuple[ExactWeekDecision, ...]
    candidates: tuple[ExactCandidate, ...]
    shortlist_complete: bool
    shortlist_floor: float
    candidate_limit: int
    near_equivalent_points: float

    @property
    def near_equivalent_candidates(self) -> tuple[ExactCandidate, ...]:
        return tuple(
            candidate
            for candidate in self.candidates
            if self.objective - candidate.exact_objective
            <= self.near_equivalent_points + 1e-12
        )


def _projection_map(
    projections: pd.DataFrame,
    gw: int,
    projection_col: str,
) -> dict[int, float]:
    rows = projections[projections["gw"] == int(gw)]
    if projection_col not in rows.columns:
        raise ValueError(f"projection table requires {projection_col!r}")
    values = rows.groupby("player_id")[projection_col].sum()
    return {int(pid): float(value) for pid, value in values.items()}


def _appearance_map(players: pd.DataFrame) -> dict[int, float]:
    values = pd.to_numeric(
        players.get("appearance_probability", pd.Series(1.0, index=players.index)),
        errors="coerce",
    ).fillna(1.0)
    return {
        int(pid): min(max(float(value), 0.0), 1.0)
        for pid, value in zip(players["player_id"].astype(int), values)
    }


def _legal_lineups(squad: pd.DataFrame):
    by_position = {
        position: tuple(
            sorted(
                squad.loc[squad["position"] == position, "player_id"]
                .astype(int)
                .tolist()
            )
        )
        for position in ("GK", "DEF", "MID", "FWD")
    }
    for goalkeeper in by_position["GK"]:
        for defenders in range(XI_MIN["DEF"], XI_MAX["DEF"] + 1):
            for midfielders in range(XI_MIN["MID"], XI_MAX["MID"] + 1):
                forwards = 10 - defenders - midfielders
                if not XI_MIN["FWD"] <= forwards <= XI_MAX["FWD"]:
                    continue
                for chosen_defenders in combinations(by_position["DEF"], defenders):
                    for chosen_midfielders in combinations(by_position["MID"], midfielders):
                        for chosen_forwards in combinations(by_position["FWD"], forwards):
                            yield (
                                int(goalkeeper),
                                *chosen_defenders,
                                *chosen_midfielders,
                                *chosen_forwards,
                            )


def optimise_fixed_squad_gameweek(
    squad: pd.DataFrame,
    xp: dict[int, float],
    appearance: dict[int, float],
    *,
    captain_eligible: set[int] | None = None,
) -> tuple[pd.DataFrame, GameweekMechanics]:
    """Exhaustively choose the legal XI and exact deadline mechanics for a squad."""
    eligible = None if captain_eligible is None else {int(pid) for pid in captain_eligible}
    squad_ids = tuple(sorted(squad["player_id"].astype(int).tolist()))
    positions = {
        int(row.player_id): str(row.position)
        for row in squad[["player_id", "position"]].itertuples(index=False)
    }
    best: tuple[float, tuple, GameweekMechanics] | None = None
    for lineup_ids in _legal_lineups(squad):
        if eligible is not None and len(set(lineup_ids) & eligible) < 2:
            continue
        mechanics = evaluate_gameweek_mechanics_ids(
            squad_ids,
            tuple(sorted(int(pid) for pid in lineup_ids)),
            positions,
            xp,
            appearance,
            captain_eligible=eligible,
        )
        tie_key = (
            tuple(sorted(int(pid) for pid in lineup_ids)),
            int(mechanics.captain_id),
            int(mechanics.vice_captain_id),
            tuple(int(pid) for pid in mechanics.outfield_bench_order),
        )
        row = (float(mechanics.expected_total_points), tie_key, mechanics)
        if best is None or row[0] > best[0] + 1e-12 or (
            abs(row[0] - best[0]) <= 1e-12 and row[1] < best[1]
        ):
            best = row
    if best is None:
        raise ValueError("fixed squad has no legal XI with two captain-eligible players")
    xi = squad[squad["player_id"].astype(int).isin(best[1][0])].copy()
    return xi, best[2]


def _rescore_candidate(
    solution: SquadSolution,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    decay: float,
    captain_eligible: set[int] | None,
    projection_col: str,
    generation_rank: int,
) -> ExactCandidate:
    appearance = _appearance_map(solution.squad)
    squad_ids = tuple(sorted(solution.squad["player_id"].astype(int).tolist()))
    positions = {
        int(row.player_id): str(row.position)
        for row in solution.squad[["player_id", "position"]].itertuples(index=False)
    }
    xp_by_gw = {
        int(gw): _projection_map(projections, int(gw), projection_col)
        for gw in gameweeks
    }
    eligible = None if captain_eligible is None else {int(pid) for pid in captain_eligible}
    best_by_gw: dict[int, tuple[float, tuple, GameweekMechanics, tuple[int, ...]]] = {}

    for lineup_ids in _legal_lineups(solution.squad):
        lineup_ids = tuple(sorted(int(pid) for pid in lineup_ids))
        if eligible is not None and len(set(lineup_ids) & eligible) < 2:
            continue
        bench_ids = tuple(sorted(set(squad_ids) - set(lineup_ids)))
        outfield = tuple(pid for pid in bench_ids if positions[pid] != "GK")
        bench_gk = tuple(pid for pid in bench_ids if positions[pid] == "GK")
        order_weights = [
            (
                tuple(int(pid) for pid in order),
                autosub_weights_ids(
                    lineup_ids,
                    bench_ids,
                    positions,
                    appearance,
                    outfield_order=tuple(int(pid) for pid in order),
                ),
            )
            for order in permutations(sorted(outfield))
        ]
        for gw in gameweeks:
            xp = xp_by_gw[int(gw)]
            captain, vice, captain_bonus = best_captain_vice_ids(
                lineup_ids,
                xp,
                appearance,
                captain_eligible=eligible,
            )
            autosub, bench_order = max(
                (
                    sum(
                        weight * max(float(xp.get(pid, 0.0)), 0.0)
                        for pid, weight in weights.items()
                    ),
                    tuple(-pid for pid in order),
                    order,
                )
                for order, weights in order_weights
            )[::2]
            xi_points = sum(max(float(xp.get(pid, 0.0)), 0.0) for pid in lineup_ids)
            mechanics = GameweekMechanics(
                expected_xi_points=float(xi_points),
                expected_autosub_points=float(autosub),
                expected_captain_bonus=float(captain_bonus),
                expected_total_points=float(xi_points + autosub + captain_bonus),
                captain_id=int(captain),
                vice_captain_id=int(vice),
                bench_gk_id=int(bench_gk[0]),
                outfield_bench_order=tuple(int(pid) for pid in bench_order),
            )
            tie_key = (
                lineup_ids,
                int(captain),
                int(vice),
                tuple(int(pid) for pid in bench_order),
            )
            previous = best_by_gw.get(int(gw))
            row = (float(mechanics.expected_total_points), tie_key, mechanics, lineup_ids)
            if previous is None or row[0] > previous[0] + 1e-12 or (
                abs(row[0] - previous[0]) <= 1e-12 and row[1] < previous[1]
            ):
                best_by_gw[int(gw)] = row

    weeks: list[ExactWeekDecision] = []
    objective = 0.0
    for offset, gw in enumerate(gameweeks):
        if int(gw) not in best_by_gw:
            raise ValueError("candidate squad has no legal exact-mechanics XI")
        _, _, mechanics, xi_ids = best_by_gw[int(gw)]
        discount = float(decay) ** offset
        objective += discount * float(mechanics.expected_total_points)
        weeks.append(
            ExactWeekDecision(
                gw=int(gw),
                discount=discount,
                xi_ids=xi_ids,
                mechanics=mechanics,
            )
        )
    return ExactCandidate(
        generation_rank=int(generation_rank),
        approximate_objective=float(solution.objective),
        squad_ids=tuple(sorted(solution.squad["player_id"].astype(int).tolist())),
        exact_objective=float(objective),
        weeks=tuple(weeks),
        generator_solver=dict(solution.solver),
    )


def _authoritative_solution(
    generator: SquadSolution,
    selected: ExactCandidate,
) -> SquadSolution:
    gw1 = selected.weeks[0]
    squad = generator.squad.copy()
    xi = squad[squad["player_id"].astype(int).isin(gw1.xi_ids)].copy()
    captain = squad[
        squad["player_id"].astype(int).eq(gw1.mechanics.captain_id)
    ].copy()
    vice = squad[
        squad["player_id"].astype(int).eq(gw1.mechanics.vice_captain_id)
    ].copy()
    bench_ids = (
        gw1.mechanics.bench_gk_id,
        *gw1.mechanics.outfield_bench_order,
    )
    bench_order = {int(pid): rank for rank, pid in enumerate(bench_ids)}
    bench = squad[~squad["player_id"].astype(int).isin(gw1.xi_ids)].copy()
    bench["exact_bench_rank"] = bench["player_id"].astype(int).map(bench_order)
    bench = bench.sort_values("exact_bench_rank")
    solver = dict(generator.solver)
    solver.update(
        {
            "authoritative_objective": "exact_horizon_fpl_mechanics",
            "shortlist_generation_objective": "approximate_flat_bench_milp",
        }
    )
    return SquadSolution(
        status="Optimal",
        objective=float(selected.exact_objective),
        squad=squad,
        xi=xi,
        captain=captain,
        vice_captain=vice,
        bench=bench,
        solver=solver,
    )


def optimise_exact_horizon_decision(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    budget: float = 100.0,
    max_per_team: int = 3,
    decay: float = 0.90,
    shortlist_bench_weight: float = 0.08,
    candidate_limit: int = 16,
    candidate_regret_fraction: float = 0.005,
    near_equivalent_points: float = 0.25,
    captain_eligible: set[int] | None = None,
    locked: set[int] | None = None,
    banned: set[int] | None = None,
    projection_col: str = "xp",
) -> ExactHorizonDecision:
    """Select one authoritative squad using exact mechanics across the horizon.

    The MILP is deliberately a candidate generator. Distinct squads inside a
    transparent approximate-xP band are rescored with exhaustive legal XI choice,
    captain/vice fallback and autosub order for every Gameweek.
    """
    if not gameweeks:
        raise ValueError("exact horizon decision requires at least one Gameweek")
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    if not 0.0 <= candidate_regret_fraction <= 0.05:
        raise ValueError("candidate_regret_fraction must be between 0 and 5%")
    if near_equivalent_points < 0.0:
        raise ValueError("near_equivalent_points cannot be negative")

    excluded: list[set[int]] = []
    generated: list[tuple[SquadSolution, ExactCandidate]] = []
    best_approximate: float | None = None
    shortlist_floor = -math.inf
    shortlist_complete = False
    for rank in range(1, int(candidate_limit) + 1):
        solution = optimise_initial_horizon(
            players,
            projections,
            gameweeks,
            budget=budget,
            max_per_team=max_per_team,
            decay=decay,
            bench_weight=shortlist_bench_weight,
            locked=locked,
            banned=banned,
            captain_eligible=captain_eligible,
            projection_col=projection_col,
            excluded_squads=excluded,
            solver_relative_gap=0.00001,
            solver_time_limit=120,
        )
        if solution.status != "Optimal":
            shortlist_complete = True
            break
        if best_approximate is None:
            best_approximate = float(solution.objective)
            shortlist_floor = best_approximate * (1.0 - candidate_regret_fraction)
        elif float(solution.objective) < shortlist_floor - 1e-9:
            shortlist_complete = True
            break
        candidate = _rescore_candidate(
            solution,
            projections,
            gameweeks,
            decay=decay,
            captain_eligible=captain_eligible,
            projection_col=projection_col,
            generation_rank=rank,
        )
        generated.append((solution, candidate))
        excluded.append(set(candidate.squad_ids))

    if not generated:
        empty = players.iloc[0:0].copy()
        infeasible = SquadSolution(
            "Infeasible", float("nan"), empty, empty, empty, empty, empty
        )
        return ExactHorizonDecision(
            "Infeasible",
            float("nan"),
            infeasible,
            tuple(),
            tuple(),
            shortlist_complete,
            shortlist_floor,
            int(candidate_limit),
            near_equivalent_points,
        )

    selected_solution, selected = min(
        generated,
        key=lambda row: (-row[1].exact_objective, row[1].squad_ids),
    )
    authoritative = _authoritative_solution(selected_solution, selected)
    candidates = tuple(
        sorted(
            (candidate for _, candidate in generated),
            key=lambda candidate: (-candidate.exact_objective, candidate.squad_ids),
        )
    )
    return ExactHorizonDecision(
        status="Optimal",
        objective=float(selected.exact_objective),
        solution=authoritative,
        weeks=selected.weeks,
        candidates=candidates,
        shortlist_complete=shortlist_complete,
        shortlist_floor=float(shortlist_floor),
        candidate_limit=int(candidate_limit),
        near_equivalent_points=float(near_equivalent_points),
    )
