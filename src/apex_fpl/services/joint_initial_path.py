from __future__ import annotations

from dataclasses import dataclass, replace

import pandas as pd

from apex_fpl.optimisation.bench_policy import BenchResilienceError
from apex_fpl.optimisation.exact_decision import (
    ExactHorizonDecision,
    optimise_exact_horizon_decision,
    optimise_fixed_squad_gameweek,
)
from apex_fpl.optimisation.transfers import TransferPlan
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


class _TransferPlanInconclusive(RuntimeError):
    pass


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


def _plan_bound_cannot_beat(
    plan: TransferPlan,
    best_future_objective: float | None,
) -> bool:
    if best_future_objective is None or plan.objective_upper_bound is None:
        return False
    # Strict inequality preserves every deterministic tie-break path. A candidate
    # whose certified upper bound can still tie the incumbent must be resolved.
    return float(plan.objective_upper_bound) < float(best_future_objective) - 1e-9


def _transfer_plan_or_prune(
    players: pd.DataFrame,
    projections: pd.DataFrame,
    future: list[int],
    ids: tuple[int, ...],
    *,
    projection_col: str,
    starting_bank: float,
    max_per_team: int,
    decay: float,
    selling_prices: dict[int, float],
    transfer_candidate_limit: int,
    captain_eligible: set[int] | None,
    best_future_objective: float | None,
    scan_time_limit: float,
    retry_time_limit: float,
    source_rank: int,
) -> TransferPlan | None:
    def run(limit: float) -> TransferPlan:
        return optimise_transfer_plan_view(
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
            solver_time_limit=max(float(limit), 0.01),
        )

    plan = run(scan_time_limit)
    if plan.status == "Optimal":
        return plan
    if plan.status.startswith("Infeasible"):
        return None
    if plan.status == "SolverLimit" and _plan_bound_cannot_beat(
        plan, best_future_objective
    ):
        return None

    if plan.status == "SolverLimit" and float(retry_time_limit) > float(scan_time_limit):
        plan = run(retry_time_limit)
        if plan.status == "Optimal":
            return plan
        if plan.status.startswith("Infeasible"):
            return None
        if plan.status == "SolverLimit" and _plan_bound_cannot_beat(
            plan, best_future_objective
        ):
            return None

    detail = plan.solver_message or "no solver message"
    bound = (
        f"{float(plan.objective_upper_bound):.6f}"
        if plan.objective_upper_bound is not None
        else "unknown"
    )
    raise _TransferPlanInconclusive(
        f"launch rank {source_rank} transfer plan ended {plan.status} "
        f"(solver_status={plan.solver_status_code}, upper_bound={bound}; {detail})"
    )


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
    best_future_objective: float | None = None,
    transfer_scan_time_limit: float = 15.0,
    transfer_retry_time_limit: float = 60.0,
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

    current_gw = int(gameweeks[0])
    try:
        _, mechanics = optimise_fixed_squad_gameweek(
            squad,
            _projection_map(projections, current_gw, projection_col),
            _appearance_map(players),
            captain_eligible=captain_eligible,
            xi_eligible=xi_eligible,
            enforce_current_bench_resilience=True,
        )
    except BenchResilienceError:
        return None
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
    transfer_plan = _transfer_plan_or_prune(
        players,
        projections,
        future,
        ids,
        projection_col=projection_col,
        starting_bank=starting_bank,
        max_per_team=max_per_team,
        decay=decay,
        selling_prices=selling_prices,
        transfer_candidate_limit=transfer_candidate_limit,
        captain_eligible=captain_eligible,
        best_future_objective=best_future_objective,
        scan_time_limit=transfer_scan_time_limit,
        retry_time_limit=transfer_retry_time_limit,
        source_rank=source_rank,
    )
    if transfer_plan is None:
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


def _future_proxy_scores(
    projections: pd.DataFrame,
    gameweeks: list[int],
    projection_col: str,
    decay: float,
) -> dict[int, float]:
    scores: dict[int, float] = {}
    for offset, gw in enumerate(gameweeks[1:]):
        rows = projections[projections["gw"].astype(int).eq(int(gw))]
        if projection_col not in rows.columns:
            continue
        values = rows.groupby("player_id")[projection_col].sum()
        weight = float(decay) ** offset
        for pid, value in values.items():
            scores[int(pid)] = scores.get(int(pid), 0.0) + weight * float(value)
    return scores


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
    min_source_rank: int = 1,
    max_source_rank: int | None = None,
    existing_candidates: list[JointPathCandidate] | None = None,
    transfer_scan_time_limit: float = 15.0,
    transfer_retry_time_limit: float = 60.0,
) -> list[JointPathCandidate]:
    best_gw1 = float(exact.objective)
    upper_rank = int(max_source_rank) if max_source_rank is not None else 10**9
    rows = [
        row
        for row in exact.candidates
        if int(min_source_rank) <= int(row.generation_rank) <= upper_rank
        and best_gw1 - float(row.exact_objective)
        <= float(gw1_regret_tolerance) + 1e-9
    ]
    proxy = _future_proxy_scores(projections, gameweeks, projection_col, decay)
    rows.sort(
        key=lambda row: (
            -sum(float(proxy.get(int(pid), 0.0)) for pid in row.squad_ids),
            int(row.generation_rank),
            tuple(int(pid) for pid in row.squad_ids),
        )
    )

    previous = list(existing_candidates or [])
    best_future = max(
        (
            float(candidate.future_objective)
            for candidate in previous
            if candidate.within_gw1_band
        ),
        default=None,
    )
    evaluated: list[JointPathCandidate] = []
    for row in rows:
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
            best_future_objective=best_future,
            transfer_scan_time_limit=transfer_scan_time_limit,
            transfer_retry_time_limit=transfer_retry_time_limit,
        )
        if candidate is not None:
            evaluated.append(candidate)
            if candidate.within_gw1_band and (
                best_future is None or candidate.future_objective > best_future
            ):
                best_future = float(candidate.future_objective)
    return evaluated


