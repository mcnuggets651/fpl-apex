"""Replay-derived algorithmic qualification for isolated receding-horizon solvers."""

from __future__ import annotations

from dataclasses import replace
import json

from apex_fpl.assurance.reference_solver_planning_exchange import (
    load_planning_reference_solver_request,
)
from apex_fpl.control.artifact_store import ArtifactStore
from apex_fpl.control.decision_policy_support import (
    load_chip_option_value_policy,
    load_continuation_value_policy,
)
from apex_fpl.control.manager_state_store import load_manager_state
from apex_fpl.control.ruleset_store import load_ruleset_artifact
from apex_fpl.core.canonical import canonical_json_bytes, canonical_sha256
from apex_fpl.core.ids import ManagerStateId, PlanningResultId, RuleSetId
from apex_fpl.core.reference_solver_planning_io import (
    PlanningReferenceSolverStatus,
    REFERENCE_SOLVER_PLANNING_CONTRACT,
)
from apex_fpl.core.reference_solver_planning_qualification import (
    PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE,
    PlanningReferenceSolverAlgorithmicQualificationCertificate,
    PlanningReferenceSolverQualificationCase,
    PlanningReferenceSolverQualificationCorpus,
    planning_reference_worker_subject_id,
)
from apex_fpl.core.reference_solver_worker import (
    ReferenceSolverWorkerArtifact,
    ReferenceSolverWorkerQualification,
)
from apex_fpl.decision.planning_store import load_planning_result
from apex_fpl.decision.store import load_candidate_universe
from apex_fpl.workers.reference_solver_planning import solve_planning_reference_request


def _object(raw: bytes, *, label: str) -> dict[str, object]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} must be object")
    if canonical_json_bytes(payload) != raw:
        raise ValueError(f"{label} is not canonical JSON")
    return payload


def store_planning_reference_solver_qualification_case(
    case: PlanningReferenceSolverQualificationCase,
    *,
    store: ArtifactStore,
) -> str:
    store.read_bytes(case.request_artifact_id)
    store.read_bytes(case.expected_planning_result_artifact_id)
    load_candidate_universe(case.candidate_universe_artifact_id, store=store)
    return store.put_bytes(
        canonical_json_bytes(case.semantic_payload()),
        media_type="application/json",
        schema_name="apex-planning-reference-solver-qualification-case",
        schema_version="1",
    ).artifact_id


