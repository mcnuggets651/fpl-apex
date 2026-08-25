"""Isolated receding-horizon reference solver for Apex V2.

This worker does not import the in-process planner, planning transitions, production action
surface, or planning objective helpers.  It reuses only the already-isolated tactical
reference worker's low-level FPL mechanics primitives, then independently reconstructs
hypothetical state transitions, free-transfer banking, chip persistence, terminal option
reserve, horizon objective, dominance and branch-and-bound search.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.reference_solver_io import ExactSolverValue
from apex_fpl.core.reference_solver_planning_io import (
    PlanningReferenceSolverRequest,
    PlanningReferenceSolverRun,
    PlanningReferenceSolverStatus,
)
from apex_fpl.workers.reference_solver import (
    _Budget,
    _Owned,
    _SearchLimit,
    _action_payload,
    _action_tie_key,
    _available_chips,
    _build_values,
    _full_rebuild_actions,
    _normal_actions,
    _optimise_submission,
    _parse_players,
    _rule_int,
    _rule_map,
    _rules,
    _validate_owned_matches,
)


_CHIPS = ("BENCH_BOOST", "FREE_HIT", "TRIPLE_CAPTAIN", "WILDCARD")
_ACTION_ORDER = ("NONE", "TRIPLE_CAPTAIN", "BENCH_BOOST", "WILDCARD", "FREE_HIT")


@dataclass(frozen=True, slots=True)
class _PlanOwned:
    player_id: int
    team_id: int
    position: str
    purchase_basis: int
    current_price: int
    selling_price: int

    def payload(self) -> dict[str, object]:
        return {
            "player_id": self.player_id,
            "team_id": self.team_id,
            "position": self.position,
            "purchase_basis_tenths": self.purchase_basis,
            "current_price_tenths": self.current_price,
            "selling_price_tenths": self.selling_price,
        }

    def tactical(self) -> _Owned:
        return _Owned(
            player_id=self.player_id,
            team_id=self.team_id,
            position=self.position,
            current_price=self.current_price,
            selling_price=self.selling_price,
        )


@dataclass(frozen=True, slots=True)
class _PlanState:
    origin_manager_state_id: str
    price_world_id: str
    season: str
    entry_id: int
    gameweek: int
    ruleset_id: str
    bank: int
    free_transfers: int
    squad: tuple[_PlanOwned, ...]
    chips_used: tuple[tuple[int, str, int], ...]
    parent_state_id: str | None = None
    parent_action_id: str | None = None

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-planning-state",
            "schema_version": 1,
            "origin_manager_state_id": self.origin_manager_state_id,
            "price_world_id": self.price_world_id,
            "season": self.season,
            "entry_id": self.entry_id,
            "gameweek": self.gameweek,
            "ruleset_id": self.ruleset_id,
            "bank_tenths": self.bank,
            "free_transfers": self.free_transfers,
            "squad": [row.payload() for row in self.squad],
            "chips_used": [
                {"gameweek": gameweek, "chip": chip, "set_number": set_number}
                for gameweek, chip, set_number in self.chips_used
            ],
            "parent_state_id": self.parent_state_id,
            "parent_action_id": self.parent_action_id,
        }

    @property
    def state_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    def tactical_state(self) -> dict[str, object]:
        return {
            "gameweek": self.gameweek,
            "bank_tenths": self.bank,
            "free_transfers": self.free_transfers,
            "chips_used": [
                {"gameweek": gameweek, "chip": chip, "set_number": set_number}
                for gameweek, chip, set_number in self.chips_used
            ],
        }


@dataclass(frozen=True, slots=True)
class _Trajectory:
    steps: tuple[dict[str, object], ...]
    terminal_reserve: Fraction
    objective: Fraction

    @property
    def payload(self) -> dict[str, object]:
        return {
            "steps": list(self.steps),
            "terminal_chip_reserve": _ratio(self.terminal_reserve),
            "selection_objective": _ratio(self.objective),
        }

    @property
    def trajectory_id(self) -> str:
        return canonical_sha256({"schema_name": "apex-planning-trajectory", **self.payload})

    @property
    def first_action(self) -> dict[str, object]:
        action = self.steps[0]["action"]
        if not isinstance(action, dict):  # pragma: no cover - constructed internally
            raise ValueError("trajectory first action is invalid")
        return action

    @property
    def first_action_id(self) -> str:
        return canonical_sha256({"schema_name": "apex-decision-action", **self.first_action})

    @property
    def tie_key(self) -> tuple[object, ...]:
        return tuple(_action_tie_key(_step_action(step)) for step in self.steps)


def _step_action(step: dict[str, object]) -> dict[str, object]:
    action = step.get("action")
    if not isinstance(action, dict):
        raise ValueError("planning reference step action must be object")
    return action


def _as_int(value: object, *, label: str, positive: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be integer")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")
    return value


def _fraction(value: object, *, label: str) -> Fraction:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be exact rational object")
    numerator = _as_int(value.get("numerator"), label=f"{label} numerator")
    denominator = _as_int(
        value.get("denominator"),
        label=f"{label} denominator",
        positive=True,
    )
    return Fraction(numerator, denominator)


def _ratio(value: Fraction) -> dict[str, int]:
    return {"numerator": value.numerator, "denominator": value.denominator}


def _exact(value: Fraction) -> ExactSolverValue:
    return ExactSolverValue(value.numerator, value.denominator)


def _root_state(request: PlanningReferenceSolverRequest, rules: dict[str, object]) -> _PlanState:
    manager = request.manager_state
    rows = manager.get("squad")
    if not isinstance(rows, list) or len(rows) != 15:
        raise ValueError("planning reference ManagerState requires 15 owned players")
    squad: list[_PlanOwned] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("planning reference owned player must be object")
        owned = _PlanOwned(
            player_id=_as_int(row.get("player_id"), label="owned player_id", positive=True),
            team_id=_as_int(row.get("team_id"), label="owned team_id", positive=True),
            position=str(row.get("position") or ""),
            purchase_basis=_as_int(
                row.get("purchase_basis_tenths"),
                label="owned purchase basis",
                positive=True,
            ),
            current_price=_as_int(
                row.get("current_price_tenths"),
                label="owned current price",
                positive=True,
            ),
            selling_price=_as_int(
                row.get("selling_price_tenths"),
                label="owned selling price",
                positive=True,
            ),
        )
        if owned.selling_price != _selling_price(
            owned.purchase_basis,
            owned.current_price,
            rules,
        ):
            raise ValueError("planning reference owned selling resource is stale")
        squad.append(owned)
    squad.sort(key=lambda row: row.player_id)
    if len({row.player_id for row in squad}) != 15:
        raise ValueError("planning reference ManagerState squad IDs must be unique")

    chips_raw = manager.get("chips_used")
    if not isinstance(chips_raw, list):
        raise ValueError("planning reference ManagerState chips_used must be list")
    chips: list[tuple[int, str, int]] = []
    for row in chips_raw:
        if not isinstance(row, dict):
            raise ValueError("planning reference chip ledger row must be object")
        chips.append(
            (
                _as_int(row.get("gameweek"), label="chip gameweek", positive=True),
                str(row.get("chip") or ""),
                _as_int(row.get("set_number"), label="chip set", positive=True),
            )
        )
    chips.sort()
    return _PlanState(
        origin_manager_state_id=canonical_sha256(manager),
        price_world_id=str(request.candidate_universe.get("global_world_id") or ""),
        season=str(manager.get("season") or ""),
        entry_id=_as_int(manager.get("entry_id"), label="manager entry_id", positive=True),
        gameweek=_as_int(manager.get("gameweek"), label="manager gameweek", positive=True),
        ruleset_id=canonical_sha256(request.ruleset),
        bank=_as_int(manager.get("bank_tenths"), label="manager bank"),
        free_transfers=_as_int(manager.get("free_transfers"), label="manager free transfers"),
        squad=tuple(squad),
        chips_used=tuple(chips),
    )


def _selling_price(purchase: int, current: int, rules: dict[str, object]) -> int:
    if current <= purchase:
        if rules.get("FPL-SELLING-PRICE-LOSS-PASSTHROUGH-001") is not True:
            raise ValueError("planning reference RuleSet lacks loss passthrough")
        return current
    step = _rule_map(rules, "FPL-SELLING-PRICE-PROFIT-STEP-001")
    rise = _as_int(step.get("purchase_price_rise_tenths"), label="selling rise", positive=True)
    profit = _as_int(step.get("selling_profit_tenths"), label="selling profit", positive=True)
    return purchase + ((current - purchase) // rise) * profit


def _chip_set(gameweek: int, rules: dict[str, object]) -> int:
    first_last = _rule_int(rules, "FPL-CHIP-FIRST-SET-LAST-GW-001")
    second_first = _rule_int(rules, "FPL-CHIP-SECOND-SET-FIRST-GW-001")
    if gameweek <= first_last:
        return 1
    if gameweek >= second_first:
        return 2
    raise ValueError("planning reference gameweek lies outside configured chip sets")


def _action_id(action: dict[str, object]) -> str:
    return canonical_sha256({"schema_name": "apex-decision-action", **action})


def _transfers(action: dict[str, object]) -> tuple[tuple[int, int], ...]:
    rows = action.get("transfers")
    if not isinstance(rows, list):
        raise ValueError("planning reference action transfers must be list")
    result: list[tuple[int, int]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("planning reference transfer row must be object")
        result.append(
            (
                _as_int(row.get("outgoing_player_id"), label="transfer outgoing", positive=True),
                _as_int(row.get("incoming_player_id"), label="transfer incoming", positive=True),
            )
        )
    return tuple(result)


def _mechanics_objective(action: dict[str, object]) -> Fraction:
    mechanics = action.get("mechanics")
    if not isinstance(mechanics, dict):
        raise ValueError("planning reference action mechanics must be object")
    return _fraction(mechanics.get("objective_points"), label="action objective")


def _mechanics_hit(action: dict[str, object]) -> int:
    mechanics = action.get("mechanics")
    if not isinstance(mechanics, dict):
        raise ValueError("planning reference action mechanics must be object")
    return _as_int(mechanics.get("hit_points"), label="action hit points")


def _next_state(
    state: _PlanState,
    action: dict[str, object],
    *,
    player_by_id: dict[int, object],
    rules: dict[str, object],
) -> _PlanState:
    current = {row.player_id: row for row in state.squad}
    squad_ids_raw = action.get("squad_ids")
    if not isinstance(squad_ids_raw, list):
        raise ValueError("planning reference action squad_ids must be list")
    squad_ids = tuple(_as_int(row, label="action squad player", positive=True) for row in squad_ids_raw)
    if len(squad_ids) != 15 or len(set(squad_ids)) != 15:
        raise ValueError("planning reference action squad must contain 15 unique players")
    current_ids = set(current)
    result_ids = set(squad_ids)
    outgoing_ids = current_ids - result_ids
    incoming_ids = result_ids - current_ids
    moves = _transfers(action)
    if (
        {outgoing for outgoing, _ in moves} != outgoing_ids
        or {incoming for _, incoming in moves} != incoming_ids
        or len(moves) != len(outgoing_ids)
    ):
        raise ValueError("planning reference transfer set does not reconcile squad delta")

    sale = sum(current[player_id].selling_price for player_id in outgoing_ids)
    incoming_cost = 0
    for player_id in incoming_ids:
        player = player_by_id.get(player_id)
        if player is None:
            raise ValueError("planning reference incoming player outside universe")
        incoming_cost += player.price  # type: ignore[attr-defined]
    temporary_bank = state.bank + sale - incoming_cost
    if temporary_bank < 0:
        raise ValueError("planning reference action is unaffordable")
    chip = str(action.get("chip") or "")
    expected_bank = state.bank if chip == "FREE_HIT" else temporary_bank
    if action.get("bank_after_tenths") != expected_bank:
        raise ValueError("planning reference action bank does not reconcile")

    hit_cost = _rule_int(rules, "FPL-EXTRA-TRANSFER-HIT-POINTS-001")
    expected_hit = 0 if chip in {"WILDCARD", "FREE_HIT"} else max(
        0,
        len(moves) - state.free_transfers,
    ) * hit_cost
    if _mechanics_hit(action) != expected_hit:
        raise ValueError("planning reference action hit cost does not reconcile")

    chips = list(state.chips_used)
    if chip != "NONE":
        set_number = _chip_set(state.gameweek, rules)
        if (chip, set_number) in {(name, number) for _, name, number in chips}:
            raise ValueError("planning reference chip already used in current set")
        chips.append((state.gameweek, chip, set_number))
        chips.sort()

    if chip == "FREE_HIT":
        permanent = state.squad
        next_bank = state.bank
    else:
        permanent_rows: list[_PlanOwned] = []
        for player_id in sorted(squad_ids):
            retained = current.get(player_id)
            if retained is not None:
                permanent_rows.append(
                    _PlanOwned(
                        player_id=retained.player_id,
                        team_id=retained.team_id,
                        position=retained.position,
                        purchase_basis=retained.purchase_basis,
                        current_price=retained.current_price,
                        selling_price=_selling_price(
                            retained.purchase_basis,
                            retained.current_price,
                            rules,
                        ),
                    )
                )
                continue
            player = player_by_id[player_id]
            permanent_rows.append(
                _PlanOwned(
                    player_id=player.player_id,  # type: ignore[attr-defined]
                    team_id=player.team_id,  # type: ignore[attr-defined]
                    position=player.position,  # type: ignore[attr-defined]
                    purchase_basis=player.price,  # type: ignore[attr-defined]
                    current_price=player.price,  # type: ignore[attr-defined]
                    selling_price=player.price,  # type: ignore[attr-defined]
                )
            )
        permanent = tuple(permanent_rows)
        next_bank = expected_bank

    if chip == "WILDCARD" and rules.get("FPL-WILDCARD-PRESERVES-BANKED-TRANSFERS-001") is True:
        next_ft = state.free_transfers
    elif chip == "FREE_HIT" and rules.get("FPL-FREE-HIT-PRESERVES-BANKED-TRANSFERS-001") is True:
        next_ft = state.free_transfers
    else:
        next_ft = min(
            _rule_int(rules, "FPL-FREE-TRANSFER-BANK-MAX-001"),
            max(0, state.free_transfers - len(moves))
            + _rule_int(rules, "FPL-FREE-TRANSFER-GRANT-001"),
        )

    return _PlanState(
        origin_manager_state_id=state.origin_manager_state_id,
        price_world_id=state.price_world_id,
        season=state.season,
        entry_id=state.entry_id,
        gameweek=state.gameweek + 1,
        ruleset_id=state.ruleset_id,
        bank=next_bank,
        free_transfers=next_ft,
        squad=permanent,
        chips_used=tuple(chips),
        parent_state_id=state.state_id,
        parent_action_id=_action_id(action),
    )


def _continuation_weights(request: PlanningReferenceSolverRequest) -> tuple[Fraction, ...]:
    rows = request.continuation_policy.get("gameweek_weights")
    if not isinstance(rows, list) or len(rows) != request.horizon_gameweeks:
        raise ValueError("planning reference continuation weights do not cover horizon")
    return tuple(_fraction(row, label="continuation weight") for row in rows)


def _chip_values(request: PlanningReferenceSolverRequest) -> dict[str, Fraction]:
    rows = request.chip_option_policy.get("option_values")
    if not isinstance(rows, list):
        raise ValueError("planning reference chip option values must be list")
    values: dict[str, Fraction] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("planning reference chip option row must be object")
        chip = str(row.get("chip") or "")
        if chip in values:
            raise ValueError("planning reference chip option contains duplicate chip")
        values[chip] = _fraction(row.get("value"), label=f"chip option {chip}")
    if set(values) != set(_CHIPS):
        raise ValueError("planning reference chip options must value all four chips")
    return values


def _terminal_reserve(
    state: _PlanState,
    *,
    chip_values: dict[str, Fraction],
    rules: dict[str, object],
) -> Fraction:
    first_last = _rule_int(rules, "FPL-CHIP-FIRST-SET-LAST-GW-001")
    second_first = _rule_int(rules, "FPL-CHIP-SECOND-SET-FIRST-GW-001")
    if second_first != first_last + 1:
        raise ValueError("planning reference chip-set boundary must be contiguous")
    eligible = (1, 2) if state.gameweek <= first_last else (2,)
    used = {(chip, set_number) for _, chip, set_number in state.chips_used}
    return sum(
        (
            chip_values[chip]
            for set_number in eligible
            for chip in _CHIPS
            if (chip, set_number) not in used
        ),
        Fraction(0, 1),
    )


def _make_step(
    state: _PlanState,
    action: dict[str, object],
    next_state: _PlanState,
    weight: Fraction,
) -> dict[str, object]:
    points = _mechanics_objective(action)
    return {
        "gameweek": state.gameweek,
        "state_before_id": state.state_id,
        "action": action,
        "state_after_id": next_state.state_id,
        "gameweek_points": _ratio(points),
        "continuation_weight": _ratio(weight),
        "weighted_points": _ratio(points * weight),
    }


def _trajectory_better(left: _Trajectory, right: _Trajectory) -> bool:
    if left.objective != right.objective:
        return left.objective > right.objective
    return left.tie_key > right.tie_key


def _economic_key(state: _PlanState) -> tuple[object, ...]:
    return (
        state.gameweek,
        state.bank,
        state.free_transfers,
        tuple(
            (
                row.player_id,
                row.team_id,
                row.position,
                row.purchase_basis,
                row.current_price,
                row.selling_price,
            )
            for row in state.squad
        ),
        state.chips_used,
    )


def _global_gw_bound(
    request: PlanningReferenceSolverRequest,
    *,
    gameweek: int,
    players,
) -> Fraction:
    values = _build_values(
        request.forecast,
        gameweek=gameweek,
        player_ids=(row.player_id for row in players),
    )
    positive = sorted(
        (max(Fraction(0, 1), row.expected_points) for row in values.values()),
        reverse=True,
    )
    return sum(positive[:15], Fraction(0, 1)) + (
        (positive[0] if positive else Fraction(0, 1)) * 2
    )


def _remaining_bound(
    *,
    depth: int,
    prefix: Fraction,
    gw_bounds: tuple[Fraction, ...],
    weights: tuple[Fraction, ...],
    max_terminal_reserve: Fraction,
) -> Fraction:
    return prefix + sum(
        (gw_bounds[index] * weights[index] for index in range(depth, len(gw_bounds))),
        Fraction(0, 1),
    ) + max_terminal_reserve


def _actions(
    state: _PlanState,
    *,
    request: PlanningReferenceSolverRequest,
    players,
    rules: dict[str, object],
    budget: _Budget,
):
    tactical_state = state.tactical_state()
    owned = tuple(row.tactical() for row in state.squad)
    _validate_owned_matches(owned, players)
    values = _build_values(
        request.forecast,
        gameweek=state.gameweek,
        player_ids=(row.player_id for row in players),
    )
    available = _available_chips(tactical_state, rules)
    for chip in _ACTION_ORDER:
        if chip not in available:
            continue
        if chip in {"WILDCARD", "FREE_HIT"}:
            squad_actions = _full_rebuild_actions(
                state=tactical_state,
                owned=owned,
                players=players,
                chip=chip,
                rules=rules,
                budget=budget,
            )
        else:
            squad_actions = _normal_actions(
                state=tactical_state,
                owned=owned,
                players=players,
                chip=chip,
                max_transfers=15,
                rules=rules,
                budget=budget,
            )
        for squad_action in squad_actions:
            submission = _optimise_submission(
                squad_action.squad,
                {row.player_id: values[row.player_id] for row in squad_action.squad},
                chip=chip,
                hit_points=squad_action.hit_points,
                rules=rules,
            )
            yield _action_payload(squad_action, submission)


def _seed(
    root: _PlanState,
    *,
    request: PlanningReferenceSolverRequest,
    players,
    player_by_id,
    rules: dict[str, object],
    weights: tuple[Fraction, ...],
    chip_values: dict[str, Fraction],
) -> _Trajectory:
    state = root
    steps: list[dict[str, object]] = []
    total = Fraction(0, 1)
    for depth in range(request.horizon_gameweeks):
        local_budget = _Budget(max(1, request.max_search_nodes))
        tactical_state = state.tactical_state()
        owned = tuple(row.tactical() for row in state.squad)
        values = _build_values(
            request.forecast,
            gameweek=state.gameweek,
            player_ids=(row.player_id for row in players),
        )
        actions = _normal_actions(
            state=tactical_state,
            owned=owned,
            players=players,
            chip="NONE",
            max_transfers=0,
            rules=rules,
            budget=local_budget,
        )
        try:
            squad_action = next(actions)
        except StopIteration as exc:
            raise ValueError("planning reference seed has no legal no-transfer action") from exc
        submission = _optimise_submission(
            squad_action.squad,
            {row.player_id: values[row.player_id] for row in squad_action.squad},
            chip="NONE",
            hit_points=0,
            rules=rules,
        )
        action = _action_payload(squad_action, submission)
        next_state = _next_state(state, action, player_by_id=player_by_id, rules=rules)
        step = _make_step(state, action, next_state, weights[depth])
        steps.append(step)
        total += _mechanics_objective(action) * weights[depth]
        state = next_state
    reserve = _terminal_reserve(state, chip_values=chip_values, rules=rules)
    return _Trajectory(tuple(steps), reserve, total + reserve)


def solve_planning_reference_request(
    request: PlanningReferenceSolverRequest,
) -> PlanningReferenceSolverRun:
    """Independently solve the sealed receding-horizon objective or fail closed at limit."""

    budget = _Budget(request.max_search_nodes)
    pruned = 0
    limit_hit = False
    unresolved_upper: Fraction | None = None
    incumbent: _Trajectory | None = None

    try:
        rules = _rules(request.ruleset)
        players = _parse_players(request.candidate_universe)
        player_by_id = {row.player_id: row for row in players}
        root = _root_state(request, rules)
        _validate_owned_matches(tuple(row.tactical() for row in root.squad), players)
        weights = _continuation_weights(request)
        chip_values = _chip_values(request)
        gw_bounds = tuple(
            _global_gw_bound(
                request,
                gameweek=root.gameweek + depth,
                players=players,
            )
            for depth in range(request.horizon_gameweeks)
        )
        max_terminal_reserve = sum(chip_values.values(), Fraction(0, 1)) * 2
        incumbent = _seed(
            root,
            request=request,
            players=players,
            player_by_id=player_by_id,
            rules=rules,
            weights=weights,
            chip_values=chip_values,
        )
        dominance: dict[tuple[int, tuple[object, ...]], Fraction] = {}

        def search(
            state: _PlanState,
            *,
            depth: int,
            steps: tuple[dict[str, object], ...],
            prefix: Fraction,
        ) -> None:
            nonlocal incumbent, pruned, limit_hit, unresolved_upper
            node_upper = _remaining_bound(
                depth=depth,
                prefix=prefix,
                gw_bounds=gw_bounds,
                weights=weights,
                max_terminal_reserve=max_terminal_reserve,
            )
            if limit_hit:
                unresolved_upper = (
                    node_upper if unresolved_upper is None else max(unresolved_upper, node_upper)
                )
                return
            if incumbent is not None and node_upper < incumbent.objective:
                pruned += 1
                return
            if depth == request.horizon_gameweeks:
                reserve = _terminal_reserve(state, chip_values=chip_values, rules=rules)
                candidate = _Trajectory(steps, reserve, prefix + reserve)
                if incumbent is None or _trajectory_better(candidate, incumbent):
                    incumbent = candidate
                return

            key = (depth, _economic_key(state))
            previous = dominance.get(key)
            if previous is not None and previous > prefix:
                pruned += 1
                return
            if previous is None or prefix > previous:
                dominance[key] = prefix

            generated = False
            try:
                actions = _actions(
                    state,
                    request=request,
                    players=players,
                    rules=rules,
                    budget=budget,
                )
                for action in actions:
                    generated = True
                    next_state = _next_state(
                        state,
                        action,
                        player_by_id=player_by_id,
                        rules=rules,
                    )
                    step = _make_step(state, action, next_state, weights[depth])
                    search(
                        next_state,
                        depth=depth + 1,
                        steps=(*steps, step),
                        prefix=prefix + _mechanics_objective(action) * weights[depth],
                    )
                    if limit_hit:
                        unresolved_upper = (
                            node_upper
                            if unresolved_upper is None
                            else max(unresolved_upper, node_upper)
                        )
                        return
            except _SearchLimit:
                limit_hit = True
                unresolved_upper = (
                    node_upper if unresolved_upper is None else max(unresolved_upper, node_upper)
                )
                return
            if not generated:
                raise ValueError(f"planning reference found no legal actions in GW{state.gameweek}")

        search(root, depth=0, steps=(), prefix=Fraction(0, 1))
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
        return PlanningReferenceSolverRun(
            request_id=request.request_id,
            solver_status=PlanningReferenceSolverStatus.ERROR,
            best_objective=None,
            best_bound=None,
            gap=None,
            selected_action_id=None,
            selected_trajectory_id=None,
            selected_trajectory_json=None,
            search_complete=False,
            nodes_evaluated=budget.nodes,
            pruned_nodes=pruned,
            limit_reason=f"{type(exc).__name__}: {exc}",
        )

    if incumbent is None:  # pragma: no cover - legal no-transfer seed normally guarantees one
        return PlanningReferenceSolverRun(
            request_id=request.request_id,
            solver_status=PlanningReferenceSolverStatus.INFEASIBLE,
            best_objective=None,
            best_bound=None,
            gap=None,
            selected_action_id=None,
            selected_trajectory_id=None,
            selected_trajectory_json=None,
            search_complete=True,
            nodes_evaluated=budget.nodes,
            pruned_nodes=pruned,
        )

    if limit_hit:
        bound = max(incumbent.objective, unresolved_upper or incumbent.objective)
        status = PlanningReferenceSolverStatus.SOLVER_LIMIT
        complete = False
        reason = f"planning reference search-node limit {request.max_search_nodes} exceeded"
    else:
        bound = incumbent.objective
        status = PlanningReferenceSolverStatus.OPTIMAL
        complete = True
        reason = None
    trajectory_json = canonical_json_bytes(incumbent.payload).decode("utf-8")
    return PlanningReferenceSolverRun(
        request_id=request.request_id,
        solver_status=status,
        best_objective=_exact(incumbent.objective),
        best_bound=_exact(bound),
        gap=_exact(bound - incumbent.objective),
        selected_action_id=incumbent.first_action_id,
        selected_trajectory_id=incumbent.trajectory_id,
        selected_trajectory_json=trajectory_json,
        search_complete=complete,
        nodes_evaluated=budget.nodes,
        pruned_nodes=pruned,
        limit_reason=reason,
    )
