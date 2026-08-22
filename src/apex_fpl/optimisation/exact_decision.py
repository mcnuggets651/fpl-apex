from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, permutations
import math

import pandas as pd

from apex_fpl.constants import XI_MAX, XI_MIN
from apex_fpl.optimisation.bench_policy import (
    BenchResilienceError,
    admissible_outfield_orders,
    bench_resilience_ok,
    credible_first_bench_ids,
    playable_outfield_ids,
    resolve_current_bench_resilience,
)
from apex_fpl.optimisation.initial_horizon import optimise_initial_horizon
from apex_fpl.optimisation.mechanics import (
    GameweekMechanics,
    autosub_weights_ids,
    best_captain_vice_ids,
    evaluate_gameweek_mechanics_ids,
)
from apex_fpl.optimisation.solver_status import certified_infeasible
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
                    for chosen_midfielders in combinations(
                        by_position["MID"], midfielders
                    ):
                        for chosen_forwards in combinations(
                            by_position["FWD"], forwards
                        ):
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
    xi_eligible: set[int] | None = None,
    enforce_current_bench_resilience: bool | None = None,
) -> tuple[pd.DataFrame, GameweekMechanics]:
    """Exhaustively choose the legal XI and exact current-deadline mechanics."""
    enforce = resolve_current_bench_resilience(
        squad,
        enforce_current_bench_resilience,
    )
    eligible = (
        None if captain_eligible is None else {int(pid) for pid in captain_eligible}
    )
    xi_allowed = None if xi_eligible is None else {int(pid) for pid in xi_eligible}
    squad_ids = tuple(sorted(squad["player_id"].astype(int).tolist()))
    positions = {
        int(row.player_id): str(row.position)
        for row in squad[["player_id", "position"]].itertuples(index=False)
    }
    playable = playable_outfield_ids(squad) if enforce else None
    first = credible_first_bench_ids(squad) if enforce else None
    best: tuple[float, tuple, GameweekMechanics] | None = None
    captain_legal_lineup_seen = False
    for lineup_ids in _legal_lineups(squad):
        lineup_ids = tuple(sorted(int(pid) for pid in lineup_ids))
        if xi_allowed is not None and not set(lineup_ids).issubset(xi_allowed):
            continue
        if eligible is not None and len(set(lineup_ids) & eligible) < 2:
            continue
        captain_legal_lineup_seen = True
        try:
            mechanics = evaluate_gameweek_mechanics_ids(
                squad_ids,
                lineup_ids,
                positions,
                xp,
                appearance,
                captain_eligible=eligible,
                playable_bench_ids=playable,
                first_bench_eligible_ids=first,
            )
        except BenchResilienceError:
            continue
        tie_key = (
            lineup_ids,
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
        if enforce and captain_legal_lineup_seen:
            raise BenchResilienceError(
                "fixed squad has no submitted XI satisfying governed bench resilience"
            )
        raise ValueError("fixed squad has no legal XI with two captain-eligible players")
    xi = squad[squad["player_id"].astype(int).isin(best[1][0])].copy()
    return xi, best[2]


def _order_weights(
    *,
    lineup_ids: tuple[int, ...],
    bench_ids: tuple[int, ...],
    outfield_orders: tuple[tuple[int, ...], ...],
    positions: dict[int, str],
    appearance: dict[int, float],
) -> list[tuple[tuple[int, ...], dict[int, float]]]:
    return [
        (
            order,
            autosub_weights_ids(
                lineup_ids,
                bench_ids,
                positions,
                appearance,
                outfield_order=order,
            ),
        )
        for order in outfield_orders
    ]


def _rescore_candidate(
    solution: SquadSolution,
    projections: pd.DataFrame,
    gameweeks: list[int],
    *,
    decay: float,
    captain_eligible: set[int] | None,
    xi_eligible: set[int] | None,
    projection_col: str,
    generation_rank: int,
    enforce_current_bench_resilience: bool,
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
    eligible = (
        None if captain_eligible is None else {int(pid) for pid in captain_eligible}
    )
    xi_allowed = None if xi_eligible is None else {int(pid) for pid in xi_eligible}
    playable = (
        playable_outfield_ids(solution.squad)
        if enforce_current_bench_resilience
        else set()
    )
    first = (
        credible_first_bench_ids(solution.squad)
        if enforce_current_bench_resilience
        else set()
    )
    current_gw = int(gameweeks[0])
    best_by_gw: dict[
        int, tuple[float, tuple, GameweekMechanics, tuple[int, ...]]
    ] = {}

    for lineup_ids in _legal_lineups(solution.squad):
        lineup_ids = tuple(sorted(int(pid) for pid in lineup_ids))
        if xi_allowed is not None and not set(lineup_ids).issubset(xi_allowed):
            continue
        if eligible is not None and len(set(lineup_ids) & eligible) < 2:
            continue
        bench_ids = tuple(sorted(set(squad_ids) - set(lineup_ids)))
        outfield = tuple(pid for pid in bench_ids if positions[pid] != "GK")
        bench_gk = tuple(pid for pid in bench_ids if positions[pid] == "GK")
        all_orders = tuple(
            tuple(int(pid) for pid in order)
            for order in permutations(sorted(outfield))
        )
        all_order_weights = _order_weights(
            lineup_ids=lineup_ids,
            bench_ids=bench_ids,
            outfield_orders=all_orders,
            positions=positions,
            appearance=appearance,
        )
        current_order_weights: list[tuple[tuple[int, ...], dict[int, float]]] = []
        if enforce_current_bench_resilience and bench_resilience_ok(
            outfield,
            playable_ids=playable,
            first_bench_ids=first,
        ):
            current_orders = admissible_outfield_orders(
                outfield,
                first_bench_ids=first,
            )
            current_order_weights = _order_weights(
                lineup_ids=lineup_ids,
                bench_ids=bench_ids,
                outfield_orders=current_orders,
                positions=positions,
                appearance=appearance,
            )

        for gw in gameweeks:
            gw = int(gw)
            if enforce_current_bench_resilience and gw == current_gw:
                order_weights = current_order_weights
                if not order_weights:
                    continue
            else:
                order_weights = all_order_weights

            xp = xp_by_gw[gw]
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
            xi_points = sum(
                max(float(xp.get(pid, 0.0)), 0.0) for pid in lineup_ids
            )
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
            previous = best_by_gw.get(gw)
            row = (
                float(mechanics.expected_total_points),
                tie_key,
                mechanics,
                lineup_ids,
            )
            if previous is None or row[0] > previous[0] + 1e-12 or (
                abs(row[0] - previous[0]) <= 1e-12 and row[1] < previous[1]
            ):
                best_by_gw[gw] = row

    if enforce_current_bench_resilience and current_gw not in best_by_gw:
        raise BenchResilienceError(
            "candidate squad has no exact current-Gameweek XI satisfying governed bench resilience"
        )

    weeks: list[ExactWeekDecision] = []
    objective = 0.0
    for offset, gw in enumerate(gameweeks):
        gw = int(gw)
        if gw not in best_by_gw:
            raise ValueError("candidate squad has no legal exact-mechanics XI")
        _, _, mechanics, xi_ids = best_by_gw[gw]
        discount = float(decay) ** offset
        objective += discount * float(mechanics.expected_total_points)
        weeks.append(
            ExactWeekDecision(
                gw=gw,
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
    current = selected.weeks[0]
    squad = generator.squad.copy()
    xi = squad[squad["player_id"].astype(int).isin(current.xi_ids)].copy()
    captain = squad[
        squad["player_id"].astype(int).eq(current.mechanics.captain_id)
    ].copy()
    vice = squad[
        squad["player_id"].astype(int).eq(current.mechanics.vice_captain_id)
    ].copy()
    bench_ids = (
        current.mechanics.bench_gk_id,
        *current.mechanics.outfield_bench_order,
    )
    bench_order = {int(pid): rank for rank, pid in enumerate(bench_ids)}
    bench = squad[~squad["player_id"].astype(int).isin(current.xi_ids)].copy()
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
    xi_eligible: set[int] | None = None,
    locked: set[int] | None = None,
    banned: set[int] | None = None,
    projection_col: str = "xp",
    enforce_current_bench_resilience: bool | None = None,
) -> ExactHorizonDecision:
    """Apply exact mechanics as a governed secondary selector over global max-EV."""
    if not gameweeks:
        raise ValueError("exact horizon decision requires at least one Gameweek")
    if candidate_limit < 1:
        raise ValueError("candidate_limit must be positive")
    if not 0.0 <= candidate_regret_fraction <= 0.05:
        raise ValueError("candidate_regret_fraction must be between 0 and 5%")
    if near_equivalent_points < 0.0:
        raise ValueError("near_equivalent_points cannot be negative")
    enforce = resolve_current_bench_resilience(
        players,
        enforce_current_bench_resilience,
    )

    excluded: list[set[int]] = []
    generated: list[tuple[SquadSolution, ExactCandidate]] = []
    best_approximate: float | None = None
    shortlist_floor = -math.inf
    shortlist_complete = False
    terminal_solution: SquadSolution | None = None
    generator_projection_col = (
        projection_col if projection_col in projections.columns else "risk_adjusted_xp"
    )
    for rank in range(1, int(candidate_limit) + 1):
        # Rank one is the globally optimal canonical maximum-EV solution. Every
        # later solve is a bounded secondary audit inside the configured epsilon
        # band; it is never allowed to displace rank one unless that band itself is
        # certified complete.
        governed_floor = (
            float(shortlist_floor)
            if best_approximate is not None and math.isfinite(shortlist_floor)
            else None
        )
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
            xi_eligible=xi_eligible,
            projection_col=projection_col,
            reference_projection_col=generator_projection_col,
            min_reference_objective=governed_floor,
            excluded_squads=excluded,
            solver_relative_gap=0.00001,
            solver_time_limit=120,
            enforce_current_bench_resilience=enforce,
        )
        if solution.status != "Optimal":
            terminal_solution = solution
            shortlist_complete = certified_infeasible(
                solution.status,
                solution.solver,
            )
            break
        if best_approximate is None:
            best_approximate = float(solution.objective)
            shortlist_floor = best_approximate * (1.0 - candidate_regret_fraction)
        elif float(solution.objective) < shortlist_floor - 1e-9:
            shortlist_complete = True
            break
        try:
            candidate = _rescore_candidate(
                solution,
                projections,
                gameweeks,
                decay=decay,
                captain_eligible=captain_eligible,
                xi_eligible=xi_eligible,
                projection_col=projection_col,
                generation_rank=rank,
                enforce_current_bench_resilience=enforce,
            )
        except BenchResilienceError:
            excluded.append(set(solution.squad["player_id"].astype(int)))
            continue
        generated.append((solution, candidate))
        excluded.append(set(candidate.squad_ids))

    if not generated:
        if terminal_solution is None:
            empty = players.iloc[0:0].copy()
            terminal_solution = SquadSolution(
                "SolverError",
                float("nan"),
                empty,
                empty,
                empty,
                empty,
                empty,
                {
                    "status_code": None,
                    "termination_reason": (
                        "candidate generation ended without an exact mechanics result"
                    ),
                    "current_bench_resilience_enforced": bool(enforce),
                },
            )
        return ExactHorizonDecision(
            terminal_solution.status,
            float("nan"),
            terminal_solution,
            tuple(),
            tuple(),
            shortlist_complete,
            shortlist_floor,
            int(candidate_limit),
            near_equivalent_points,
        )

    primary_solution, primary_candidate = generated[0]
    if shortlist_complete:
        selected_solution, selected = min(
            generated,
            key=lambda row: (-row[1].exact_objective, row[1].squad_ids),
        )
        selector_mode = "exact_secondary"
    else:
        # A resource ceiling is not proof that the secondary band is exhausted.
        # Fail closed on the secondary selector, not on the already-certified
        # primary objective: publish the globally optimal max-EV squad and exact-
        # rescore only its XI/captain/vice/bench mechanics.
        selected_solution, selected = primary_solution, primary_candidate
        selector_mode = "maximum_ev_fallback"

    authoritative = _authoritative_solution(selected_solution, selected)
    authoritative.solver.update(
        {
            "selection_contract": "global_max_ev_then_bounded_exact_secondary",
            "selector_mode": selector_mode,
            "global_max_ev_certified": True,
            "global_max_ev_objective": float(primary_solution.objective),
            "global_max_ev_squad_ids": list(primary_candidate.squad_ids),
            "secondary_exact_selector_certified": bool(shortlist_complete),
            "secondary_candidate_count": len(generated),
            "secondary_candidate_limit": int(candidate_limit),
            "secondary_regret_fraction": float(candidate_regret_fraction),
            "secondary_shortlist_floor": float(shortlist_floor),
            "authoritative_objective": (
                "exact_horizon_fpl_mechanics_within_certified_max_ev_band"
                if shortlist_complete
                else "global_max_ev_with_exact_horizon_mechanics"
            ),
        }
    )
    if terminal_solution is not None and not certified_infeasible(
        terminal_solution.status,
        terminal_solution.solver,
    ):
        authoritative.solver.update(
            {
                "shortlist_terminal_status": terminal_solution.status,
                "shortlist_terminal_solver": dict(terminal_solution.solver or {}),
            }
        )
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