def load_planning_reference_solver_qualification_case(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> PlanningReferenceSolverQualificationCase:
    payload = _object(
        store.read_bytes(artifact_id),
        label="planning reference solver qualification case",
    )
    if payload.get("schema_name") != "apex-planning-reference-solver-qualification-case":
        raise ValueError("not a planning reference solver qualification case")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported planning reference solver qualification case schema")
    case = PlanningReferenceSolverQualificationCase(
        request_artifact_id=str(payload.get("request_artifact_id") or ""),
        expected_planning_result_artifact_id=str(
            payload.get("expected_planning_result_artifact_id") or ""
        ),
        candidate_universe_artifact_id=str(payload.get("candidate_universe_artifact_id") or ""),
    )
    if case.case_id != artifact_id:
        raise ValueError("planning qualification case semantic identity mismatch")
    store.read_bytes(case.request_artifact_id)
    store.read_bytes(case.expected_planning_result_artifact_id)
    load_candidate_universe(case.candidate_universe_artifact_id, store=store)
    return case


def store_planning_reference_solver_qualification_corpus(
    corpus: PlanningReferenceSolverQualificationCorpus,
    *,
    store: ArtifactStore,
) -> str:
    for artifact_id in corpus.case_artifact_ids:
        load_planning_reference_solver_qualification_case(artifact_id, store=store)
    return store.put_bytes(
        canonical_json_bytes(corpus.semantic_payload()),
        media_type="application/json",
        schema_name="apex-planning-reference-solver-qualification-corpus",
        schema_version="1",
    ).artifact_id


def load_planning_reference_solver_qualification_corpus(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> PlanningReferenceSolverQualificationCorpus:
    payload = _object(
        store.read_bytes(artifact_id),
        label="planning reference solver qualification corpus",
    )
    if payload.get("schema_name") != "apex-planning-reference-solver-qualification-corpus":
        raise ValueError("not a planning reference solver qualification corpus")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported planning reference solver qualification corpus schema")
    rows = payload.get("case_artifact_ids")
    if not isinstance(rows, list) or any(not isinstance(item, str) for item in rows):
        raise ValueError("planning qualification case_artifact_ids must be strings")
    corpus = PlanningReferenceSolverQualificationCorpus(
        season=str(payload.get("season") or ""),
        max_horizon_gameweeks=payload.get("max_horizon_gameweeks"),  # type: ignore[arg-type]
        solver_contract=str(payload.get("solver_contract") or ""),
        case_artifact_ids=tuple(rows),
    )
    if corpus.corpus_id != artifact_id:
        raise ValueError("planning qualification corpus semantic identity mismatch")
    for case_id in corpus.case_artifact_ids:
        load_planning_reference_solver_qualification_case(case_id, store=store)
    return corpus


def _shadow_subject(worker: ReferenceSolverWorkerArtifact) -> ReferenceSolverWorkerArtifact:
    return replace(
        worker,
        qualification_state=ReferenceSolverWorkerQualification.SHADOW,
        qualification_artifact_id=None,
    )


def _ratio_nonzero(value: object) -> bool:
    return isinstance(value, dict) and isinstance(value.get("numerator"), int) and value["numerator"] != 0


def _all_chips_available(request) -> bool:
    manager = request.manager_state
    gameweek = manager.get("gameweek")
    if isinstance(gameweek, bool) or not isinstance(gameweek, int):
        return False
    rules = {row.get("rule_id"): row.get("value") for row in request.ruleset.get("rules", []) if isinstance(row, dict)}
    first_last = rules.get("FPL-CHIP-FIRST-SET-LAST-GW-001")
    second_first = rules.get("FPL-CHIP-SECOND-SET-FIRST-GW-001")
    if not isinstance(first_last, int) or not isinstance(second_first, int):
        return False
    set_number = 1 if gameweek <= first_last else 2 if gameweek >= second_first else 0
    if not set_number:
        return False
    used_rows = manager.get("chips_used")
    if not isinstance(used_rows, list):
        return False
    used = {
        (row.get("chip"), row.get("set_number"))
        for row in used_rows
        if isinstance(row, dict)
    }
    if any((chip, set_number) in used for chip in ("TRIPLE_CAPTAIN", "BENCH_BOOST", "WILDCARD", "FREE_HIT")):
        return False
    fh_disallowed = rules.get("FPL-FREE-HIT-DISALLOWED-GWS-001")
    wc_disallowed = rules.get("FPL-WILDCARD-DISALLOWED-GWS-001")
    return not (
        isinstance(fh_disallowed, list)
        and gameweek in fh_disallowed
        or isinstance(wc_disallowed, list)
        and gameweek in wc_disallowed
    )


def _derived_case_coverage(request, expected, run) -> set[str]:
    coverage = {
        "FULL_OFFICIAL_ACTION_SURFACE",
        "MULTI_GAMEWEEK_OBJECTIVE",
        "ROOT_ACTION_PARITY",
        "SUPPORT_POLICY_BINDING",
        "TRAJECTORY_PARITY",
        "ZERO_GAP_COMPLETENESS",
    }
    option_rows = request.chip_option_policy.get("option_values")
    if isinstance(option_rows, list) and any(
        isinstance(row, dict) and _ratio_nonzero(row.get("value")) for row in option_rows
    ):
        coverage.add("TERMINAL_CHIP_RESERVE")
    rules = {row.get("rule_id"): row.get("value") for row in request.ruleset.get("rules", []) if isinstance(row, dict)}
    if (
        isinstance(rules.get("FPL-FREE-TRANSFER-GRANT-001"), int)
        and rules.get("FPL-FREE-TRANSFER-GRANT-001", 0) > 0
        and request.horizon_gameweeks >= 2
    ):
        coverage.add("FT_BANKING_SURFACE")
    players = request.candidate_universe.get("players")
    manager_squad = request.manager_state.get("squad")
    if isinstance(players, list) and isinstance(manager_squad, list) and len(players) > len(manager_squad):
        coverage.add("TRANSFER_FINANCE_SURFACE")
    if _all_chips_available(request):
        coverage.update(
            {
                "BENCH_BOOST_SURFACE",
                "FREE_HIT_REVERSAL_SURFACE",
                "TRIPLE_CAPTAIN_SURFACE",
                "WILDCARD_PERSISTENCE_SURFACE",
            }
        )
    if run.selected_action_id != expected.selected_action.action_id:
        coverage.discard("ROOT_ACTION_PARITY")
    if run.selected_trajectory_id != expected.selected_trajectory.trajectory_id:
        coverage.discard("TRAJECTORY_PARITY")
    if (
        run.solver_status is not PlanningReferenceSolverStatus.OPTIMAL
        or not run.search_complete
        or run.gap is None
        or run.gap.numerator != 0
        or expected.solver.gap is None
        or expected.solver.gap.numerator != 0
    ):
        coverage.discard("ZERO_GAP_COMPLETENESS")
    return coverage


def _replay_expected(case, request, *, store: ArtifactStore):
    universe = load_candidate_universe(case.candidate_universe_artifact_id, store=store).universe
    if canonical_sha256(universe.semantic_payload()) != canonical_sha256(request.candidate_universe):
        raise ValueError("planning qualification CandidateUniverse differs from sealed request")
    manager_id = ManagerStateId(canonical_sha256(request.manager_state))
    ruleset_id = RuleSetId(canonical_sha256(request.ruleset))
    manager = load_manager_state(manager_id, store=store)
    ruleset = load_ruleset_artifact(ruleset_id, store=store)
    continuation_id = canonical_sha256(request.continuation_policy)
    chip_option_id = canonical_sha256(request.chip_option_policy)
    continuation = load_continuation_value_policy(continuation_id, store=store)
    chip_option = load_chip_option_value_policy(chip_option_id, store=store)
    return load_planning_result(
        PlanningResultId(case.expected_planning_result_artifact_id),
        manager_state_id=manager.manager_state_id,
        universe=universe,
        ruleset=ruleset,
        continuation=continuation,
        chip_option=chip_option,
        store=store,
    ).result


def derive_planning_reference_solver_algorithmic_qualification(
    worker: ReferenceSolverWorkerArtifact,
    *,
    corpus_artifact_id: str,
    store: ArtifactStore,
) -> PlanningReferenceSolverAlgorithmicQualificationCertificate:
    if not store.verify(worker.code_artifact_id):
        raise ValueError("planning reference worker code artifact is missing/corrupt")
    if worker.solver_contract != REFERENCE_SOLVER_PLANNING_CONTRACT:
        raise ValueError("worker does not implement planning reference solver contract")
    corpus = load_planning_reference_solver_qualification_corpus(corpus_artifact_id, store=store)
    if worker.solver_contract != corpus.solver_contract:
        raise ValueError("planning worker/corpus solver contract mismatch")
    if corpus.season not in worker.valid_seasons:
        raise ValueError("planning qualification season outside worker scope")
    if corpus.max_horizon_gameweeks > worker.max_horizon_gameweeks:
        raise ValueError("planning qualification horizon outside worker scope")

    coverage: set[str] = set()
    passed = 0
    for case_id in corpus.case_artifact_ids:
        case = load_planning_reference_solver_qualification_case(case_id, store=store)
        request = load_planning_reference_solver_request(case.request_artifact_id, store=store).request
        if request.horizon_gameweeks > corpus.max_horizon_gameweeks:
            raise ValueError("planning qualification case horizon exceeds corpus scope")
        expected = _replay_expected(case, request, store=store)
        if canonical_sha256(expected.decision_input.semantic_payload()) != canonical_sha256(request.decision_input):
            raise ValueError("planning qualification expected DecisionInput differs from request")
        run = solve_planning_reference_request(request)
        if run.solver_status is not PlanningReferenceSolverStatus.OPTIMAL:
            raise ValueError(
                "planning reference qualification case did not terminate OPTIMAL: "
                f"{run.solver_status.value}"
            )
        expected_objective = expected.selection_objective
        if run.best_objective is None or (
            run.best_objective.numerator != expected_objective.numerator
            or run.best_objective.denominator != expected_objective.denominator
        ):
            raise ValueError("planning reference qualification objective parity failed")
        if run.selected_action_id != expected.selected_action.action_id:
            raise ValueError("planning reference qualification root-action parity failed")
        if run.selected_trajectory_id != expected.selected_trajectory.trajectory_id:
            raise ValueError("planning reference qualification trajectory parity failed")
        coverage.update(_derived_case_coverage(request, expected, run))
        passed += 1

    required = set(PLANNING_REFERENCE_SOLVER_REQUIRED_COVERAGE)
    missing = sorted(required - coverage)
    if missing:
        raise ValueError(
            "planning reference qualification corpus lacks mandatory derived coverage: "
            + ",".join(missing)
        )
    subject = _shadow_subject(worker)
    return PlanningReferenceSolverAlgorithmicQualificationCertificate(
        worker_subject_id=planning_reference_worker_subject_id(subject.semantic_payload()),
        worker_name=worker.worker_name,
        worker_version=worker.worker_version,
        worker_code_artifact_id=worker.code_artifact_id,
        solver_contract=worker.solver_contract,
        season=corpus.season,
        max_horizon_gameweeks=corpus.max_horizon_gameweeks,
        corpus_artifact_id=corpus_artifact_id,
        corpus_id=corpus.corpus_id,
        passed_case_count=passed,
        coverage_tags=tuple(sorted(coverage)),
    )


def store_planning_reference_solver_algorithmic_qualification(
    certificate: PlanningReferenceSolverAlgorithmicQualificationCertificate,
    *,
    store: ArtifactStore,
) -> str:
    store.read_bytes(certificate.worker_code_artifact_id)
    load_planning_reference_solver_qualification_corpus(certificate.corpus_artifact_id, store=store)
    return store.put_bytes(
        canonical_json_bytes(certificate.semantic_payload()),
        media_type="application/json",
        schema_name="apex-planning-reference-solver-algorithmic-qualification-certificate",
        schema_version="1",
    ).artifact_id


def _load_certificate(
    artifact_id: str,
    *,
    store: ArtifactStore,
) -> PlanningReferenceSolverAlgorithmicQualificationCertificate:
    payload = _object(
        store.read_bytes(artifact_id),
        label="planning reference algorithmic qualification certificate",
    )
    if payload.get("schema_name") != "apex-planning-reference-solver-algorithmic-qualification-certificate":
        raise ValueError("not a planning reference solver qualification certificate")
    if payload.get("schema_version") != 1:
        raise ValueError("unsupported planning reference qualification certificate schema")
    tags = payload.get("coverage_tags")
    if not isinstance(tags, list) or any(not isinstance(item, str) for item in tags):
        raise ValueError("planning qualification coverage_tags must be strings")
    certificate = PlanningReferenceSolverAlgorithmicQualificationCertificate(
        worker_subject_id=str(payload.get("worker_subject_id") or ""),
        worker_name=str(payload.get("worker_name") or ""),
        worker_version=str(payload.get("worker_version") or ""),
        worker_code_artifact_id=str(payload.get("worker_code_artifact_id") or ""),
        solver_contract=str(payload.get("solver_contract") or ""),
        season=str(payload.get("season") or ""),
        max_horizon_gameweeks=payload.get("max_horizon_gameweeks"),  # type: ignore[arg-type]
        corpus_artifact_id=str(payload.get("corpus_artifact_id") or ""),
        corpus_id=str(payload.get("corpus_id") or ""),
        passed_case_count=payload.get("passed_case_count"),  # type: ignore[arg-type]
        coverage_tags=tuple(tags),
        replay_algorithm_id=str(payload.get("replay_algorithm_id") or ""),
    )
    if certificate.certificate_id != artifact_id:
        raise ValueError("planning qualification certificate semantic identity mismatch")
    return certificate


def verify_planning_reference_solver_algorithmic_qualification(
    worker: ReferenceSolverWorkerArtifact,
    *,
    qualification_artifact_id: str,
    store: ArtifactStore,
    season: str,
    horizon_gameweeks: int,
) -> PlanningReferenceSolverAlgorithmicQualificationCertificate:
    stored = _load_certificate(qualification_artifact_id, store=store)
    replayed = derive_planning_reference_solver_algorithmic_qualification(
        worker,
        corpus_artifact_id=stored.corpus_artifact_id,
        store=store,
    )
    if replayed.semantic_payload() != stored.semantic_payload():
        raise ValueError("planning qualification certificate failed replay derivation")
    subject = _shadow_subject(worker)
    expected_subject = planning_reference_worker_subject_id(subject.semantic_payload())
    if stored.worker_subject_id != expected_subject:
        raise ValueError("planning qualification subject mismatch")
    if stored.worker_code_artifact_id != worker.code_artifact_id:
        raise ValueError("planning qualification code artifact mismatch")
    if stored.solver_contract != worker.solver_contract:
        raise ValueError("planning qualification solver contract mismatch")
    if stored.season != season:
        raise ValueError("planning qualification season mismatch")
    if horizon_gameweeks > stored.max_horizon_gameweeks:
        raise ValueError("planning qualification horizon does not cover decision")
    return stored