def _rebase_gw1_band(
    candidates: list[JointPathCandidate],
    best_gw1_points: float,
    tolerance: float,
) -> list[JointPathCandidate]:
    rebased: list[JointPathCandidate] = []
    for candidate in candidates:
        regret = max(float(best_gw1_points) - float(candidate.gw1_expected_points), 0.0)
        rebased.append(
            replace(
                candidate,
                gw1_regret=regret,
                within_gw1_band=regret <= float(tolerance) + 1e-9,
            )
        )
    return rebased


def _winner_through_rank(
    candidates: list[JointPathCandidate],
    source_rank: int,
) -> JointPathCandidate | None:
    return select_best_joint_candidate(
        [candidate for candidate in candidates if int(candidate.source_rank) <= int(source_rank)]
    )


def _candidate_with_source_rank(
    candidate: JointPathCandidate,
    source_rank: int,
) -> JointPathCandidate:
    return replace(candidate, source_rank=int(source_rank))


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
    transfer_scan_time_limit: float = 15.0,
    transfer_retry_time_limit: float = 60.0,
) -> JointInitialPathResult:
    """Choose the current launch squad before valuing future transfer options.

    Current-Gameweek exact expected points remain the primary launch objective.
    Future legal transfer option value can only distinguish squads inside the
    existing near-equivalent point band. The submitted XI/bench is additionally
    constrained by the governed current-deadline resilience policy; that policy is
    deliberately not projected onto later transfer-plan Gameweeks.
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
        enforce_current_bench_resilience=True,
    )
    if static.status != "Optimal":
        return JointInitialPathResult(
            "infeasible", None, None, tuple(), None, tolerance, None,
            None, None, False, None, None, None, projection_col,
            "The static comparison baseline is not optimal.",
        )

    base_prefix = max(int(exact_candidate_limit), 16)
    initial_launch_limit = max(base_prefix * 3, 48)
    extended_launch_limit = max(base_prefix * 4, 64)
    launch = optimise_exact_horizon_decision(
        players,
        projections,
        [gws[0]],
        budget=budget,
        max_per_team=max_per_team,
        decay=1.0,
        candidate_limit=initial_launch_limit,
        near_equivalent_points=tolerance,
        captain_eligible=captain_eligible,
        xi_eligible=xi_eligible,
        projection_col=projection_col,
        enforce_current_bench_resilience=True,
    )
    if launch.status != "Optimal":
        return JointInitialPathResult(
            "infeasible", None, None, tuple(), None, tolerance, None,
            None, None, False, None, None, None, projection_col,
            "The current-Gameweek-first launch solve is not optimal.",
        )

    evaluated: list[JointPathCandidate] = []
    current_prefix = min(base_prefix * 2, initial_launch_limit)
    previous_winner: JointPathCandidate | None = None
    selected: JointPathCandidate | None = None
    stable = False
    comparison_left = current_prefix
    comparison_right = current_prefix

    try:
        evaluated.extend(
            _evaluate_exact_candidates(
                launch,
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
                min_source_rank=1,
                max_source_rank=current_prefix,
                existing_candidates=evaluated,
                transfer_scan_time_limit=transfer_scan_time_limit,
                transfer_retry_time_limit=transfer_retry_time_limit,
            )
        )
        selected = _winner_through_rank(evaluated, current_prefix)
        max_generated_rank = max(
            (int(row.generation_rank) for row in launch.candidates),
            default=0,
        )
        stable = bool(launch.shortlist_complete and max_generated_rank <= current_prefix)

        if not stable and current_prefix < initial_launch_limit:
            next_prefix = initial_launch_limit
            evaluated.extend(
                _evaluate_exact_candidates(
                    launch,
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
                    min_source_rank=current_prefix + 1,
                    max_source_rank=next_prefix,
                    existing_candidates=evaluated,
                    transfer_scan_time_limit=transfer_scan_time_limit,
                    transfer_retry_time_limit=transfer_retry_time_limit,
                )
            )
            previous_winner = selected
            comparison_left = current_prefix
            current_prefix = next_prefix
            comparison_right = current_prefix
            selected = _winner_through_rank(evaluated, current_prefix)
            complete = bool(launch.shortlist_complete and max_generated_rank <= current_prefix)
            stable = bool(
                complete
                or (
                    previous_winner is not None
                    and selected is not None
                    and previous_winner.squad_ids == selected.squad_ids
                )
            )

        if not stable and not launch.shortlist_complete and current_prefix < extended_launch_limit:
            extended = optimise_exact_horizon_decision(
                players,
                projections,
                [gws[0]],
                budget=budget,
                max_per_team=max_per_team,
                decay=1.0,
                candidate_limit=extended_launch_limit,
                near_equivalent_points=tolerance,
                captain_eligible=captain_eligible,
                xi_eligible=xi_eligible,
                projection_col=projection_col,
                enforce_current_bench_resilience=True,
            )
            if extended.status != "Optimal":
                raise _TransferPlanInconclusive(
                    "extended current-Gameweek launch shortlist did not solve optimally"
                )
            launch = extended
            evaluated = _rebase_gw1_band(evaluated, float(launch.objective), tolerance)
            next_prefix = extended_launch_limit
            evaluated.extend(
                _evaluate_exact_candidates(
                    launch,
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
                    min_source_rank=current_prefix + 1,
                    max_source_rank=next_prefix,
                    existing_candidates=evaluated,
                    transfer_scan_time_limit=transfer_scan_time_limit,
                    transfer_retry_time_limit=transfer_retry_time_limit,
                )
            )
            previous_winner = _winner_through_rank(evaluated, current_prefix)
            comparison_left = current_prefix
            current_prefix = next_prefix
            comparison_right = current_prefix
            selected = _winner_through_rank(evaluated, current_prefix)
            max_generated_rank = max(
                (int(row.generation_rank) for row in launch.candidates),
                default=0,
            )
            complete = bool(launch.shortlist_complete and max_generated_rank <= current_prefix)
            stable = bool(
                complete
                or (
                    previous_winner is not None
                    and selected is not None
                    and previous_winner.squad_ids == selected.squad_ids
                )
            )
    except _TransferPlanInconclusive as exc:
        best_gw1 = float(launch.objective)
        floor = best_gw1 - tolerance
        return JointInitialPathResult(
            "inconclusive",
            None,
            None,
            tuple(sorted(evaluated, key=_candidate_key)),
            best_gw1,
            tolerance,
            floor,
            previous_winner.squad_ids if previous_winner else None,
            None,
            False,
            None,
            None,
            None,
            projection_col,
            f"Final launch transfer planning is inconclusive: {exc}",
        )

    best_gw1 = float(launch.objective)
    evaluated = _rebase_gw1_band(evaluated, best_gw1, tolerance)
    previous_winner = _winner_through_rank(evaluated, comparison_left)
    selected = _winner_through_rank(evaluated, comparison_right)
    floor = best_gw1 - tolerance
    if selected is None:
        return JointInitialPathResult(
            "infeasible", None, None, tuple(sorted(evaluated, key=_candidate_key)),
            best_gw1, tolerance, floor,
            previous_winner.squad_ids if previous_winner else None,
            None, False, None, None, None, projection_col,
            "No launch candidate survives the current-Gameweek expected-points floor.",
        )

    baseline_ids = tuple(sorted(static.solution.squad["player_id"].astype(int).tolist()))
    baseline_match = next(
        (candidate for candidate in evaluated if candidate.squad_ids == baseline_ids),
        None,
    )
    baseline_note = ""
    if baseline_match is not None:
        baseline = _candidate_with_source_rank(baseline_match, 0)
    else:
        try:
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
                best_future_objective=None,
                transfer_scan_time_limit=transfer_scan_time_limit,
                transfer_retry_time_limit=transfer_retry_time_limit,
            )
        except _TransferPlanInconclusive as exc:
            baseline = None
            baseline_note = f" Static comparison future path unavailable: {exc}."

    small_ids = previous_winner.squad_ids if previous_winner else None
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
        tuple(sorted(evaluated, key=_candidate_key)),
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
            "Current-Gameweek exact expected points are the primary launch objective. "
            "The governed submitted-bench resilience policy is enforced in both the "
            "candidate MILP and exhaustive mechanics. The existing near-equivalent "
            "point band is a hard floor; only then may the legal future transfer path "
            "choose between launch-equivalent squads. Candidate convergence is checked "
            f"between rank prefixes {comparison_left} and {comparison_right}; rank 64 "
            "is solved only after another identity change. Solver-limit candidates are "
            "pruned only by certified objective bounds against an in-band incumbent, "
            "otherwise the selector fails closed. Execute only the current decision "
            "and rebuild projections before every later deadline."
            f"{baseline_note}"
        ),
    )
