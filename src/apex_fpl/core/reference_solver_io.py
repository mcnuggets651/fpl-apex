"""Dependency-free sealed I/O contracts for the isolated V2 reference solver worker."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import json

from .canonical import canonical_json_bytes, canonical_sha256


REFERENCE_SOLVER_CONTRACT = "apex-v2-exact-decision-parity-v1"


def _nonempty(value: str, *, label: str) -> str:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{label} cannot be empty")
    return text


def _canonical_document(value: dict[str, object], *, schema_name: str, label: str) -> str:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
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


def _strict_positive_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be positive integer")
    return value


def _strict_nonnegative_int(value: object, *, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{label} must be nonnegative integer")
    return value


@dataclass(frozen=True, slots=True)
class ExactSolverValue:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        from math import gcd

        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise ValueError("solver value numerator must be integer")
        if (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, int)
            or self.denominator <= 0
        ):
            raise ValueError("solver value denominator must be positive integer")
        divisor = gcd(abs(self.numerator), self.denominator)
        object.__setattr__(self, "numerator", self.numerator // divisor)
        object.__setattr__(self, "denominator", self.denominator // divisor)

    @classmethod
    def zero(cls) -> "ExactSolverValue":
        return cls(0, 1)

    def semantic_payload(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


class ReferenceSolverRunStatus(StrEnum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    SOLVER_LIMIT = "SOLVER_LIMIT"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class ReferenceSolverRequest:
    decision_input_json: str
    manager_state_json: str
    forecast_json: str
    candidate_universe_json: str
    ruleset_json: str
    decision_policy_json: str
    max_search_nodes: int
    solver_contract: str = REFERENCE_SOLVER_CONTRACT
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reference solver request schema_version")
        contract = _nonempty(self.solver_contract, label="reference solver contract")
        if contract != REFERENCE_SOLVER_CONTRACT:
            raise ValueError("unsupported reference solver contract")
        if (
            isinstance(self.max_search_nodes, bool)
            or not isinstance(self.max_search_nodes, int)
            or self.max_search_nodes <= 0
        ):
            raise ValueError("reference solver max_search_nodes must be positive integer")

        decision_input = _load_document(
            self.decision_input_json,
            schema_name="apex-decision-input",
            label="reference solver DecisionInput",
        )
        manager_state = _load_document(
            self.manager_state_json,
            schema_name="apex-manager-state",
            label="reference solver ManagerState",
        )
        forecast = _load_document(
            self.forecast_json,
            schema_name="apex-probabilistic-forecast",
            label="reference solver Forecast",
        )
        universe = _load_document(
            self.candidate_universe_json,
            schema_name="apex-candidate-universe",
            label="reference solver CandidateUniverse",
        )
        ruleset = _load_document(
            self.ruleset_json,
            schema_name="apex-fpl-ruleset",
            label="reference solver RuleSet",
        )
        policy = _load_document(
            self.decision_policy_json,
            schema_name="apex-decision-policy",
            label="reference solver DecisionPolicy",
        )

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
                    f"reference solver {field_name} does not match embedded semantic document"
                )
        if decision_input.get("gameweek") != manager_state.get("gameweek"):
            raise ValueError("reference solver gameweek mismatch")
        if manager_state.get("ruleset_id") != decision_input.get("ruleset_id"):
            raise ValueError("reference solver ManagerState RuleSetId mismatch")
        if forecast.get("ruleset_id") != decision_input.get("ruleset_id"):
            raise ValueError("reference solver Forecast RuleSetId mismatch")
        if manager_state.get("season") != forecast.get("season"):
            raise ValueError("reference solver season mismatch")
        if manager_state.get("season") != ruleset.get("season"):
            raise ValueError("reference solver RuleSet season mismatch")
        if manager_state.get("season") != policy.get("season"):
            raise ValueError("reference solver DecisionPolicy season mismatch")
        if forecast.get("global_world_id") != universe.get("global_world_id"):
            raise ValueError("reference solver world identity mismatch")
        if decision_input.get("objective_model") != "MARGINAL_INDEPENDENCE_BASELINE":
            raise ValueError("reference solver request uses unsupported objective model")
        if policy.get("evaluation_mode") != "TACTICAL_CURRENT_GAMEWEEK":
            raise ValueError(
                "reference solver v1 accepts only tactical current-Gameweek DecisionPolicy"
            )
        if decision_input.get("decision_policy_id") != canonical_sha256(policy):
            raise ValueError("reference solver DecisionPolicy identity mismatch")
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
        max_search_nodes: int,
    ) -> "ReferenceSolverRequest":
        return cls(
            decision_input_json=_canonical_document(
                decision_input,
                schema_name="apex-decision-input",
                label="DecisionInput",
            ),
            manager_state_json=_canonical_document(
                manager_state,
                schema_name="apex-manager-state",
                label="ManagerState",
            ),
            forecast_json=_canonical_document(
                forecast,
                schema_name="apex-probabilistic-forecast",
                label="Forecast",
            ),
            candidate_universe_json=_canonical_document(
                candidate_universe,
                schema_name="apex-candidate-universe",
                label="CandidateUniverse",
            ),
            ruleset_json=_canonical_document(
                ruleset,
                schema_name="apex-fpl-ruleset",
                label="RuleSet",
            ),
            decision_policy_json=_canonical_document(
                decision_policy,
                schema_name="apex-decision-policy",
                label="DecisionPolicy",
            ),
            max_search_nodes=max_search_nodes,
        )

    @property
    def decision_input(self) -> dict[str, object]:
        return _load_document(
            self.decision_input_json,
            schema_name="apex-decision-input",
            label="reference solver DecisionInput",
        )

    @property
    def manager_state(self) -> dict[str, object]:
        return _load_document(
            self.manager_state_json,
            schema_name="apex-manager-state",
            label="reference solver ManagerState",
        )

    @property
    def forecast(self) -> dict[str, object]:
        return _load_document(
            self.forecast_json,
            schema_name="apex-probabilistic-forecast",
            label="reference solver Forecast",
        )

    @property
    def candidate_universe(self) -> dict[str, object]:
        return _load_document(
            self.candidate_universe_json,
            schema_name="apex-candidate-universe",
            label="reference solver CandidateUniverse",
        )

    @property
    def ruleset(self) -> dict[str, object]:
        return _load_document(
            self.ruleset_json,
            schema_name="apex-fpl-ruleset",
            label="reference solver RuleSet",
        )

    @property
    def decision_policy(self) -> dict[str, object]:
        return _load_document(
            self.decision_policy_json,
            schema_name="apex-decision-policy",
            label="reference solver DecisionPolicy",
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-reference-solver-request",
            "schema_version": self.schema_version,
            "solver_contract": self.solver_contract,
            "max_search_nodes": self.max_search_nodes,
            "decision_input_json": self.decision_input_json,
            "manager_state_json": self.manager_state_json,
            "forecast_json": self.forecast_json,
            "candidate_universe_json": self.candidate_universe_json,
            "ruleset_json": self.ruleset_json,
            "decision_policy_json": self.decision_policy_json,
        }

    @property
    def request_id(self) -> str:
        return canonical_sha256(self.semantic_payload())

    @property
    def decision_input_id(self) -> str:
        return canonical_sha256(self.decision_input)

    @property
    def candidate_universe_id(self) -> str:
        return canonical_sha256(self.candidate_universe)

    @property
    def decision_policy_id(self) -> str:
        return canonical_sha256(self.decision_policy)


@dataclass(frozen=True, slots=True)
class ReferenceSolverRun:
    request_id: str
    solver_status: ReferenceSolverRunStatus
    best_objective: ExactSolverValue | None
    best_bound: ExactSolverValue | None
    gap: ExactSolverValue | None
    selected_action_id: str | None
    selected_action_json: str | None
    action_surface_complete: bool
    tie_break_policy_id: str | None
    nodes_evaluated: int
    actions_evaluated: int
    limit_reason: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported reference solver run schema_version")
        request_id = _nonempty(self.request_id, label="reference solver request_id")
        if not isinstance(self.solver_status, ReferenceSolverRunStatus):
            raise ValueError("reference solver run status must be typed")
        for label, value in (
            ("nodes_evaluated", self.nodes_evaluated),
            ("actions_evaluated", self.actions_evaluated),
        ):
            _strict_nonnegative_int(value, label=label)
        if not isinstance(self.action_surface_complete, bool):
            raise ValueError("reference solver action_surface_complete must be boolean")
        selected_id = self.selected_action_id
        selected_json = self.selected_action_json
        if (selected_id is None) != (selected_json is None):
            raise ValueError(
                "reference solver selected action identity/payload must be present together"
            )
        if selected_json is not None:
            try:
                selected_payload = json.loads(selected_json)
            except json.JSONDecodeError as exc:
                raise ValueError("reference solver selected action JSON is invalid") from exc
            if not isinstance(selected_payload, dict):
                raise ValueError("reference solver selected action JSON must be object")
            canonical = canonical_json_bytes(selected_payload).decode("utf-8")
            if canonical != selected_json:
                raise ValueError("reference solver selected action JSON is not canonical")
            expected_id = canonical_sha256(
                {"schema_name": "apex-decision-action", **selected_payload}
            )
            if expected_id != selected_id:
                raise ValueError("reference solver selected action semantic identity mismatch")
        if self.tie_break_policy_id is not None:
            object.__setattr__(
                self,
                "tie_break_policy_id",
                _nonempty(self.tie_break_policy_id, label="reference solver tie-break policy"),
            )
        if self.limit_reason is not None:
            object.__setattr__(
                self,
                "limit_reason",
                _nonempty(self.limit_reason, label="reference solver limit reason"),
            )

        if self.gap is not None:
            if self.best_objective is None or self.best_bound is None:
                raise ValueError("reference solver gap requires objective and bound")
            left = (
                self.best_bound.numerator * self.best_objective.denominator
                - self.best_objective.numerator * self.best_bound.denominator
            )
            denominator = self.best_bound.denominator * self.best_objective.denominator
            if ExactSolverValue(left, denominator) != self.gap or self.gap.numerator < 0:
                raise ValueError("reference solver gap does not reconcile")
        if self.solver_status is ReferenceSolverRunStatus.OPTIMAL:
            if (
                self.best_objective is None
                or self.best_bound is None
                or self.gap is None
                or self.gap.numerator != 0
                or selected_id is None
                or not self.action_surface_complete
                or self.limit_reason is not None
            ):
                raise ValueError("OPTIMAL reference solver run requires complete zero-gap action")
        if self.solver_status is ReferenceSolverRunStatus.INFEASIBLE:
            if (
                self.best_objective is not None
                or self.best_bound is not None
                or self.gap is not None
                or selected_id is not None
            ):
                raise ValueError("INFEASIBLE reference solver run cannot carry incumbent")
        if self.solver_status is ReferenceSolverRunStatus.ERROR and selected_id is not None:
            raise ValueError("ERROR reference solver run cannot carry selected action")
        if self.solver_status is ReferenceSolverRunStatus.SOLVER_LIMIT:
            if self.action_surface_complete:
                raise ValueError("SOLVER_LIMIT cannot claim complete action surface")
            if self.limit_reason is None:
                raise ValueError("SOLVER_LIMIT requires explicit limit reason")
        object.__setattr__(self, "request_id", request_id)

    def semantic_payload(self) -> dict[str, object]:
        def value(row: ExactSolverValue | None) -> dict[str, int] | None:
            return None if row is None else row.semantic_payload()

        return {
            "schema_name": "apex-reference-solver-run",
            "schema_version": self.schema_version,
            "request_id": self.request_id,
            "solver_status": self.solver_status.value,
            "best_objective": value(self.best_objective),
            "best_bound": value(self.best_bound),
            "gap": value(self.gap),
            "selected_action_id": self.selected_action_id,
            "selected_action_json": self.selected_action_json,
            "action_surface_complete": self.action_surface_complete,
            "tie_break_policy_id": self.tie_break_policy_id,
            "nodes_evaluated": self.nodes_evaluated,
            "actions_evaluated": self.actions_evaluated,
            "limit_reason": self.limit_reason,
        }

    @property
    def run_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


def request_from_payload(payload: dict[str, object]) -> ReferenceSolverRequest:
    if payload.get("schema_name") != "apex-reference-solver-request":
        raise ValueError("unsupported reference solver request schema")
    return ReferenceSolverRequest(
        decision_input_json=str(payload.get("decision_input_json") or ""),
        manager_state_json=str(payload.get("manager_state_json") or ""),
        forecast_json=str(payload.get("forecast_json") or ""),
        candidate_universe_json=str(payload.get("candidate_universe_json") or ""),
        ruleset_json=str(payload.get("ruleset_json") or ""),
        decision_policy_json=str(payload.get("decision_policy_json") or ""),
        max_search_nodes=_strict_positive_int(
            payload.get("max_search_nodes"),
            label="reference solver max_search_nodes",
        ),
        solver_contract=str(payload.get("solver_contract") or ""),
        schema_version=_strict_positive_int(
            payload.get("schema_version"),
            label="reference solver request schema_version",
        ),
    )


def _value_from_payload(value: object, *, label: str) -> ExactSolverValue | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be object or null")
    return ExactSolverValue(
        numerator=value.get("numerator"),  # type: ignore[arg-type]
        denominator=value.get("denominator"),  # type: ignore[arg-type]
    )


def run_from_payload(payload: dict[str, object]) -> ReferenceSolverRun:
    if payload.get("schema_name") != "apex-reference-solver-run":
        raise ValueError("unsupported reference solver run schema")
    return ReferenceSolverRun(
        request_id=str(payload.get("request_id") or ""),
        solver_status=ReferenceSolverRunStatus(str(payload.get("solver_status") or "")),
        best_objective=_value_from_payload(
            payload.get("best_objective"),
            label="reference solver best_objective",
        ),
        best_bound=_value_from_payload(
            payload.get("best_bound"),
            label="reference solver best_bound",
        ),
        gap=_value_from_payload(payload.get("gap"), label="reference solver gap"),
        selected_action_id=(
            None
            if payload.get("selected_action_id") is None
            else str(payload.get("selected_action_id"))
        ),
        selected_action_json=(
            None
            if payload.get("selected_action_json") is None
            else str(payload.get("selected_action_json"))
        ),
        action_surface_complete=payload.get("action_surface_complete"),  # type: ignore[arg-type]
        tie_break_policy_id=(
            None
            if payload.get("tie_break_policy_id") is None
            else str(payload.get("tie_break_policy_id"))
        ),
        nodes_evaluated=_strict_nonnegative_int(
            payload.get("nodes_evaluated"),
            label="reference solver nodes_evaluated",
        ),
        actions_evaluated=_strict_nonnegative_int(
            payload.get("actions_evaluated"),
            label="reference solver actions_evaluated",
        ),
        limit_reason=(
            None if payload.get("limit_reason") is None else str(payload.get("limit_reason"))
        ),
        schema_version=_strict_positive_int(
            payload.get("schema_version"),
            label="reference solver run schema_version",
        ),
    )
