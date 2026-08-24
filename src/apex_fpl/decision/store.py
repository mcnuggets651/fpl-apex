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
    DecisionPolicyId,
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


def _exact_int(value: object, *, label: str, minimum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an exact integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} must be >= {minimum}")
    return value


def _exact_bool(value: object, *, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be boolean")
    return value


def _list(value: object, *, label: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list")
    return value


def _dict_rows(value: object, *, label: str) -> list[dict[str, object]]:
    rows = _list(value, label=label)
    if any(not isinstance(row, dict) for row in rows):
        raise ValueError(f"{label} must contain objects only")
    return [row for row in rows if isinstance(row, dict)]


def _rv(raw: object) -> RationalValue:
    if not isinstance(raw, dict):
        raise ValueError("rational value must be an object")
    return RationalValue(
        _exact_int(raw.get("numerator"), label="rational numerator"),
        _exact_int(raw.get("denominator"), label="rational denominator", minimum=1),
    )


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
    if _exact_int(
        envelope.get("schema_version"),
        label="stored candidate universe schema_version",
    ) != 1:
        raise ValueError("unsupported stored candidate universe schema")
    raw = envelope.get("candidate_universe")
    if not isinstance(raw, dict):
        raise ValueError("stored candidate universe payload is missing")
    player_rows = _dict_rows(raw.get("players"), label="candidate universe players")
    source_rows = _list(
        raw.get("source_artifact_ids"),
        label="candidate universe source artifacts",
    )
    if any(not isinstance(item, str) for item in source_rows):
        raise ValueError("candidate universe source artifacts must be strings")
    universe = CandidateUniverse(
        global_world_id=GlobalWorldId(str(raw["global_world_id"])),
        scope=CandidateUniverseScope(str(raw["scope"])),
        players=tuple(
            CandidatePlayer(
                player_id=OfficialPlayerId(
                    _exact_int(row.get("player_id"), label="candidate player_id", minimum=1)
                ),
                team_id=_exact_int(row.get("team_id"), label="candidate team_id", minimum=1),
                position=str(row["position"]),
                current_price_tenths=_exact_int(
                    row.get("current_price_tenths"),
                    label="candidate current_price_tenths",
                    minimum=1,
                ),
            )
            for row in player_rows
        ),
        official_player_count=_exact_int(
            raw.get("official_player_count"),
            label="candidate official_player_count",
            minimum=1,
        ),
        source_artifact_ids=tuple(source_rows),
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
    chips = _list(raw.get("chips_considered"), label="DecisionInput chips_considered")
    if any(not isinstance(item, str) for item in chips):
        raise ValueError("DecisionInput chip names must be strings")
    return DecisionInput(
        manager_state_id=ManagerStateId(str(raw["manager_state_id"])),
        forecast_id=ForecastId(str(raw["forecast_id"])),
        ruleset_id=RuleSetId(str(raw["ruleset_id"])),
        candidate_universe_id=CandidateUniverseId(str(raw["candidate_universe_id"])),
        decision_policy_id=DecisionPolicyId(str(raw["decision_policy_id"])),
        gameweek=_exact_int(raw.get("gameweek"), label="DecisionInput gameweek", minimum=1),
        use_mode=DecisionUseMode(str(raw["use_mode"])),
        objective_model=DecisionObjectiveModel(str(raw["objective_model"])),
        max_normal_transfers=_exact_int(
            raw.get("max_normal_transfers"),
            label="DecisionInput max_normal_transfers",
            minimum=0,
        ),
        chips_considered=tuple(DecisionChip(item) for item in chips),
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
        hit_points=_exact_int(raw.get("hit_points"), label="decision hit_points", minimum=0),
        objective_points=_rv(raw["objective_points"]),
    )


def _official_ids(value: object, *, label: str) -> tuple[OfficialPlayerId, ...]:
    rows = _list(value, label=label)
    return tuple(
        OfficialPlayerId(_exact_int(item, label=f"{label} player_id", minimum=1))
        for item in rows
    )


def _action(raw: object) -> DecisionAction:
    if not isinstance(raw, dict):
        raise ValueError("DecisionAction payload must be an object")
    transfer_rows = _dict_rows(raw.get("transfers"), label="DecisionAction transfers")
    return DecisionAction(
        chip=DecisionChip(str(raw["chip"])),
        transfers=tuple(
            TransferMove(
                OfficialPlayerId(
                    _exact_int(
                        row.get("outgoing_player_id"),
                        label="transfer outgoing_player_id",
                        minimum=1,
                    )
                ),
                OfficialPlayerId(
                    _exact_int(
                        row.get("incoming_player_id"),
                        label="transfer incoming_player_id",
                        minimum=1,
                    )
                ),
            )
            for row in transfer_rows
        ),
        squad_ids=_official_ids(raw.get("squad_ids"), label="DecisionAction squad_ids"),
        xi_ids=_official_ids(raw.get("xi_ids"), label="DecisionAction xi_ids"),
        captain_id=OfficialPlayerId(
            _exact_int(raw.get("captain_id"), label="DecisionAction captain_id", minimum=1)
        ),
        vice_captain_id=OfficialPlayerId(
            _exact_int(raw.get("vice_captain_id"), label="DecisionAction vice_captain_id", minimum=1)
        ),
        bench_gk_id=OfficialPlayerId(
            _exact_int(raw.get("bench_gk_id"), label="DecisionAction bench_gk_id", minimum=1)
        ),
        outfield_bench_order=_official_ids(
            raw.get("outfield_bench_order"),
            label="DecisionAction outfield_bench_order",
        ),
        bank_after_tenths=_exact_int(
            raw.get("bank_after_tenths"),
            label="DecisionAction bank_after_tenths",
            minimum=0,
        ),
        mechanics=_mechanics(raw["mechanics"]),
    )


def _solver(raw: object) -> SolverCertificate:
    if not isinstance(raw, dict):
        raise ValueError("SolverCertificate payload must be an object")
    return SolverCertificate(
        status=SolverStatus(str(raw["status"])),
        incumbent_objective=(
            None if raw.get("incumbent_objective") is None else _rv(raw["incumbent_objective"])
        ),
        best_bound=None if raw.get("best_bound") is None else _rv(raw["best_bound"]),
        gap=None if raw.get("gap") is None else _rv(raw["gap"]),
        numeric_error_bound=_rv(raw["numeric_error_bound"]),
        message=str(raw["message"]),
    )


def _exactness(raw: object) -> ExactnessClaim:
    if not isinstance(raw, dict):
        raise ValueError("ExactnessClaim payload must be an object")
    reasons = _list(raw.get("reasons", []), label="ExactnessClaim reasons")
    if any(not isinstance(item, str) for item in reasons):
        raise ValueError("ExactnessClaim reasons must be strings")
    return ExactnessClaim(
        status=ExactnessStatus(str(raw["status"])),
        candidate_universe_id=CandidateUniverseId(str(raw["candidate_universe_id"])),
        universe_scope=CandidateUniverseScope(str(raw["universe_scope"])),
        solver_status=SolverStatus(str(raw["solver_status"])),
        action_surface_complete=_exact_bool(
            raw.get("action_surface_complete"),
            label="ExactnessClaim action_surface_complete",
        ),
        search_complete=_exact_bool(
            raw.get("search_complete"),
            label="ExactnessClaim search_complete",
        ),
        best_bound=None if raw.get("best_bound") is None else _rv(raw["best_bound"]),
        gap=None if raw.get("gap") is None else _rv(raw["gap"]),
        filter_identity=str(raw["filter_identity"]),
        expansion_result=ExpansionResult(str(raw["expansion_result"])),
        expansion_certificate_id=(
            None
            if raw.get("expansion_certificate_id") is None
            else str(raw["expansion_certificate_id"])
        ),
        numeric_error_bound=_rv(raw["numeric_error_bound"]),
        reasons=tuple(reasons),
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
    if _exact_int(
        envelope.get("schema_version"),
        label="stored decision result schema_version",
    ) != 1:
        raise ValueError("unsupported stored decision result schema")
    raw = envelope.get("decision_result")
    if not isinstance(raw, dict):
        raise ValueError("stored decision result payload is missing")
    alternatives = _list(raw.get("alternatives"), label="stored decision alternatives")
    result = DecisionResult(
        decision_input=_decision_input(raw["decision_input"]),
        selected_action=_action(raw["selected_action"]),
        alternatives=tuple(_action(item) for item in alternatives),
        solver=_solver(raw["solver"]),
        exactness=_exactness(raw["exactness"]),
        enumerated_actions=_exact_int(
            raw.get("enumerated_actions"),
            label="decision enumerated_actions",
            minimum=1,
        ),
    )
    if str(result.decision_id) != str(envelope.get("decision_id")):
        raise ValueError("decision semantic identity mismatch during replay")
    return StoredDecisionResult(result=result, artifact_id=artifact_id)
