"""Dependency-free sealed I/O for the isolated receding-horizon reference solver.

The tactical v1 reference-solver contract is frozen.  This module introduces a distinct
planning contract whose request commits to the exact current truth, forecast, full
Official universe, RuleSet, receding DecisionPolicy and every support policy that defines
the multi-Gameweek objective.  It is deliberately data-only so an isolated worker can
replay the objective without importing the in-process planner.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json

from .canonical import canonical_json_bytes, canonical_sha256
from .numeric_policy import DECISION_NUMERIC_POLICY_ID
from .reference_solver_io import ExactSolverValue


REFERENCE_SOLVER_PLANNING_CONTRACT = "apex-v2-exact-receding-horizon-parity-v2"
_ALL_CHIPS = {
    "NONE",
    "TRIPLE_CAPTAIN",
    "BENCH_BOOST",
    "WILDCARD",
    "FREE_HIT",
}


def _nonempty(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


def _nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be nonnegative integer")
    return value


def _canonical_document(value: dict[str, object], *, schema_name: str, label: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object")
    if value.get("schema_name") != schema_name:
        raise ValueError(f"{label} schema_name must be {schema_name!r}")
    return canonical_json_bytes(value).decode("utf-8")


def _load_document(value: str, *, schema_name: str, label: str) -> dict[str, object]:
    text = _nonempty(value, label=label)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must decode to object")
    canonical = _canonical_document(payload, schema_name=schema_name, label=label)
    if canonical != text:
        raise ValueError(f"{label} is not canonical semantic JSON")
    return payload


def _ratio(value: object, *, label: str) -> ExactSolverValue:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be exact rational object")
    return ExactSolverValue(
        numerator=value.get("numerator"),  # type: ignore[arg-type]
        denominator=value.get("denominator"),  # type: ignore[arg-type]
    )


class PlanningReferenceSolverStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    SOLVER_LIMIT = "SOLVER_LIMIT"
    INFEASIBLE = "INFEASIBLE"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class PlanningReferenceSolverRequest:
    decision_input_json: str
    manager_state_json: str
    forecast_json: str
    candidate_universe_json: str
    ruleset_json: str
    decision_policy_json: str
    continuation_policy_json: str
    chip_option_policy_json: str
    price_policy_json: str
    candidate_policy_json: str
    max_search_nodes: int
    solver_contract: str = REFERENCE_SOLVER_PLANNING_CONTRACT
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported planning reference solver request schema_version")
        contract = _nonempty(self.solver_contract, label="planning reference solver contract")
        if contract != REFERENCE_SOLVER_PLANNING_CONTRACT:
            raise ValueError("unsupported planning reference solver contract")
        _positive_int(self.max_search_nodes, label="planning reference max_search_nodes")

        decision_input = self.decision_input
        manager_state = self.manager_state
        forecast = self.forecast
        universe = self.candidate_universe
        ruleset = self.ruleset
        policy = self.decision_policy
        continuation = self.continuation_policy
        chip_option = self.chip_option_policy
        price = self.price_policy
        candidate = self.candidate_policy

        declared_pairs = (
            ("manager_state_id", manager_state),
            ("forecast_id", forecast),
            ("ruleset_id", ruleset),
            ("candidate_universe_id", universe),
            ("decision_policy_id", policy),
        )
        for field_name, document in declared_pairs:
            declared = str(decision_input.get(field_name) or "")
            actual = canonical_sha256(document)
            if declared != actual:
                raise ValueError(
                    f"planning reference {field_name} does not match embedded semantic document"
                )

        season = manager_state.get("season")
        if any(
            document.get("season") != season
            for document in (
                forecast,
                ruleset,
                policy,
                continuation,
                chip_option,
                price,
                candidate,
            )
        ):
            raise ValueError("planning reference solver season mismatch")
        if decision_input.get("gameweek") != manager_state.get("gameweek"):
            raise ValueError("planning reference solver gameweek mismatch")
        if manager_state.get("ruleset_id") != decision_input.get("ruleset_id"):
            raise ValueError("planning reference ManagerState RuleSetId mismatch")
        if forecast.get("ruleset_id") != decision_input.get("ruleset_id"):
            raise ValueError("planning reference Forecast RuleSetId mismatch")
        if forecast.get("global_world_id") != universe.get("global_world_id"):
            raise ValueError("planning reference solver world identity mismatch")
        if universe.get("scope") != "FULL_OFFICIAL":
            raise ValueError("planning reference solver requires FULL_OFFICIAL universe")
        if decision_input.get("objective_model") != "MARGINAL_INDEPENDENCE_BASELINE":
            raise ValueError("planning reference solver objective model is unsupported")
        if policy.get("evaluation_mode") != "RECEDING_HORIZON_WITH_CONTINUATION":
            raise ValueError("planning reference solver requires receding-horizon DecisionPolicy")
        if policy.get("objective_policy") != "MAX_EXPECTED_FPL_POINTS_OVER_TIME":
            raise ValueError("planning reference solver DecisionPolicy objective is unsupported")
        if policy.get("tie_break_policy") != "lexicographic-official-id-v1":
            raise ValueError("planning reference solver tie-break policy is unsupported")
        if decision_input.get("numeric_policy_id") != DECISION_NUMERIC_POLICY_ID:
            raise ValueError("planning reference DecisionInput numeric policy is unsupported")
        if policy.get("numeric_policy_id") != DECISION_NUMERIC_POLICY_ID:
            raise ValueError("planning reference DecisionPolicy numeric policy is unsupported")
        if decision_input.get("numeric_policy_id") != policy.get("numeric_policy_id"):
            raise ValueError("planning reference numeric policy mismatch")

        horizon = _positive_int(
            policy.get("horizon_gameweeks"),
            label="planning reference policy horizon",
        )
        if horizon < 2:
            raise ValueError("planning reference solver horizon must be at least two Gameweeks")
        if continuation.get("horizon_gameweeks") != horizon:
            raise ValueError("planning reference continuation horizon mismatch")
        if chip_option.get("horizon_gameweeks") != horizon:
            raise ValueError("planning reference chip-option horizon mismatch")
        if price.get("mode") != "OFFICIAL_CURRENT_ONLY":
            raise ValueError("planning reference price policy mode is unsupported")
        if candidate.get("mode") != "FULL_OFFICIAL":
            raise ValueError("planning reference candidate policy mode is unsupported")

        support_pairs = (
            ("continuation_value_artifact_id", continuation),
            ("chip_option_value_artifact_id", chip_option),
            ("price_policy_artifact_id", price),
            ("candidate_policy_artifact_id", candidate),
        )
        for field_name, document in support_pairs:
            if policy.get(field_name) != canonical_sha256(document):
                raise ValueError(f"planning reference DecisionPolicy {field_name} mismatch")

        if decision_input.get("max_normal_transfers") != 15:
            raise ValueError("planning reference exact surface requires max_normal_transfers=15")
        chips = decision_input.get("chips_considered")
        if not isinstance(chips, list) or set(chips) != _ALL_CHIPS or len(chips) != len(_ALL_CHIPS):
            raise ValueError("planning reference exact surface requires all five chip actions")
        if decision_input.get("use_mode") not in {"SHADOW", "PRODUCTION"}:
            raise ValueError("planning reference DecisionInput use_mode is invalid")
        object.__setattr__(self, "solver_contract", contract)

    @classmethod
    def from_semantic_documents(
        cls,
        *,
        decision_input: dict[str, object],
        manager_state: dict[str, object],
        forecast: dict[str, object],
        candidate_universe: dict[str, object],
        ruleset: dict[str, object],
        decision_policy: dict[str, object],
        continuation_policy: dict[str, object],
        chip_option_policy: dict[str, object],
        price_policy: dict[str, object],
        candidate_policy: dict[str, object],
        max_search_nodes: int,
    ) -> "PlanningReferenceSolverRequest":
        documents = {
            "decision_input_json": (decision_input, "apex-decision-input", "DecisionInput"),
            "manager_state_json": (manager_state, "apex-manager-state", "ManagerState"),
            "forecast_json": (forecast, "apex-probabilistic-forecast", "Forecast"),
            "candidate_universe_json": (
                candidate_universe,
                "apex-candidate-universe",
                "CandidateUniverse",
            ),
            "ruleset_json": (ruleset, "apex-fpl-ruleset", "RuleSet"),
            "decision_policy_json": (decision_policy, "apex-decision-policy", "DecisionPolicy"),
            "continuation_policy_json": (
                continuation_policy,
                "apex-decision-continuation-value-policy",
                "ContinuationValuePolicy",
            ),
            "chip_option_policy_json": (
                chip_option_policy,
                "apex-decision-chip-option-value-policy",
                "ChipOptionValuePolicy",
            ),
            "price_policy_json": (price_policy, "apex-decision-price-policy", "PricePolicy"),
            "candidate_policy_json": (
                candidate_policy,
                "apex-decision-candidate-policy",
                "CandidatePolicy",
            ),
        }
        encoded = {
            field: _canonical_document(document, schema_name=schema, label=label)
            for field, (document, schema, label) in documents.items()
        }
        return cls(max_search_nodes=max_search_nodes, **encoded)

    def _document(self, field: str, schema_name: str, label: str) -> dict[str, object]:
        return _load_document(getattr(self, field), schema_name=schema_name, label=label)

    @property
    def decision_input(self) -> dict[str, object]:
        return self._document("decision_input_json", "apex-decision-input", "planning DecisionInput")

    @property
    def manager_state(self) -> dict[str, object]:
        return self._document("manager_state_json", "apex-manager-state", "planning ManagerState")

    @property
    def forecast(self) -> dict[str, object]:
        return self._document("forecast_json", "apex-probabilistic-forecast", "planning Forecast")

    @property
    def candidate_universe(self) -> dict[str, object]:
        return self._document(
            "candidate_universe_json",
            "apex-candidate-universe",
            "planning CandidateUniverse",
        )

    @property
    def ruleset(self) -> dict[str, object]:
        return self._document("ruleset_json", "apex-fpl-ruleset", "planning RuleSet")

    @property
    def decision_policy(self) -> dict[str, object]:
        return self._document("decision_policy_json", "apex-decision-policy", "planning DecisionPolicy")

    @property
    def continuation_policy(self) -> dict[str, object]:
        return self._document(
            "continuation_policy_json",
            "apex-decision-continuation-value-policy",
            "planning ContinuationValuePolicy",
        )

    @property
    def chip_option_policy(self) -> dict[str, object]:
        return self._document(
            "chip_option_policy_json",
            "apex-decision-chip-option-value-policy",
            "planning ChipOptionValuePolicy",
        )

    @property
    def price_policy(self) -> dict[str, object]:
        return self._document("price_policy_json", "apex-decision-price-policy", "planning PricePolicy")

    @property
    def candidate_policy(self) -> dict[str, object]:
        return self._document(
            "candidate_policy_json",
            "apex-decision-candidate-policy",
            "planning CandidatePolicy",
        )

    @property
    def horizon_gameweeks(self) -> int:
        return _positive_int(
            self.decision_policy.get("horizon_gameweeks"),
            label="planning reference horizon",
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-planning-reference-solver-request",
            "schema_version": self.schema_version,
            "solver_contract": self.solver_contract,
            "max_search_nodes": self.max_search_nodes,
            "decision_input_json": self.decision_input_json,
            "manager_state_json": self.manager_state_json,
            "forecast_json": self.forecast_json,
            "candidate_universe_json": self.candidate_universe_json,
            "ruleset_json": self.ruleset_json,
            "decision_policy_json": self.decision_policy_json,
            "continuation_policy_json": self.continuation_policy_json,
            "chip_option_policy_json": self.chip_option_policy_json,
            "price_policy_json": self.price_policy_json,
            "candidate_policy_json": self.candidate_policy_json,
        }

    @property
    def request_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class PlanningReferenceSolverRun:
    request_id: str
    solver_status: PlanningReferenceSolverStatus
    best_objective: ExactSolverValue | None
    best_bound: ExactSolverValue | None
    gap: ExactSolverValue | None
    selected_action_id: str | None
    selected_trajectory_id: str | None
    selected_trajectory_json: str | None
    search_complete: bool
    nodes_evaluated: int
    pruned_nodes: int
    limit_reason: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported planning reference solver run schema_version")
        request_id = _nonempty(self.request_id, label="planning reference request_id")
        if not isinstance(self.solver_status, PlanningReferenceSolverStatus):
            raise ValueError("planning reference solver status must be typed")
        if not isinstance(self.search_complete, bool):
            raise ValueError("planning reference search_complete must be boolean")
        _nonnegative_int(self.nodes_evaluated, label="planning reference nodes_evaluated")
        _nonnegative_int(self.pruned_nodes, label="planning reference pruned_nodes")

        trajectory_fields = (
            self.selected_action_id,
            self.selected_trajectory_id,
            self.selected_trajectory_json,
        )
        if any(item is None for item in trajectory_fields) != all(
            item is None for item in trajectory_fields
        ):
            raise ValueError("planning reference selected trajectory fields must be present together")
        if self.selected_trajectory_json is not None:
            try:
                payload = json.loads(self.selected_trajectory_json)
            except json.JSONDecodeError as exc:
                raise ValueError("planning reference trajectory JSON is invalid") from exc
            if not isinstance(payload, dict):
                raise ValueError("planning reference trajectory JSON must be object")
            canonical = canonical_json_bytes(payload).decode("utf-8")
            if canonical != self.selected_trajectory_json:
                raise ValueError("planning reference trajectory JSON is not canonical")
            expected = canonical_sha256({"schema_name": "apex-planning-trajectory", **payload})
            if expected != self.selected_trajectory_id:
                raise ValueError("planning reference trajectory semantic identity mismatch")
            steps = payload.get("steps")
            if not isinstance(steps, list) or not steps or not isinstance(steps[0], dict):
                raise ValueError("planning reference selected trajectory requires steps")
            action = steps[0].get("action")
            if not isinstance(action, dict):
                raise ValueError("planning reference first step action is invalid")
            action_id = canonical_sha256({"schema_name": "apex-decision-action", **action})
            if action_id != self.selected_action_id:
                raise ValueError("planning reference selected action does not match trajectory")
            objective = _ratio(payload.get("selection_objective"), label="trajectory objective")
            if self.best_objective is not None and objective != self.best_objective:
                raise ValueError("planning reference trajectory objective does not match incumbent")

        if self.gap is not None:
            if self.best_objective is None or self.best_bound is None:
                raise ValueError("planning reference gap requires incumbent and bound")
            numerator = (
                self.best_bound.numerator * self.best_objective.denominator
                - self.best_objective.numerator * self.best_bound.denominator
            )
            denominator = self.best_bound.denominator * self.best_objective.denominator
            if ExactSolverValue(numerator, denominator) != self.gap or self.gap.numerator < 0:
                raise ValueError("planning reference gap does not reconcile")
        if self.solver_status is PlanningReferenceSolverStatus.OPTIMAL:
            if (
                not self.search_complete
                or self.best_objective is None
                or self.best_bound is None
                or self.gap is None
                or self.gap.numerator != 0
                or self.selected_action_id is None
                or self.limit_reason is not None
            ):
                raise ValueError("OPTIMAL planning reference run requires complete zero-gap trajectory")
        elif self.solver_status is PlanningReferenceSolverStatus.SOLVER_LIMIT:
            if self.search_complete or self.limit_reason is None:
                raise ValueError("SOLVER_LIMIT planning reference run requires incomplete search and reason")
        elif self.solver_status in {
            PlanningReferenceSolverStatus.INFEASIBLE,
            PlanningReferenceSolverStatus.ERROR,
        }:
            if self.search_complete and self.solver_status is PlanningReferenceSolverStatus.ERROR:
                raise ValueError("ERROR planning reference run cannot claim complete search")
            if self.selected_action_id is not None:
                raise ValueError(f"{self.solver_status.value} planning reference run cannot carry incumbent")
        object.__setattr__(self, "request_id", request_id)
        if self.limit_reason is not None:
            object.__setattr__(self, "limit_reason", _nonempty(self.limit_reason, label="limit reason"))

    def semantic_payload(self) -> dict[str, object]:
        def value(row: ExactSolverValue | None) -> dict[str, int] | None:
            return None if row is None else row.semantic_payload()

        return {
            "schema_name": "apex-planning-reference-solver-run",
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "solver_status": self.solver_status.value,
            "best_objective": value(self.best_objective),
            "best_bound": value(self.best_bound),
            "gap": value(self.gap),
            "selected_action_id": self.selected_action_id,
            "selected_trajectory_id": self.selected_trajectory_id,
            "selected_trajectory_json": self.selected_trajectory_json,
            "search_complete": self.search_complete,
            "nodes_evaluated": self.nodes_evaluated,
            "pruned_nodes": self.pruned_nodes,
            "limit_reason": self.limit_reason,
        }

    @property
    def run_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


def planning_request_from_payload(payload: dict[str, object]) -> PlanningReferenceSolverRequest:
    if payload.get("schema_name") != "apex-planning-reference-solver-request":
        raise ValueError("unsupported planning reference solver request schema")
    return PlanningReferenceSolverRequest(
        decision_input_json=str(payload.get("decision_input_json") or ""),
        manager_state_json=str(payload.get("manager_state_json") or ""),
        forecast_json=str(payload.get("forecast_json") or ""),
        candidate_universe_json=str(payload.get("candidate_universe_json") or ""),
        ruleset_json=str(payload.get("ruleset_json") or ""),
        decision_policy_json=str(payload.get("decision_policy_json") or ""),
        continuation_policy_json=str(payload.get("continuation_policy_json") or ""),
        chip_option_policy_json=str(payload.get("chip_option_policy_json") or ""),
        price_policy_json=str(payload.get("price_policy_json") or ""),
        candidate_policy_json=str(payload.get("candidate_policy_json") or ""),
        max_search_nodes=_positive_int(
            payload.get("max_search_nodes"), label="planning reference max_search_nodes"
        ),
        solver_contract=str(payload.get("solver_contract") or ""),
        schema_version=_positive_int(
            payload.get("schema_version"), label="planning reference schema_version"
        ),
    )


def _optional_value(value: object, *, label: str) -> ExactSolverValue | None:
    return None if value is None else _ratio(value, label=label)


def planning_run_from_payload(payload: dict[str, object]) -> PlanningReferenceSolverRun:
    if payload.get("schema_name") != "apex-planning-reference-solver-run":
        raise ValueError("unsupported planning reference solver run schema")
    return PlanningReferenceSolverRun(
        request_id=str(payload.get("request_id") or ""),
        solver_status=PlanningReferenceSolverStatus(str(payload.get("solver_status") or "")),
        best_objective=_optional_value(payload.get("best_objective"), label="best objective"),
        best_bound=_optional_value(payload.get("best_bound"), label="best bound"),
        gap=_optional_value(payload.get("gap"), label="gap"),
        selected_action_id=(
            None if payload.get("selected_action_id") is None else str(payload.get("selected_action_id"))
        ),
        selected_trajectory_id=(
            None
            if payload.get("selected_trajectory_id") is None
            else str(payload.get("selected_trajectory_id"))
        ),
        selected_trajectory_json=(
            None
            if payload.get("selected_trajectory_json") is None
            else str(payload.get("selected_trajectory_json"))
        ),
        search_complete=payload.get("search_complete"),  # type: ignore[arg-type]
        nodes_evaluated=_nonnegative_int(
            payload.get("nodes_evaluated"), label="planning reference nodes_evaluated"
        ),
        pruned_nodes=_nonnegative_int(
            payload.get("pruned_nodes"), label="planning reference pruned_nodes"
        ),
        limit_reason=(
            None if payload.get("limit_reason") is None else str(payload.get("limit_reason"))
        ),
        schema_version=_positive_int(
            payload.get("schema_version"), label="planning reference run schema_version"
        ),
    )
