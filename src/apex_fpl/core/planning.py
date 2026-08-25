"""Dependency-free receding-horizon planning contracts for Apex V2.

A planning state is deliberately not a ``ManagerState``.  ``ManagerState`` represents
current/replayed FPL truth and only ``CURRENT_EXACT`` may authorize a live action.  A
``PlanningState`` is a content-addressed hypothetical state used to compare future action
sequences under one sealed price/forecast surface.  It can therefore never be passed off
as current manager truth.

Likewise, a receding-horizon result keeps the selected current ``DecisionAction`` and its
exact FPL mechanics separate from the multi-Gameweek selection objective.  A plan may
rationally sacrifice current-Gameweek points for higher governed continuation value, so
it must not be laundered through the tactical ``DecisionResult`` invariant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .canonical import canonical_sha256
from .decision import DecisionAction, DecisionInput, RationalValue
from .ids import (
    DecisionId,
    GlobalWorldId,
    ManagerStateId,
    PlanningResultId,
    PlanningStateId,
    RuleSetId,
)
from .manager_state import OwnedPlayer


_CHIPS = frozenset({"WILDCARD", "FREE_HIT", "TRIPLE_CAPTAIN", "BENCH_BOOST"})


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be a nonnegative integer")
    return value


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _rv_add(left: RationalValue, right: RationalValue) -> RationalValue:
    return RationalValue(
        left.numerator * right.denominator + right.numerator * left.denominator,
        left.denominator * right.denominator,
    )


def _rv_subtract(left: RationalValue, right: RationalValue) -> RationalValue:
    return RationalValue(
        left.numerator * right.denominator - right.numerator * left.denominator,
        left.denominator * right.denominator,
    )


def _rv_multiply(left: RationalValue, right: RationalValue) -> RationalValue:
    return RationalValue(
        left.numerator * right.numerator,
        left.denominator * right.denominator,
    )


def _rv_compare(left: RationalValue, right: RationalValue) -> int:
    value = (
        left.numerator * right.denominator
        - right.numerator * left.denominator
    )
    return (value > 0) - (value < 0)


@dataclass(frozen=True, slots=True, order=True)
class PlanningChipUse:
    """Set-specific chip use inside a hypothetical planning path."""

    gameweek: int
    chip: str
    set_number: int

    def __post_init__(self) -> None:
        _positive_int(self.gameweek, label="planning chip gameweek")
        chip = str(self.chip).strip().upper()
        if chip not in _CHIPS:
            raise ValueError(f"unknown planning chip: {self.chip!r}")
        if self.set_number not in {1, 2}:
            raise ValueError("planning chip set_number must be 1 or 2")
        object.__setattr__(self, "chip", chip)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "gameweek": self.gameweek,
            "chip": self.chip,
            "set_number": self.set_number,
        }


@dataclass(frozen=True, slots=True)
class PlanningState:
    """Exact hypothetical state under one immutable Official-current price surface."""

    origin_manager_state_id: ManagerStateId
    price_world_id: GlobalWorldId
    season: str
    entry_id: int
    gameweek: int
    ruleset_id: RuleSetId
    bank_tenths: int
    free_transfers: int
    squad: tuple[OwnedPlayer, ...]
    chips_used: tuple[PlanningChipUse, ...]
    parent_state_id: PlanningStateId | None = None
    parent_action_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported PlanningState schema_version")
        season = str(self.season).strip()
        if not season:
            raise ValueError("PlanningState season cannot be empty")
        _positive_int(self.entry_id, label="PlanningState entry_id")
        _positive_int(self.gameweek, label="PlanningState gameweek")
        _nonnegative_int(self.bank_tenths, label="PlanningState bank_tenths")
        _nonnegative_int(self.free_transfers, label="PlanningState free_transfers")
        if any(not isinstance(row, OwnedPlayer) for row in self.squad):
            raise ValueError("PlanningState squad must contain OwnedPlayer values")
        squad = tuple(sorted(self.squad, key=lambda row: int(row.player_id)))
        player_ids = [row.player_id for row in squad]
        if len(squad) != 15 or len(player_ids) != len(set(player_ids)):
            raise ValueError("PlanningState requires exactly 15 unique owned players")
        chips = tuple(sorted(self.chips_used))
        if len({row.gameweek for row in chips}) != len(chips):
            raise ValueError("PlanningState cannot use multiple chips in one gameweek")
        if len({(row.chip, row.set_number) for row in chips}) != len(chips):
            raise ValueError("PlanningState cannot use the same chip twice in one set")
        paired = (self.parent_state_id is None, self.parent_action_id is None)
        if paired[0] != paired[1]:
            raise ValueError("PlanningState parent state/action lineage must be paired")
        parent_action = self.parent_action_id
        if parent_action is not None:
            parent_action = str(parent_action).strip()
            if not parent_action:
                raise ValueError("PlanningState parent_action_id cannot be blank")
        object.__setattr__(self, "season", season)
        object.__setattr__(self, "squad", squad)
        object.__setattr__(self, "chips_used", chips)
        object.__setattr__(self, "parent_action_id", parent_action)

    @property
    def player_ids(self):
        return tuple(row.player_id for row in self.squad)

    def player(self, player_id):
        for row in self.squad:
            if row.player_id == player_id:
                return row
        raise ValueError(f"player {player_id} is not owned in PlanningState")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-planning-state",
            "schema_version": self.schema_version,
            "origin_manager_state_id": str(self.origin_manager_state_id),
            "price_world_id": str(self.price_world_id),
            "season": self.season,
            "entry_id": self.entry_id,
            "gameweek": self.gameweek,
            "ruleset_id": str(self.ruleset_id),
            "bank_tenths": self.bank_tenths,
            "free_transfers": self.free_transfers,
            "squad": [row.as_dict() for row in self.squad],
            "chips_used": [row.semantic_payload() for row in self.chips_used],
            "parent_state_id": (
                None if self.parent_state_id is None else str(self.parent_state_id)
            ),
            "parent_action_id": self.parent_action_id,
        }

    @property
    def planning_state_id(self) -> PlanningStateId:
        return PlanningStateId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True)
class PlanningStep:
    gameweek: int
    state_before_id: PlanningStateId
    action: DecisionAction
    state_after_id: PlanningStateId
    gameweek_points: RationalValue
    continuation_weight: RationalValue
    weighted_points: RationalValue

    def __post_init__(self) -> None:
        _positive_int(self.gameweek, label="planning step gameweek")
        if self.gameweek_points != self.action.mechanics.objective_points:
            raise ValueError("planning step points must equal exact DecisionAction mechanics")
        if self.continuation_weight.numerator < 0:
            raise ValueError("planning continuation weight cannot be negative")
        expected = _rv_multiply(self.gameweek_points, self.continuation_weight)
        if self.weighted_points != expected:
            raise ValueError("planning weighted points do not reconcile")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "gameweek": self.gameweek,
            "state_before_id": str(self.state_before_id),
            "action": self.action.semantic_payload(),
            "state_after_id": str(self.state_after_id),
            "gameweek_points": self.gameweek_points.semantic_payload(),
            "continuation_weight": self.continuation_weight.semantic_payload(),
            "weighted_points": self.weighted_points.semantic_payload(),
        }


@dataclass(frozen=True, slots=True)
class PlanningTrajectory:
    steps: tuple[PlanningStep, ...]
    terminal_chip_reserve: RationalValue
    selection_objective: RationalValue

    def __post_init__(self) -> None:
        if not self.steps:
            raise ValueError("PlanningTrajectory requires at least one step")
        steps = tuple(self.steps)
        expected_gws = tuple(range(steps[0].gameweek, steps[0].gameweek + len(steps)))
        if tuple(step.gameweek for step in steps) != expected_gws:
            raise ValueError("PlanningTrajectory gameweeks must be contiguous")
        for left, right in zip(steps, steps[1:], strict=False):
            if left.state_after_id != right.state_before_id:
                raise ValueError("PlanningTrajectory state lineage is not contiguous")
        if self.terminal_chip_reserve.numerator < 0:
            raise ValueError("terminal chip reserve cannot be negative")
        expected = self.terminal_chip_reserve
        for step in steps:
            expected = _rv_add(expected, step.weighted_points)
        if expected != self.selection_objective:
            raise ValueError("PlanningTrajectory selection objective does not reconcile")
        object.__setattr__(self, "steps", steps)

    @property
    def first_action(self) -> DecisionAction:
        return self.steps[0].action

    @property
    def first_state_id(self) -> PlanningStateId:
        return self.steps[0].state_before_id

    @property
    def terminal_state_id(self) -> PlanningStateId:
        return self.steps[-1].state_after_id

    def semantic_payload(self) -> dict[str, object]:
        return {
            "steps": [step.semantic_payload() for step in self.steps],
            "terminal_chip_reserve": self.terminal_chip_reserve.semantic_payload(),
            "selection_objective": self.selection_objective.semantic_payload(),
        }

    @property
    def trajectory_id(self) -> str:
        return canonical_sha256(
            {"schema_name": "apex-planning-trajectory", **self.semantic_payload()}
        )


class PlanningSolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    SOLVER_LIMIT = "SOLVER_LIMIT"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class PlanningSolverCertificate:
    status: PlanningSolverStatus
    incumbent_objective: RationalValue | None
    best_bound: RationalValue | None
    gap: RationalValue | None
    search_complete: bool
    expanded_nodes: int
    pruned_nodes: int
    message: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported PlanningSolverCertificate schema_version")
        if not isinstance(self.status, PlanningSolverStatus):
            raise ValueError("planning solver status must be typed")
        if not isinstance(self.search_complete, bool):
            raise ValueError("planning solver search_complete must be boolean")
        _nonnegative_int(self.expanded_nodes, label="planning expanded_nodes")
        _nonnegative_int(self.pruned_nodes, label="planning pruned_nodes")
        message = str(self.message).strip()
        if not message:
            raise ValueError("planning solver certificate requires message")
        if self.gap is not None:
            if self.incumbent_objective is None or self.best_bound is None:
                raise ValueError("planning solver gap requires incumbent and bound")
            expected = _rv_subtract(self.best_bound, self.incumbent_objective)
            if expected != self.gap or self.gap.numerator < 0:
                raise ValueError("planning solver gap does not reconcile bound/incumbent")
        if self.status is PlanningSolverStatus.OPTIMAL:
            if (
                not self.search_complete
                or self.incumbent_objective is None
                or self.best_bound is None
                or self.gap is None
                or self.gap.numerator != 0
            ):
                raise ValueError("OPTIMAL planning certificate requires complete zero-gap proof")
        if self.status in {PlanningSolverStatus.ERROR, PlanningSolverStatus.INCONCLUSIVE}:
            if self.search_complete:
                raise ValueError(f"{self.status.value} planning result cannot claim complete search")
        object.__setattr__(self, "message", message)

    def semantic_payload(self) -> dict[str, object]:
        def rv(value: RationalValue | None):
            return None if value is None else value.semantic_payload()

        return {
            "schema_name": "apex-planning-solver-certificate",
            "schema_version": self.schema_version,
            "status": self.status.value,
            "incumbent_objective": rv(self.incumbent_objective),
            "best_bound": rv(self.best_bound),
            "gap": rv(self.gap),
            "search_complete": self.search_complete,
            "expanded_nodes": self.expanded_nodes,
            "pruned_nodes": self.pruned_nodes,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class RecedingHorizonDecisionResult:
    """Multi-GW policy selection with one immediately executable current action."""

    decision_input: DecisionInput
    initial_planning_state_id: PlanningStateId
    selected_trajectory: PlanningTrajectory
    alternatives: tuple[PlanningTrajectory, ...]
    solver: PlanningSolverCertificate
    enumerated_root_actions: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported RecedingHorizonDecisionResult schema_version")
        _positive_int(self.enumerated_root_actions, label="enumerated_root_actions")
        if self.selected_trajectory.first_state_id != self.initial_planning_state_id:
            raise ValueError("selected trajectory does not start at initial planning state")
        alternatives = tuple(self.alternatives)
        if self.enumerated_root_actions < 1 + len(alternatives):
            raise ValueError("root action count cannot be smaller than returned trajectories")
        all_rows = (self.selected_trajectory, *alternatives)
        first_action_ids = [row.first_action.action_id for row in all_rows]
        if len(first_action_ids) != len(set(first_action_ids)):
            raise ValueError("planning result contains duplicate root actions")
        if any(
            _rv_compare(row.selection_objective, self.selected_trajectory.selection_objective) > 0
            for row in alternatives
        ):
            raise ValueError("planning alternative cannot outrank selected policy objective")
        if (
            self.solver.incumbent_objective is not None
            and self.solver.incumbent_objective
            != self.selected_trajectory.selection_objective
        ):
            raise ValueError("planning solver incumbent does not match selected trajectory")
        object.__setattr__(self, "alternatives", alternatives)

    @property
    def selected_action(self) -> DecisionAction:
        return self.selected_trajectory.first_action

    @property
    def selection_objective(self) -> RationalValue:
        return self.selected_trajectory.selection_objective

    def selection_objective_for_action(self, action_id: str) -> RationalValue:
        for row in (self.selected_trajectory, *self.alternatives):
            if row.first_action.action_id == action_id:
                return row.selection_objective
        raise ValueError(f"action {action_id} is not a returned planning root")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-receding-horizon-decision-result",
            "schema_version": self.schema_version,
            "decision_input": self.decision_input.semantic_payload(),
            "initial_planning_state_id": str(self.initial_planning_state_id),
            "selected_trajectory": self.selected_trajectory.semantic_payload(),
            "alternatives": [row.semantic_payload() for row in self.alternatives],
            "solver": self.solver.semantic_payload(),
            "enumerated_root_actions": self.enumerated_root_actions,
        }

    @property
    def planning_result_id(self) -> PlanningResultId:
        return PlanningResultId(canonical_sha256(self.semantic_payload()))

    @property
    def decision_id(self) -> DecisionId:
        return DecisionId(str(self.planning_result_id))
