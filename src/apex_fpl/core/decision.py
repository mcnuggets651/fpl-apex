"""Typed legal-decision contracts for Apex V2 Slice 8.

The DecisionEngine optimises one declared action surface over one declared candidate
universe. Exactness is therefore a first-class scope, not a marketing adjective.
Expected-value mechanics use rational numbers and explicitly name the marginal
independence baseline that Slice 9 later stress-tests with correlated scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import gcd

from .canonical import canonical_sha256
from .identity import OfficialPlayerId
from .ids import (
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    DecisionPolicyId,
    ForecastId,
    GlobalWorldId,
    ManagerStateId,
    RuleSetId,
)


DEFAULT_NUMERIC_POLICY_ID = "decision-rational-v1"


def _artifact_id(value: str, *, label: str) -> str:
    text = str(value).strip()
    algorithm, separator, digest = text.partition(":")
    if algorithm != "sha256" or not separator or len(digest) != 64:
        raise ValueError(f"{label} must be sha256 content identity")
    try:
        int(digest, 16)
    except ValueError as exc:
        raise ValueError(f"{label} digest is invalid") from exc
    return text


class CandidateUniverseScope(str, Enum):
    FULL_OFFICIAL = "FULL_OFFICIAL"
    SCOPED = "SCOPED"


class DecisionUseMode(str, Enum):
    SHADOW = "SHADOW"
    PRODUCTION = "PRODUCTION"


class DecisionChip(str, Enum):
    NONE = "NONE"
    TRIPLE_CAPTAIN = "TRIPLE_CAPTAIN"
    BENCH_BOOST = "BENCH_BOOST"
    WILDCARD = "WILDCARD"
    FREE_HIT = "FREE_HIT"


class DecisionObjectiveModel(str, Enum):
    MARGINAL_INDEPENDENCE_BASELINE = "MARGINAL_INDEPENDENCE_BASELINE"


class SolverStatus(str, Enum):
    OPTIMAL = "OPTIMAL"
    FEASIBLE = "FEASIBLE"
    INFEASIBLE = "INFEASIBLE"
    UNBOUNDED = "UNBOUNDED"
    SOLVER_LIMIT = "SOLVER_LIMIT"
    ERROR = "ERROR"
    INVALID_INPUT = "INVALID_INPUT"


class ExactnessStatus(str, Enum):
    GLOBAL_OPTIMAL = "GLOBAL_OPTIMAL"
    EPSILON_GLOBAL_OPTIMAL = "EPSILON_GLOBAL_OPTIMAL"
    OPTIMAL_WITHIN_CERTIFIED_UNIVERSE = "OPTIMAL_WITHIN_CERTIFIED_UNIVERSE"
    FEASIBLE_INCUMBENT = "FEASIBLE_INCUMBENT"
    INCONCLUSIVE = "INCONCLUSIVE"


class ExpansionResult(str, Enum):
    NOT_RUN = "NOT_RUN"
    NO_MATERIAL_IMPROVEMENT = "NO_MATERIAL_IMPROVEMENT"
    MATERIAL_IMPROVEMENT_FOUND = "MATERIAL_IMPROVEMENT_FOUND"


@dataclass(frozen=True, slots=True)
class CandidatePlayer:
    player_id: OfficialPlayerId
    team_id: int
    position: str
    current_price_tenths: int

    def __post_init__(self) -> None:
        if (
            isinstance(self.team_id, bool)
            or not isinstance(self.team_id, int)
            or self.team_id <= 0
        ):
            raise ValueError("candidate team_id must be a positive integer")
        if self.position not in {"GK", "DEF", "MID", "FWD"}:
            raise ValueError(f"invalid candidate position: {self.position!r}")
        if (
            isinstance(self.current_price_tenths, bool)
            or not isinstance(self.current_price_tenths, int)
            or self.current_price_tenths <= 0
        ):
            raise ValueError("candidate current price must be positive integer tenths")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "player_id": int(self.player_id),
            "team_id": self.team_id,
            "position": self.position,
            "current_price_tenths": self.current_price_tenths,
        }


@dataclass(frozen=True, slots=True)
class CandidateUniverse:
    global_world_id: GlobalWorldId
    scope: CandidateUniverseScope
    players: tuple[CandidatePlayer, ...]
    official_player_count: int
    source_artifact_ids: tuple[str, ...]
    filter_artifact_id: str | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported CandidateUniverse schema_version")
        if (
            isinstance(self.official_player_count, bool)
            or not isinstance(self.official_player_count, int)
            or self.official_player_count <= 0
        ):
            raise ValueError("official_player_count must be a positive integer")
        players = tuple(sorted(self.players, key=lambda row: int(row.player_id)))
        ids = [row.player_id for row in players]
        if not players or len(ids) != len(set(ids)):
            raise ValueError("candidate universe requires unique players")
        if (
            self.scope is CandidateUniverseScope.FULL_OFFICIAL
            and len(players) != self.official_player_count
        ):
            raise ValueError(
                "FULL_OFFICIAL candidate universe must contain every Official player"
            )
        if len(players) > self.official_player_count:
            raise ValueError("candidate universe cannot exceed Official player count")
        artifacts = tuple(
            sorted(
                {
                    _artifact_id(item, label="candidate universe source artifact")
                    for item in self.source_artifact_ids
                }
            )
        )
        if not artifacts:
            raise ValueError("candidate universe requires immutable source lineage")
        filter_artifact = self.filter_artifact_id
        if self.scope is CandidateUniverseScope.FULL_OFFICIAL:
            if filter_artifact is not None:
                raise ValueError("FULL_OFFICIAL universe cannot carry a prefilter artifact")
        else:
            if filter_artifact is None:
                raise ValueError(
                    "SCOPED candidate universe requires a versioned/hashable filter artifact"
                )
            filter_artifact = _artifact_id(
                filter_artifact,
                label="candidate filter artifact",
            )
            if filter_artifact not in artifacts:
                raise ValueError(
                    "candidate filter artifact must be included in universe lineage"
                )
        object.__setattr__(self, "players", players)
        object.__setattr__(self, "source_artifact_ids", artifacts)
        object.__setattr__(self, "filter_artifact_id", filter_artifact)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-candidate-universe",
            "schema_version": self.schema_version,
            "global_world_id": str(self.global_world_id),
            "scope": self.scope.value,
            "official_player_count": self.official_player_count,
            "players": [row.semantic_payload() for row in self.players],
            "source_artifact_ids": list(self.source_artifact_ids),
            "filter_artifact_id": self.filter_artifact_id,
        }

    @property
    def candidate_universe_id(self) -> CandidateUniverseId:
        return CandidateUniverseId(canonical_sha256(self.semantic_payload()))

    @property
    def filter_identity(self) -> str:
        return "FULL_OFFICIAL" if self.filter_artifact_id is None else self.filter_artifact_id

    def player(self, player_id: OfficialPlayerId) -> CandidatePlayer:
        for row in self.players:
            if row.player_id == player_id:
                return row
        raise ValueError(f"player {player_id} is outside the candidate universe")


@dataclass(frozen=True, slots=True)
class DecisionInput:
    manager_state_id: ManagerStateId
    forecast_id: ForecastId
    ruleset_id: RuleSetId
    candidate_universe_id: CandidateUniverseId
    decision_policy_id: DecisionPolicyId
    gameweek: int
    use_mode: DecisionUseMode
    objective_model: DecisionObjectiveModel
    max_normal_transfers: int
    chips_considered: tuple[DecisionChip, ...]
    numeric_policy_id: str = DEFAULT_NUMERIC_POLICY_ID
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported DecisionInput schema_version")
        if (
            isinstance(self.gameweek, bool)
            or not isinstance(self.gameweek, int)
            or self.gameweek <= 0
        ):
            raise ValueError("decision gameweek must be a positive integer")
        if (
            isinstance(self.max_normal_transfers, bool)
            or not isinstance(self.max_normal_transfers, int)
            or not 0 <= self.max_normal_transfers <= 15
        ):
            raise ValueError("max_normal_transfers must be an integer in [0,15]")
        chips = tuple(sorted(set(self.chips_considered), key=lambda chip: chip.value))
        if not chips or DecisionChip.NONE not in chips:
            raise ValueError("decision action surface must include NONE")
        numeric_policy = str(self.numeric_policy_id).strip()
        if not numeric_policy:
            raise ValueError("decision numeric policy identity cannot be empty")
        object.__setattr__(self, "chips_considered", chips)
        object.__setattr__(self, "numeric_policy_id", numeric_policy)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-input",
            "schema_version": self.schema_version,
            "manager_state_id": str(self.manager_state_id),
            "forecast_id": str(self.forecast_id),
            "ruleset_id": str(self.ruleset_id),
            "candidate_universe_id": str(self.candidate_universe_id),
            "decision_policy_id": str(self.decision_policy_id),
            "gameweek": self.gameweek,
            "use_mode": self.use_mode.value,
            "objective_model": self.objective_model.value,
            "max_normal_transfers": self.max_normal_transfers,
            "chips_considered": [chip.value for chip in self.chips_considered],
            "numeric_policy_id": self.numeric_policy_id,
        }

    @property
    def decision_input_id(self) -> DecisionInputId:
        return DecisionInputId(canonical_sha256(self.semantic_payload()))


@dataclass(frozen=True, slots=True, order=True)
class TransferMove:
    outgoing_player_id: OfficialPlayerId
    incoming_player_id: OfficialPlayerId

    def __post_init__(self) -> None:
        if self.outgoing_player_id == self.incoming_player_id:
            raise ValueError("transfer move must change player")

    def semantic_payload(self) -> dict[str, int]:
        return {
            "outgoing_player_id": int(self.outgoing_player_id),
            "incoming_player_id": int(self.incoming_player_id),
        }


@dataclass(frozen=True, slots=True)
class RationalValue:
    numerator: int
    denominator: int

    def __post_init__(self) -> None:
        if isinstance(self.numerator, bool) or not isinstance(self.numerator, int):
            raise ValueError("rational numerator must be integer")
        if (
            isinstance(self.denominator, bool)
            or not isinstance(self.denominator, int)
            or self.denominator <= 0
        ):
            raise ValueError("rational denominator must be positive integer")
        divisor = gcd(abs(self.numerator), self.denominator)
        object.__setattr__(self, "numerator", self.numerator // divisor)
        object.__setattr__(self, "denominator", self.denominator // divisor)

    @classmethod
    def zero(cls) -> "RationalValue":
        return cls(0, 1)

    def semantic_payload(self) -> dict[str, int]:
        return {"numerator": self.numerator, "denominator": self.denominator}


@dataclass(frozen=True, slots=True)
class DecisionMechanics:
    xi_points: RationalValue
    autosub_points: RationalValue
    captain_bonus: RationalValue
    squad_points_if_bench_boost: RationalValue
    points_before_hits: RationalValue
    hit_points: int
    objective_points: RationalValue

    def __post_init__(self) -> None:
        if (
            isinstance(self.hit_points, bool)
            or not isinstance(self.hit_points, int)
            or self.hit_points < 0
        ):
            raise ValueError("decision hit_points must be nonnegative integer")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "xi_points": self.xi_points.semantic_payload(),
            "autosub_points": self.autosub_points.semantic_payload(),
            "captain_bonus": self.captain_bonus.semantic_payload(),
            "squad_points_if_bench_boost": (
                self.squad_points_if_bench_boost.semantic_payload()
            ),
            "points_before_hits": self.points_before_hits.semantic_payload(),
            "hit_points": self.hit_points,
            "objective_points": self.objective_points.semantic_payload(),
        }


@dataclass(frozen=True, slots=True)
class DecisionAction:
    chip: DecisionChip
    transfers: tuple[TransferMove, ...]
    squad_ids: tuple[OfficialPlayerId, ...]
    xi_ids: tuple[OfficialPlayerId, ...]
    captain_id: OfficialPlayerId
    vice_captain_id: OfficialPlayerId
    bench_gk_id: OfficialPlayerId
    outfield_bench_order: tuple[OfficialPlayerId, ...]
    bank_after_tenths: int
    mechanics: DecisionMechanics

    def __post_init__(self) -> None:
        transfers = tuple(sorted(self.transfers))
        if len({row.outgoing_player_id for row in transfers}) != len(transfers):
            raise ValueError(
                "decision action transfers contain duplicate outgoing players"
            )
        if len({row.incoming_player_id for row in transfers}) != len(transfers):
            raise ValueError(
                "decision action transfers contain duplicate incoming players"
            )
        squad = tuple(sorted(self.squad_ids))
        xi = tuple(sorted(self.xi_ids))
        bench_order = tuple(self.outfield_bench_order)
        if len(squad) != 15 or len(set(squad)) != 15:
            raise ValueError("decision action requires exactly 15 unique squad players")
        if (
            len(xi) != 11
            or len(set(xi)) != 11
            or not set(xi).issubset(set(squad))
        ):
            raise ValueError(
                "decision action requires exactly 11 unique XI players from squad"
            )
        if (
            self.captain_id == self.vice_captain_id
            or self.captain_id not in xi
            or self.vice_captain_id not in xi
        ):
            raise ValueError("captain and vice must be distinct XI players")
        bench = set(squad) - set(xi)
        if self.bench_gk_id not in bench:
            raise ValueError("bench goalkeeper must be outside XI")
        if len(bench_order) != 3 or len(set(bench_order)) != 3:
            raise ValueError(
                "decision action requires three ordered outfield substitutes"
            )
        if set(bench_order) | {self.bench_gk_id} != bench:
            raise ValueError(
                "decision bench order must cover the four non-XI players exactly"
            )
        if (
            isinstance(self.bank_after_tenths, bool)
            or not isinstance(self.bank_after_tenths, int)
            or self.bank_after_tenths < 0
        ):
            raise ValueError(
                "decision bank_after_tenths must be nonnegative integer"
            )
        object.__setattr__(self, "transfers", transfers)
        object.__setattr__(self, "squad_ids", squad)
        object.__setattr__(self, "xi_ids", xi)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "chip": self.chip.value,
            "transfers": [row.semantic_payload() for row in self.transfers],
            "squad_ids": [int(item) for item in self.squad_ids],
            "xi_ids": [int(item) for item in self.xi_ids],
            "captain_id": int(self.captain_id),
            "vice_captain_id": int(self.vice_captain_id),
            "bench_gk_id": int(self.bench_gk_id),
            "outfield_bench_order": [
                int(item) for item in self.outfield_bench_order
            ],
            "bank_after_tenths": self.bank_after_tenths,
            "mechanics": self.mechanics.semantic_payload(),
        }

    @property
    def action_id(self) -> str:
        return canonical_sha256(
            {"schema_name": "apex-decision-action", **self.semantic_payload()}
        )


@dataclass(frozen=True, slots=True)
class SolverCertificate:
    status: SolverStatus
    incumbent_objective: RationalValue | None
    best_bound: RationalValue | None
    gap: RationalValue | None
    numeric_error_bound: RationalValue
    message: str

    def __post_init__(self) -> None:
        message = str(self.message).strip()
        if not message:
            raise ValueError("solver certificate requires a message")
        if self.numeric_error_bound.numerator < 0:
            raise ValueError("numeric error bound cannot be negative")
        if self.gap is not None and self.gap.numerator < 0:
            raise ValueError("solver gap cannot be negative")
        if self.status is SolverStatus.OPTIMAL:
            if (
                self.incumbent_objective is None
                or self.best_bound is None
                or self.gap is None
            ):
                raise ValueError("OPTIMAL solver result requires incumbent/bound/gap")
            if self.gap.numerator != 0:
                raise ValueError("OPTIMAL solver result must have zero gap")
        if self.status in {
            SolverStatus.INFEASIBLE,
            SolverStatus.UNBOUNDED,
            SolverStatus.ERROR,
            SolverStatus.INVALID_INPUT,
        } and self.incumbent_objective is not None:
            raise ValueError(
                f"{self.status.value} solver result cannot carry an incumbent"
            )
        object.__setattr__(self, "message", message)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "incumbent_objective": (
                None
                if self.incumbent_objective is None
                else self.incumbent_objective.semantic_payload()
            ),
            "best_bound": (
                None if self.best_bound is None else self.best_bound.semantic_payload()
            ),
            "gap": None if self.gap is None else self.gap.semantic_payload(),
            "numeric_error_bound": self.numeric_error_bound.semantic_payload(),
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class CandidateExpansionCertificate:
    baseline_universe_id: CandidateUniverseId
    expanded_universe_id: CandidateUniverseId
    expanded_universe_scope: CandidateUniverseScope
    baseline_objective: RationalValue
    expanded_objective: RationalValue
    materiality_threshold: RationalValue
    result: ExpansionResult
    expanded_exactness_status: ExactnessStatus
    source_artifact_id: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported CandidateExpansionCertificate schema_version")
        if self.baseline_universe_id == self.expanded_universe_id:
            raise ValueError("expansion certificate requires a different expanded universe")
        if self.materiality_threshold.numerator < 0:
            raise ValueError("expansion materiality threshold cannot be negative")
        source = _artifact_id(
            self.source_artifact_id,
            label="candidate expansion source artifact",
        )
        object.__setattr__(self, "source_artifact_id", source)
        if self.result is ExpansionResult.NOT_RUN:
            raise ValueError("stored expansion certificate cannot have NOT_RUN result")

    @property
    def certifies_baseline_universe(self) -> bool:
        return (
            self.result is ExpansionResult.NO_MATERIAL_IMPROVEMENT
            and self.expanded_universe_scope is CandidateUniverseScope.FULL_OFFICIAL
            and self.expanded_exactness_status is ExactnessStatus.GLOBAL_OPTIMAL
        )

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-candidate-expansion-certificate",
            "schema_version": self.schema_version,
            "baseline_universe_id": str(self.baseline_universe_id),
            "expanded_universe_id": str(self.expanded_universe_id),
            "expanded_universe_scope": self.expanded_universe_scope.value,
            "baseline_objective": self.baseline_objective.semantic_payload(),
            "expanded_objective": self.expanded_objective.semantic_payload(),
            "materiality_threshold": self.materiality_threshold.semantic_payload(),
            "result": self.result.value,
            "expanded_exactness_status": self.expanded_exactness_status.value,
            "source_artifact_id": self.source_artifact_id,
        }

    @property
    def certificate_id(self) -> str:
        return canonical_sha256(self.semantic_payload())


@dataclass(frozen=True, slots=True)
class ExactnessClaim:
    status: ExactnessStatus
    candidate_universe_id: CandidateUniverseId
    universe_scope: CandidateUniverseScope
    solver_status: SolverStatus
    action_surface_complete: bool
    search_complete: bool
    best_bound: RationalValue | None
    gap: RationalValue | None
    filter_identity: str
    expansion_result: ExpansionResult
    expansion_certificate_id: str | None
    numeric_error_bound: RationalValue
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        filter_identity = str(self.filter_identity).strip()
        if not filter_identity:
            raise ValueError("exactness claim requires candidate filter identity")
        if self.numeric_error_bound.numerator < 0:
            raise ValueError("exactness numeric error bound cannot be negative")
        if self.gap is not None and self.gap.numerator < 0:
            raise ValueError("exactness gap cannot be negative")
        certificate_id = self.expansion_certificate_id
        if certificate_id is not None:
            certificate_id = _artifact_id(
                certificate_id,
                label="expansion certificate artifact",
            )
        reasons = tuple(
            str(reason).strip() for reason in self.reasons if str(reason).strip()
        )
        if self.status is ExactnessStatus.GLOBAL_OPTIMAL:
            if (
                self.universe_scope is not CandidateUniverseScope.FULL_OFFICIAL
                or self.solver_status is not SolverStatus.OPTIMAL
                or not self.action_surface_complete
                or not self.search_complete
                or self.best_bound is None
                or self.gap is None
                or self.gap.numerator != 0
            ):
                raise ValueError("GLOBAL_OPTIMAL exactness claim is internally inconsistent")
        elif self.status is ExactnessStatus.OPTIMAL_WITHIN_CERTIFIED_UNIVERSE:
            if (
                self.universe_scope is not CandidateUniverseScope.SCOPED
                or self.solver_status is not SolverStatus.OPTIMAL
                or not self.action_surface_complete
                or not self.search_complete
                or self.expansion_result is not ExpansionResult.NO_MATERIAL_IMPROVEMENT
                or certificate_id is None
            ):
                raise ValueError(
                    "OPTIMAL_WITHIN_CERTIFIED_UNIVERSE requires a successful expansion certificate"
                )
        elif self.status is ExactnessStatus.EPSILON_GLOBAL_OPTIMAL:
            if (
                self.universe_scope is not CandidateUniverseScope.FULL_OFFICIAL
                or not self.action_surface_complete
                or self.best_bound is None
                or self.gap is None
            ):
                raise ValueError("EPSILON_GLOBAL_OPTIMAL requires full universe/bound/gap")
        elif self.status in {
            ExactnessStatus.FEASIBLE_INCUMBENT,
            ExactnessStatus.INCONCLUSIVE,
        } and not reasons:
            raise ValueError(f"{self.status.value} requires explicit limiting reasons")
        object.__setattr__(self, "filter_identity", filter_identity)
        object.__setattr__(self, "expansion_certificate_id", certificate_id)
        object.__setattr__(self, "reasons", reasons)

    @property
    def publication_exactness_eligible(self) -> bool:
        return self.status in {
            ExactnessStatus.GLOBAL_OPTIMAL,
            ExactnessStatus.EPSILON_GLOBAL_OPTIMAL,
            ExactnessStatus.OPTIMAL_WITHIN_CERTIFIED_UNIVERSE,
        }

    def semantic_payload(self) -> dict[str, object]:
        return {
            "status": self.status.value,
            "candidate_universe_id": str(self.candidate_universe_id),
            "universe_scope": self.universe_scope.value,
            "solver_status": self.solver_status.value,
            "action_surface_complete": self.action_surface_complete,
            "search_complete": self.search_complete,
            "best_bound": (
                None if self.best_bound is None else self.best_bound.semantic_payload()
            ),
            "gap": None if self.gap is None else self.gap.semantic_payload(),
            "filter_identity": self.filter_identity,
            "expansion_result": self.expansion_result.value,
            "expansion_certificate_id": self.expansion_certificate_id,
            "numeric_error_bound": self.numeric_error_bound.semantic_payload(),
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision_input: DecisionInput
    selected_action: DecisionAction
    alternatives: tuple[DecisionAction, ...]
    solver: SolverCertificate
    exactness: ExactnessClaim
    enumerated_actions: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported DecisionResult schema_version")
        if (
            isinstance(self.enumerated_actions, bool)
            or not isinstance(self.enumerated_actions, int)
            or self.enumerated_actions <= 0
        ):
            raise ValueError("decision result must enumerate at least one legal action")
        if self.solver.incumbent_objective is None:
            raise ValueError("decision result requires a feasible solver incumbent")
        if self.exactness.candidate_universe_id != self.decision_input.candidate_universe_id:
            raise ValueError("exactness candidate universe does not match DecisionInput")
        if self.exactness.solver_status is not self.solver.status:
            raise ValueError("exactness solver status does not match solver certificate")
        if self.exactness.best_bound != self.solver.best_bound:
            raise ValueError("exactness best bound does not match solver certificate")
        if self.exactness.gap != self.solver.gap:
            raise ValueError("exactness gap does not match solver certificate")
        if self.exactness.numeric_error_bound != self.solver.numeric_error_bound:
            raise ValueError("exactness numeric error does not match solver certificate")
        alternatives = tuple(self.alternatives)
        action_ids = [
            self.selected_action.action_id,
            *(row.action_id for row in alternatives),
        ]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("decision result alternatives contain duplicate actions")
        object.__setattr__(self, "alternatives", alternatives)

    @property
    def decision_input_id(self) -> DecisionInputId:
        return self.decision_input.decision_input_id

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-result",
            "schema_version": self.schema_version,
            "decision_input": self.decision_input.semantic_payload(),
            "selected_action": self.selected_action.semantic_payload(),
            "alternatives": [row.semantic_payload() for row in self.alternatives],
            "solver": self.solver.semantic_payload(),
            "exactness": self.exactness.semantic_payload(),
            "enumerated_actions": self.enumerated_actions,
        }

    @property
    def decision_id(self) -> DecisionId:
        return DecisionId(canonical_sha256(self.semantic_payload()))
