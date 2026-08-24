"""Immutable storage and offline replay for Slice 8 decision artifacts."""

from __future__ import annotations

from dataclasses import dataclass
import json

from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.core.canonical import canonical_json_bytes
from apex_fpl.core.decision import (
    CandidatePlayer,
    CandidateUniverse,
    CandidateUniverseScope,
    DecisionAction,
    DecisionChip,
    DecisionInput,
    DecisionMechanics,
    DecisionObjectiveModel,
    DecisionResult,
    DecisionUseMode,
    ExactnessClaim,
    ExactnessStatus,
    ExpansionResult,
    RationalValue,
    SolverCertificate,
    SolverStatus,
    TransferMove,
)
from apex_fpl.core.identity import OfficialPlayerId
from apex_fpl.core.ids import (
    CandidateUniverseId,
    ForecastId,
    GlobalWorldId,
    ManagerStateId,
    RuleSetId,
)


@dataclass(frozen=True, slots=True)
class StoredCandidateUniverse:
    universe: CandidateUniverse
    artifact_id: str


@dataclass(frozen=True, slots=True)
class StoredDecisionResult:
    result: DecisionResult
    artifact_id: str


def _json_object(content: bytes, *, label: str) -> dict[str, object]:
    try:
        raw = json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be a JSON object")
    return raw


def _rv(raw: object) -> RationalValue:
    if not isinstance(raw, dict):
        raise ValueError("rational value must be an object")
    return RationalValue(int(raw["numerator"]), int(raw["denominator"]))


def store_candidate_universe(
    universe: CandidateUniverse,
    *,
    store: ArtifactStore,
) -> StoredCandidateUniverse:
    for artifact_id in universe.source_artifact_ids:
        store.read_bytes(artifact_id)
    envelope = {
        "schema_name": "apex-stored-candidate-universe",
        "schema_version": 1,
        "candidate_universe_id": str(universe.candidate_universe_id),
        "candidate_universe": universe.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-candidate-universe",
        schema_version="1",
    )
    return StoredCandidateUniverse(universe=universe, artifact_id=ref.artifact_id)


