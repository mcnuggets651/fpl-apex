"""Immutable storage and replay-derived validation for receding-horizon decisions."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactIntegrityError, ArtifactStore
from apex_fpl.control.manager_state_store import load_manager_state
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import (
    CandidateUniverse,
    DecisionAction,
    DecisionChip,
    DecisionInput,
    DecisionMechanics,
    DecisionObjectiveModel,
    DecisionUseMode,
    RationalValue,
    TransferMove,
)
from apex_fpl.core.decision_policy_support import ChipOptionValuePolicy, ContinuationValuePolicy
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    CandidateUniverseId,
    DecisionPolicyId,
    ForecastId,
    ManagerStateId,
    PlanningResultId,
    PlanningStateId,
    RuleSetId,
)
from apex_fpl.core.manager_state import OwnedPlayer
from apex_fpl.core.planning import (
    PlanningChipUse,
    PlanningSolverCertificate,
    PlanningSolverStatus,
    PlanningState,
    PlanningStep,
    PlanningTrajectory,
    RecedingHorizonDecisionResult,
)
from apex_fpl.core.rules import RuleSet

from .planning_objective import terminal_chip_reserve
from .planning_state import apply_planning_action, planning_state_from_manager_state


@dataclass(frozen=True, slots=True)
class StoredPlanningResult:
    result: RecedingHorizonDecisionResult
    artifact_id: str


def _int(value: object, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be exact integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return value


def _bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _text(value: object, *, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be nonempty string")
    return value.strip()


def _objects(value: object, *, label: str) -> list[dict[str, object]]:
    if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
        raise ValueError(f"{label} must be an array of objects")
    return [dict(row) for row in value]


def _values(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be an array")
    return list(value)


def _rv(value: object, *, label: str = "rational") -> RationalValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    return RationalValue(
        _int(value.get("numerator"), label=f"{label} numerator"),
        _int(value.get("denominator"), label=f"{label} denominator", minimum=1),
    )


def _owned(raw: dict[str, object]) -> OwnedPlayer:
    return OwnedPlayer(
        player_id=OfficialPlayerId(_int(raw.get("player_id"), label="planning owned player_id", minimum=1)),
        team_id=_int(raw.get("team_id"), label="planning owned team_id", minimum=1),
        position=_text(raw.get("position"), label="planning owned position"),
        purchase_basis_tenths=_int(
            raw.get("purchase_basis_tenths"), label="planning owned purchase basis", minimum=1
        ),
        current_price_tenths=_int(
            raw.get("current_price_tenths"), label="planning owned current price", minimum=1
        ),
        selling_price_tenths=_int(
            raw.get("selling_price_tenths"), label="planning owned selling price", minimum=1
        ),
    )


def _planning_state(raw: dict[str, object]) -> PlanningState:
    parent_state = raw.get("parent_state_id")
    parent_action = raw.get("parent_action_id")
    return PlanningState(
        origin_manager_state_id=ManagerStateId(
            _text(raw.get("origin_manager_state_id"), label="planning origin manager state")
        ),
        price_world_id=__import__("apex_fpl.core.ids", fromlist=["GlobalWorldId"]).GlobalWorldId(
            _text(raw.get("price_world_id"), label="planning price world")
        ),
        season=_text(raw.get("season"), label="planning season"),
        entry_id=_int(raw.get("entry_id"), label="planning entry_id", minimum=1),
        gameweek=_int(raw.get("gameweek"), label="planning gameweek", minimum=1),
        ruleset_id=RuleSetId(_text(raw.get("ruleset_id"), label="planning ruleset_id")),
        bank_tenths=_int(raw.get("bank_tenths"), label="planning bank", minimum=0),
        free_transfers=_int(raw.get("free_transfers"), label="planning free transfers", minimum=0),
        squad=tuple(_owned(row) for row in _objects(raw.get("squad"), label="planning squad")),
        chips_used=tuple(
            PlanningChipUse(
                gameweek=_int(row.get("gameweek"), label="planning chip gameweek", minimum=1),
                chip=_text(row.get("chip"), label="planning chip"),
                set_number=_int(row.get("set_number"), label="planning chip set", minimum=1),
            )
            for row in _objects(raw.get("chips_used"), label="planning chips_used")
        ),
        parent_state_id=(
            None if parent_state is None else PlanningStateId(_text(parent_state, label="planning parent state"))
        ),
        parent_action_id=(
            None if parent_action is None else _text(parent_action, label="planning parent action")
        ),
        schema_version=_int(raw.get("schema_version"), label="planning state schema_version", minimum=1),
    )


def _decision_input(raw: object) -> DecisionInput:
    if not isinstance(raw, dict):
        raise ValueError("planning DecisionInput must be object")
    chips = _values(raw.get("chips_considered"), label="planning DecisionInput chips")
    if any(not isinstance(row, str) for row in chips):
        raise ValueError("planning DecisionInput chip names must be strings")
    return DecisionInput(
        manager_state_id=ManagerStateId(_text(raw.get("manager_state_id"), label="manager_state_id")),
        forecast_id=ForecastId(_text(raw.get("forecast_id"), label="forecast_id")),
        ruleset_id=RuleSetId(_text(raw.get("ruleset_id"), label="ruleset_id")),
        candidate_universe_id=CandidateUniverseId(
            _text(raw.get("candidate_universe_id"), label="candidate_universe_id")
        ),
        decision_policy_id=DecisionPolicyId(
            _text(raw.get("decision_policy_id"), label="decision_policy_id")
        ),
        gameweek=_int(raw.get("gameweek"), label="decision gameweek", minimum=1),
        use_mode=DecisionUseMode(_text(raw.get("use_mode"), label="decision use mode")),
        objective_model=DecisionObjectiveModel(
            _text(raw.get("objective_model"), label="decision objective model")
        ),
        max_normal_transfers=_int(
            raw.get("max_normal_transfers"), label="decision max normal transfers", minimum=0
        ),
        chips_considered=tuple(DecisionChip(row) for row in chips),
        numeric_policy_id=_text(raw.get("numeric_policy_id"), label="numeric_policy_id"),
    )


def _ids(value: object, *, label: str) -> tuple[OfficialPlayerId, ...]:
    return tuple(
        OfficialPlayerId(_int(row, label=f"{label} player_id", minimum=1))
        for row in _values(value, label=label)
    )


def _mechanics(raw: object) -> DecisionMechanics:
    if not isinstance(raw, dict):
        raise ValueError("planning action mechanics must be object")
    return DecisionMechanics(
        xi_points=_rv(raw.get("xi_points"), label="xi points"),
        autosub_points=_rv(raw.get("autosub_points"), label="autosub points"),
        captain_bonus=_rv(raw.get("captain_bonus"), label="captain bonus"),
        squad_points_if_bench_boost=_rv(
            raw.get("squad_points_if_bench_boost"), label="bench boost squad points"
        ),
        points_before_hits=_rv(raw.get("points_before_hits"), label="points before hits"),
        hit_points=_int(raw.get("hit_points"), label="hit points", minimum=0),
        objective_points=_rv(raw.get("objective_points"), label="objective points"),
    )


def _action(raw: object) -> DecisionAction:
    if not isinstance(raw, dict):
        raise ValueError("planning action must be object")
    return DecisionAction(
        chip=DecisionChip(_text(raw.get("chip"), label="action chip")),
        transfers=tuple(
            TransferMove(
                outgoing_player_id=OfficialPlayerId(
                    _int(row.get("outgoing_player_id"), label="outgoing player", minimum=1)
                ),
                incoming_player_id=OfficialPlayerId(
                    _int(row.get("incoming_player_id"), label="incoming player", minimum=1)
                ),
            )
            for row in _objects(raw.get("transfers"), label="action transfers")
        ),
        squad_ids=_ids(raw.get("squad_ids"), label="action squad_ids"),
        xi_ids=_ids(raw.get("xi_ids"), label="action xi_ids"),
        captain_id=OfficialPlayerId(_int(raw.get("captain_id"), label="captain_id", minimum=1)),
        vice_captain_id=OfficialPlayerId(
            _int(raw.get("vice_captain_id"), label="vice_captain_id", minimum=1)
        ),
        bench_gk_id=OfficialPlayerId(_int(raw.get("bench_gk_id"), label="bench_gk_id", minimum=1)),
        outfield_bench_order=_ids(
            raw.get("outfield_bench_order"), label="action outfield bench order"
        ),
        bank_after_tenths=_int(raw.get("bank_after_tenths"), label="action bank", minimum=0),
        mechanics=_mechanics(raw.get("mechanics")),
    )


def _step(raw: dict[str, object]) -> PlanningStep:
    return PlanningStep(
        gameweek=_int(raw.get("gameweek"), label="planning step gameweek", minimum=1),
        state_before_id=PlanningStateId(
            _text(raw.get("state_before_id"), label="planning state_before_id")
        ),
        action=_action(raw.get("action")),
        state_after_id=PlanningStateId(
            _text(raw.get("state_after_id"), label="planning state_after_id")
        ),
        gameweek_points=_rv(raw.get("gameweek_points"), label="planning gameweek points"),
        continuation_weight=_rv(
            raw.get("continuation_weight"), label="planning continuation weight"
        ),
        weighted_points=_rv(raw.get("weighted_points"), label="planning weighted points"),
    )


def _trajectory(raw: object) -> PlanningTrajectory:
    if not isinstance(raw, dict):
        raise ValueError("planning trajectory must be object")
    return PlanningTrajectory(
        steps=tuple(_step(row) for row in _objects(raw.get("steps"), label="planning steps")),
        terminal_chip_reserve=_rv(raw.get("terminal_chip_reserve"), label="terminal chip reserve"),
        selection_objective=_rv(raw.get("selection_objective"), label="selection objective"),
    )


def _solver(raw: object) -> PlanningSolverCertificate:
    if not isinstance(raw, dict):
        raise ValueError("planning solver certificate must be object")
    return PlanningSolverCertificate(
        status=PlanningSolverStatus(_text(raw.get("status"), label="planning solver status")),
        incumbent_objective=(
            None if raw.get("incumbent_objective") is None else _rv(raw.get("incumbent_objective"))
        ),
        best_bound=None if raw.get("best_bound") is None else _rv(raw.get("best_bound")),
        gap=None if raw.get("gap") is None else _rv(raw.get("gap")),
        search_complete=_bool(raw.get("search_complete"), label="planning search_complete"),
        expanded_nodes=_int(raw.get("expanded_nodes"), label="planning expanded_nodes", minimum=0),
        pruned_nodes=_int(raw.get("pruned_nodes"), label="planning pruned_nodes", minimum=0),
        message=_text(raw.get("message"), label="planning solver message"),
        schema_version=_int(raw.get("schema_version"), label="planning solver schema_version", minimum=1),
    )


def result_from_payload(raw: dict[str, object]) -> RecedingHorizonDecisionResult:
    return RecedingHorizonDecisionResult(
        decision_input=_decision_input(raw.get("decision_input")),
        initial_planning_state_id=PlanningStateId(
            _text(raw.get("initial_planning_state_id"), label="initial_planning_state_id")
        ),
        selected_trajectory=_trajectory(raw.get("selected_trajectory")),
        alternatives=tuple(
            _trajectory(row) for row in _objects(raw.get("alternatives"), label="planning alternatives")
        ),
        solver=_solver(raw.get("solver")),
        enumerated_root_actions=_int(
            raw.get("enumerated_root_actions"), label="enumerated_root_actions", minimum=1
        ),
        schema_version=_int(raw.get("schema_version"), label="planning result schema_version", minimum=1),
    )


def _store_planning_state(state: PlanningState, *, store: ArtifactStore) -> None:
    ref = store.put_bytes(
        canonical_json_bytes(state.semantic_payload()),
        media_type="application/json",
        schema_name="apex-planning-state",
        schema_version=str(state.schema_version),
    )
    if ref.artifact_id != str(state.planning_state_id):
        raise ValueError("PlanningState storage identity mismatch")


def load_planning_state(state_id: PlanningStateId | str, *, store: ArtifactStore) -> PlanningState:
    expected = PlanningStateId(str(state_id))
    try:
        content = store.read_bytes(str(expected))
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError("PlanningState artifact failed integrity verification") from exc
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("PlanningState artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_name") != "apex-planning-state":
        raise ValueError("not an Apex PlanningState artifact")
    if canonical_json_bytes(raw) != content:
        raise ValueError("PlanningState artifact is not canonical JSON")
    state = _planning_state(raw)
    if state.planning_state_id != expected:
        raise ValueError("PlanningState semantic identity mismatch")
    return state


def _replay_trajectory(
    trajectory: PlanningTrajectory,
    *,
    root: PlanningState,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
    store: ArtifactStore,
) -> None:
    state = root
    for index, step in enumerate(trajectory.steps):
        if step.state_before_id != state.planning_state_id:
            raise ValueError("planning trajectory state-before identity does not replay")
        retained_before = load_planning_state(step.state_before_id, store=store)
        if retained_before.semantic_payload() != state.semantic_payload():
            raise ValueError("retained planning state-before does not match replayed state")
        expected_weight = continuation.gameweek_weights[index]
        if step.continuation_weight != RationalValue(
            expected_weight.numerator, expected_weight.denominator
        ):
            raise ValueError("planning trajectory continuation weight differs from policy")
        next_state = apply_planning_action(state, step.action, universe, ruleset=ruleset)
        if next_state.planning_state_id != step.state_after_id:
            raise ValueError("planning trajectory state transition does not replay")
        retained_after = load_planning_state(step.state_after_id, store=store)
        if retained_after.semantic_payload() != next_state.semantic_payload():
            raise ValueError("retained planning state-after does not match replayed transition")
        state = next_state
    reserve = terminal_chip_reserve(state, chip_option, ruleset=ruleset)
    if reserve != trajectory.terminal_chip_reserve:
        raise ValueError("planning trajectory terminal chip reserve does not replay")


def _store_and_replay_trajectory(
    trajectory: PlanningTrajectory,
    *,
    root: PlanningState,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
    store: ArtifactStore,
) -> None:
    state = root
    _store_planning_state(state, store=store)
    for step in trajectory.steps:
        if step.state_before_id != state.planning_state_id:
            raise ValueError("planning trajectory does not start from replayed state")
        next_state = apply_planning_action(state, step.action, universe, ruleset=ruleset)
        if next_state.planning_state_id != step.state_after_id:
            raise ValueError("planning trajectory state transition does not derive")
        _store_planning_state(next_state, store=store)
        state = next_state
    _replay_trajectory(
        trajectory,
        root=root,
        universe=universe,
        ruleset=ruleset,
        continuation=continuation,
        chip_option=chip_option,
        store=store,
    )


def store_planning_result(
    result: RecedingHorizonDecisionResult,
    *,
    manager_state_id: ManagerStateId | str,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
    store: ArtifactStore,
) -> StoredPlanningResult:
    """Store only after every returned trajectory derives from retained current truth."""

    manager_state = load_manager_state(manager_state_id, store=store)
    if manager_state.manager_state_id != result.decision_input.manager_state_id:
        raise ValueError("planning result ManagerState identity mismatch")
    if universe.candidate_universe_id != result.decision_input.candidate_universe_id:
        raise ValueError("planning result CandidateUniverse identity mismatch")
    if ruleset.ruleset_id != result.decision_input.ruleset_id:
        raise ValueError("planning result RuleSet identity mismatch")
    root = planning_state_from_manager_state(manager_state, universe, ruleset=ruleset)
    if root.planning_state_id != result.initial_planning_state_id:
        raise ValueError("planning result root does not derive from retained ManagerState")
    for trajectory in (result.selected_trajectory, *result.alternatives):
        _store_and_replay_trajectory(
            trajectory,
            root=root,
            universe=universe,
            ruleset=ruleset,
            continuation=continuation,
            chip_option=chip_option,
            store=store,
        )
    ref = store.put_bytes(
        canonical_json_bytes(result.semantic_payload()),
        media_type="application/json",
        schema_name="apex-receding-horizon-decision-result",
        schema_version=str(result.schema_version),
    )
    if ref.artifact_id != str(result.planning_result_id):
        raise ValueError("planning result storage identity mismatch")
    return StoredPlanningResult(result=result, artifact_id=ref.artifact_id)


def load_planning_result(
    result_id: PlanningResultId | str,
    *,
    manager_state_id: ManagerStateId | str,
    universe: CandidateUniverse,
    ruleset: RuleSet,
    continuation: ContinuationValuePolicy,
    chip_option: ChipOptionValuePolicy,
    store: ArtifactStore,
) -> StoredPlanningResult:
    """Replay canonical result bytes and every retained hypothetical state transition."""

    expected = PlanningResultId(str(result_id))
    try:
        content = store.read_bytes(str(expected))
    except (FileNotFoundError, ArtifactIntegrityError) as exc:
        raise ValueError("planning result artifact failed integrity verification") from exc
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("planning result artifact is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict) or raw.get("schema_name") != "apex-receding-horizon-decision-result":
        raise ValueError("not an Apex receding-horizon decision result")
    if canonical_json_bytes(raw) != content:
        raise ValueError("planning result artifact is not canonical JSON")
    result = result_from_payload(raw)
    if result.planning_result_id != expected:
        raise ValueError("planning result semantic identity mismatch")
    manager_state = load_manager_state(manager_state_id, store=store)
    if manager_state.manager_state_id != result.decision_input.manager_state_id:
        raise ValueError("planning result retained ManagerState identity mismatch")
    root = planning_state_from_manager_state(manager_state, universe, ruleset=ruleset)
    if root.planning_state_id != result.initial_planning_state_id:
        raise ValueError("planning result root does not derive during replay")
    for trajectory in (result.selected_trajectory, *result.alternatives):
        _replay_trajectory(
            trajectory,
            root=root,
            universe=universe,
            ruleset=ruleset,
            continuation=continuation,
            chip_option=chip_option,
            store=store,
        )
    return StoredPlanningResult(result=result, artifact_id=str(expected))
