"""Typed legal-decision contracts for Apex V2 Slice 8.

The DecisionEngine optimises one declared action surface over one declared candidate
universe. Exactness is therefore a first-class scope, not a marketing adjective.
Expected-value mechanics use rational numbers and explicitly name the marginal
independence baseline that Slice 9 later stress-tests with correlated scenarios.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .canonical import canonical_sha256
from .identity import OfficialPlayerId
from .ids import (
    CandidateUniverseId,
    DecisionId,
    DecisionInputId,
    ForecastId,
    GlobalWorldId,
    ManagerStateId,
    RuleSetId,
)


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


@dataclass(frozen=True, slots=True)
class CandidatePlayer:
    player_id: OfficialPlayerId
    team_id: int
    position: str
    current_price_tenths: int

    def __post_init__(self) -> None:
        if isinstance(self.team_id, bool) or not isinstance(self.team_id, int) or self.team_id <= 0:
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
        if self.scope is CandidateUniverseScope.FULL_OFFICIAL and len(players) != self.official_player_count:
            raise ValueError("FULL_OFFICIAL candidate universe must contain every Official player")
        if len(players) > self.official_player_count:
            raise ValueError("candidate universe cannot exceed Official player count")
        artifacts = tuple(sorted({str(item).strip() for item in self.source_artifact_ids if str(item).strip()}))
        if not artifacts:
            raise ValueError("candidate universe requires immutable source lineage")
        for artifact in artifacts:
            algorithm, separator, digest = artifact.partition(":")
            if algorithm != "sha256" or not separator or len(digest) != 64:
                raise ValueError("candidate universe source artifact must be sha256 identity")
            try:
                int(digest, 16)
            except ValueError as exc:
                raise ValueError("candidate universe source artifact digest is invalid") from exc
        object.__setattr__(self, "players", players)
        object.__setattr__(self, "source_artifact_ids", artifacts)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-candidate-universe",
            "schema_version": self.schema_version,
            "global_world_id": str(self.global_world_id),
            "scope": self.scope.value,
            "official_player_count": self.official_player_count,
            "players": [row.semantic_payload() for row in self.players],
            "source_artifact_ids": list(self.source_artifact_ids),
        }

    @property
    def candidate_universe_id(self) -> CandidateUniverseId:
        return CandidateUniverseId(canonical_sha256(self.semantic_payload()))

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
    gameweek: int
    use_mode: DecisionUseMode
    objective_model: DecisionObjectiveModel
    max_normal_transfers: int
    chips_considered: tuple[DecisionChip, ...]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported DecisionInput schema_version")
        if isinstance(self.gameweek, bool) or not isinstance(self.gameweek, int) or self.gameweek <= 0:
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
        object.__setattr__(self, "chips_considered", chips)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-input",
            "schema_version": self.schema_version,
            "manager_state_id": str(self.manager_state_id),
            "forecast_id": str(self.forecast_id),
            "ruleset_id": str(self.ruleset_id),
            "candidate_universe_id": str(self.candidate_universe_id),
            "gameweek": self.gameweek,
            "use_mode": self.use_mode.value,
            "objective_model": self.objective_model.value,
            "max_normal_transfers": self.max_normal_transfers,
            "chips_considered": [chip.value for chip in self.chips_considered],
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
        if isinstance(self.denominator, bool) or not isinstance(self.denominator, int) or self.denominator <= 0:
            raise ValueError("rational denominator must be positive integer")

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
        if isinstance(self.hit_points, bool) or not isinstance(self.hit_points, int) or self.hit_points < 0:
            raise ValueError("decision hit_points must be nonnegative integer")

    def semantic_payload(self) -> dict[str, object]:
        return {
            "xi_points": self.xi_points.semantic_payload(),
            "autosub_points": self.autosub_points.semantic_payload(),
            "captain_bonus": self.captain_bonus.semantic_payload(),
            "squad_points_if_bench_boost": self.squad_points_if_bench_boost.semantic_payload(),
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
            raise ValueError("decision action transfers contain duplicate outgoing players")
        if len({row.incoming_player_id for row in transfers}) != len(transfers):
            raise ValueError("decision action transfers contain duplicate incoming players")
        squad = tuple(sorted(self.squad_ids))
        xi = tuple(sorted(self.xi_ids))
        bench_order = tuple(self.outfield_bench_order)
        if len(squad) != 15 or len(set(squad)) != 15:
            raise ValueError("decision action requires exactly 15 unique squad players")
        if len(xi) != 11 or len(set(xi)) != 11 or not set(xi).issubset(set(squad)):
            raise ValueError("decision action requires exactly 11 unique XI players from squad")
        if self.captain_id == self.vice_captain_id or self.captain_id not in xi or self.vice_captain_id not in xi:
            raise ValueError("captain and vice must be distinct XI players")
        bench = set(squad) - set(xi)
        if self.bench_gk_id not in bench:
            raise ValueError("bench goalkeeper must be outside XI")
        if len(bench_order) != 3 or len(set(bench_order)) != 3:
            raise ValueError("decision action requires three ordered outfield substitutes")
        if set(bench_order) | {self.bench_gk_id} != bench:
            raise ValueError("decision bench order must cover the four non-XI players exactly")
        if isinstance(self.bank_after_tenths, bool) or not isinstance(self.bank_after_tenths, int) or self.bank_after_tenths < 0:
            raise ValueError("decision bank_after_tenths must be nonnegative integer")
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
            "outfield_bench_order": [int(item) for item in self.outfield_bench_order],
            "bank_after_tenths": self.bank_after_tenths,
            "mechanics": self.mechanics.semantic_payload(),
        }

    @property
    def action_id(self) -> str:
        return canonical_sha256({"schema_name": "apex-decision-action", **self.semantic_payload()})


@dataclass(frozen=True, slots=True)
class ExactnessClaim:
    universe_scope: CandidateUniverseScope
    action_surface_complete: bool
    search_complete: bool
    global_optimum: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        expected_global = (
            self.universe_scope is CandidateUniverseScope.FULL_OFFICIAL
            and self.action_surface_complete
            and self.search_complete
        )
        if self.global_optimum != expected_global:
            raise ValueError("global_optimum claim is inconsistent with exactness scope")
        reasons = tuple(str(reason).strip() for reason in self.reasons if str(reason).strip())
        if not self.global_optimum and not reasons:
            raise ValueError("non-global exactness claim requires explicit reasons")
        object.__setattr__(self, "reasons", reasons)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "universe_scope": self.universe_scope.value,
            "action_surface_complete": self.action_surface_complete,
            "search_complete": self.search_complete,
            "global_optimum": self.global_optimum,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True, slots=True)
class DecisionResult:
    decision_input_id: DecisionInputId
    selected_action: DecisionAction
    alternatives: tuple[DecisionAction, ...]
    exactness: ExactnessClaim
    enumerated_actions: int
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("unsupported DecisionResult schema_version")
        if isinstance(self.enumerated_actions, bool) or not isinstance(self.enumerated_actions, int) or self.enumerated_actions <= 0:
            raise ValueError("decision result must enumerate at least one legal action")
        alternatives = tuple(self.alternatives)
        action_ids = [self.selected_action.action_id, *(row.action_id for row in alternatives)]
        if len(action_ids) != len(set(action_ids)):
            raise ValueError("decision result alternatives contain duplicate actions")
        object.__setattr__(self, "alternatives", alternatives)

    def semantic_payload(self) -> dict[str, object]:
        return {
            "schema_name": "apex-decision-result",
            "schema_version": self.schema_version,
            "decision_input_id": str(self.decision_input_id),
            "selected_action": self.selected_action.semantic_payload(),
            "alternatives": [row.semantic_payload() for row in self.alternatives],
            "exactness": self.exactness.semantic_payload(),
            "enumerated_actions": self.enumerated_actions,
        }

    @property
    def decision_id(self) -> DecisionId:
        return DecisionId(canonical_sha256(self.semantic_payload()))