def load_candidate_universe(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredCandidateUniverse:
    envelope = _json_object(
        store.read_bytes(artifact_id),
        label="stored candidate universe",
    )
    if envelope.get("schema_name") != "apex-stored-candidate-universe":
        raise ValueError("not an Apex stored candidate universe")
    if int(envelope.get("schema_version", -1)) != 1:
        raise ValueError("unsupported stored candidate universe schema")
    raw = envelope.get("candidate_universe")
    if not isinstance(raw, dict):
        raise ValueError("stored candidate universe payload is missing")
    player_rows = raw.get("players")
    source_rows = raw.get("source_artifact_ids")
    if not isinstance(player_rows, list) or not isinstance(source_rows, list):
        raise ValueError("stored candidate universe is incomplete")
    universe = CandidateUniverse(
        global_world_id=GlobalWorldId(str(raw["global_world_id"])),
        scope=CandidateUniverseScope(str(raw["scope"])),
        players=tuple(
            CandidatePlayer(
                player_id=OfficialPlayerId(int(row["player_id"])),
                team_id=int(row["team_id"]),
                position=str(row["position"]),
                current_price_tenths=int(row["current_price_tenths"]),
            )
            for row in player_rows
            if isinstance(row, dict)
        ),
        official_player_count=int(raw["official_player_count"]),
        source_artifact_ids=tuple(str(item) for item in source_rows),
        filter_artifact_id=(
            None
            if raw.get("filter_artifact_id") is None
            else str(raw["filter_artifact_id"])
        ),
    )
    if str(universe.candidate_universe_id) != str(envelope.get("candidate_universe_id")):
        raise ValueError("candidate universe semantic identity mismatch during replay")
    for source_artifact_id in universe.source_artifact_ids:
        store.read_bytes(source_artifact_id)
    return StoredCandidateUniverse(universe=universe, artifact_id=artifact_id)


def _decision_input(raw: object) -> DecisionInput:
    if not isinstance(raw, dict):
        raise ValueError("DecisionInput payload must be an object")
    chips = raw.get("chips_considered")
    if not isinstance(chips, list):
        raise ValueError("DecisionInput chips_considered must be a list")
    return DecisionInput(
        manager_state_id=ManagerStateId(str(raw["manager_state_id"])),
        forecast_id=ForecastId(str(raw["forecast_id"])),
        ruleset_id=RuleSetId(str(raw["ruleset_id"])),
        candidate_universe_id=CandidateUniverseId(
            str(raw["candidate_universe_id"])
        ),
        gameweek=int(raw["gameweek"]),
        use_mode=DecisionUseMode(str(raw["use_mode"])),
        objective_model=DecisionObjectiveModel(str(raw["objective_model"])),
        max_normal_transfers=int(raw["max_normal_transfers"]),
        chips_considered=tuple(DecisionChip(str(item)) for item in chips),
        numeric_policy_id=str(raw["numeric_policy_id"]),
    )


def _mechanics(raw: object) -> DecisionMechanics:
    if not isinstance(raw, dict):
        raise ValueError("DecisionMechanics payload must be an object")
    return DecisionMechanics(
        xi_points=_rv(raw["xi_points"]),
        autosub_points=_rv(raw["autosub_points"]),
        captain_bonus=_rv(raw["captain_bonus"]),
        squad_points_if_bench_boost=_rv(raw["squad_points_if_bench_boost"]),
        points_before_hits=_rv(raw["points_before_hits"]),
        hit_points=int(raw["hit_points"]),
        objective_points=_rv(raw["objective_points"]),
    )


def _action(raw: object) -> DecisionAction:
    if not isinstance(raw, dict):
        raise ValueError("DecisionAction payload must be an object")
    transfer_rows = raw.get("transfers")
    squad_rows = raw.get("squad_ids")
    xi_rows = raw.get("xi_ids")
    bench_rows = raw.get("outfield_bench_order")
    if not all(isinstance(row, list) for row in (transfer_rows, squad_rows, xi_rows, bench_rows)):
        raise ValueError("DecisionAction list fields are malformed")
    return DecisionAction(
        chip=DecisionChip(str(raw["chip"])),
        transfers=tuple(
            TransferMove(
                OfficialPlayerId(int(row["outgoing_player_id"])),
                OfficialPlayerId(int(row["incoming_player_id"])),
            )
            for row in transfer_rows
            if isinstance(row, dict)
        ),
        squad_ids=tuple(OfficialPlayerId(int(item)) for item in squad_rows),
        xi_ids=tuple(OfficialPlayerId(int(item)) for item in xi_rows),
        captain_id=OfficialPlayerId(int(raw["captain_id"])),
        vice_captain_id=OfficialPlayerId(int(raw["vice_captain_id"])),
        bench_gk_id=OfficialPlayerId(int(raw["bench_gk_id"])),
        outfield_bench_order=tuple(
            OfficialPlayerId(int(item)) for item in bench_rows
        ),
        bank_after_tenths=int(raw["bank_after_tenths"]),
        mechanics=_mechanics(raw["mechanics"]),
    )


def _solver(raw: object) -> SolverCertificate:
    if not isinstance(raw, dict):
        raise ValueError("SolverCertificate payload must be an object")
    return SolverCertificate(
        status=SolverStatus(str(raw["status"])),
        incumbent_objective=(
            None
            if raw.get("incumbent_objective") is None
            else _rv(raw["incumbent_objective"])
        ),
        best_bound=(None if raw.get("best_bound") is None else _rv(raw["best_bound"])),
        gap=None if raw.get("gap") is None else _rv(raw["gap"]),
        numeric_error_bound=_rv(raw["numeric_error_bound"]),
        message=str(raw["message"]),
    )


def _exactness(raw: object) -> ExactnessClaim:
    if not isinstance(raw, dict):
        raise ValueError("ExactnessClaim payload must be an object")
    return ExactnessClaim(
        status=ExactnessStatus(str(raw["status"])),
        candidate_universe_id=CandidateUniverseId(
            str(raw["candidate_universe_id"])
        ),
        universe_scope=CandidateUniverseScope(str(raw["universe_scope"])),
        solver_status=SolverStatus(str(raw["solver_status"])),
        action_surface_complete=bool(raw["action_surface_complete"]),
        search_complete=bool(raw["search_complete"]),
        best_bound=(None if raw.get("best_bound") is None else _rv(raw["best_bound"])),
        gap=None if raw.get("gap") is None else _rv(raw["gap"]),
        filter_identity=str(raw["filter_identity"]),
        expansion_result=ExpansionResult(str(raw["expansion_result"])),
        expansion_certificate_id=(
            None
            if raw.get("expansion_certificate_id") is None
            else str(raw["expansion_certificate_id"])
        ),
        numeric_error_bound=_rv(raw["numeric_error_bound"]),
        reasons=tuple(str(item) for item in raw.get("reasons", [])),
    )


def store_decision_result(
    result: DecisionResult,
    *,
    store: ArtifactStore,
) -> StoredDecisionResult:
    envelope = {
        "schema_name": "apex-stored-decision-result",
        "schema_version": 1,
        "decision_id": str(result.decision_id),
        "decision_result": result.semantic_payload(),
    }
    ref = store.put_bytes(
        canonical_json_bytes(envelope),
        media_type="application/json",
        schema_name="apex-stored-decision-result",
        schema_version="1",
    )
    return StoredDecisionResult(result=result, artifact_id=ref.artifact_id)


def load_decision_result(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> StoredDecisionResult:
    envelope = _json_object(
        store.read_bytes(artifact_id),
        label="stored decision result",
    )
    if envelope.get("schema_name") != "apex-stored-decision-result":
        raise ValueError("not an Apex stored decision result")
    if int(envelope.get("schema_version", -1)) != 1:
        raise ValueError("unsupported stored decision result schema")
    raw = envelope.get("decision_result")
    if not isinstance(raw, dict):
        raise ValueError("stored decision result payload is missing")
    alternatives = raw.get("alternatives")
    if not isinstance(alternatives, list):
        raise ValueError("stored decision alternatives must be a list")
    result = DecisionResult(
        decision_input=_decision_input(raw["decision_input"]),
        selected_action=_action(raw["selected_action"]),
        alternatives=tuple(_action(item) for item in alternatives),
        solver=_solver(raw["solver"]),
        exactness=_exactness(raw["exactness"]),
        enumerated_actions=int(raw["enumerated_actions"]),
    )
    if str(result.decision_id) != str(envelope.get("decision_id")):
        raise ValueError("decision semantic identity mismatch during replay")
    return StoredDecisionResult(result=result, artifact_id=artifact_id)
